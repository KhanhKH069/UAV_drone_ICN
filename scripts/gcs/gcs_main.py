import argparse
import asyncio
import json
import logging
import signal
import sys
import threading
import urllib.request

import websockets

import os
from datetime import datetime
import csv

from gcs_flight_controller import DroneState, UAVController, command_executor_loop
from gcs_vision import vision_tracking_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gcs_main")

_R   = "\033[91m"
_G   = "\033[92m"
_Y   = "\033[93m"
_B   = "\033[94m"
_C   = "\033[96m"
_RST = "\033[0m"
_BOLD = "\033[1m"

_shutdown_event = threading.Event()

class BlackboxLogger:
    """Ghi log chuyến bay vào file CSV — tương tự Flight Data Recorder."""
    def __init__(self, log_dir="logs"):
        os.makedirs(log_dir, exist_ok=True)
        filename = datetime.now().strftime("flight_log_%Y%m%d_%H%M%S.csv")
        self.filepath = os.path.join(log_dir, filename)
        
        with open(self.filepath, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "battery_percent", "voltage", "altitude_m",
                "pitch", "roll", "yaw", "satellites",
                "last_intent", "command_result"
            ])
            
        logger.info(f"📓 Blackbox Logger khởi tạo tại: {self.filepath}")

    def log(self, telemetry_data: dict, last_intent: str, command_result: str = ""):
        with open(self.filepath, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().isoformat(),
                telemetry_data.get("battery", 0),
                telemetry_data.get("voltage", 0),
                telemetry_data.get("alt", 0),
                telemetry_data.get("pitch", 0),
                telemetry_data.get("roll", 0),
                telemetry_data.get("yaw", 0),
                telemetry_data.get("satellites", 0),
                last_intent,
                command_result,
            ])


def _print_status(state: DroneState, last_intent: str, telemetry: dict):
    """Định kỳ in trạng thái hệ thống bằng màu ANSI."""
    bat  = telemetry.get("battery", 0)
    alt  = telemetry.get("alt", 0.0)
    sats = telemetry.get("satellites", 0)
    yaw  = telemetry.get("yaw", 0.0)

    bat_color  = _G if bat > 30 else _Y if bat > 15 else _R
    sats_color = _G if sats >= 6 else _Y if sats >= 4 else _R
    track_str  = f"{_C}🎯 TRACKING: {state.target_class}{_RST}" if state.is_tracking else f"{_Y}👁️  IDLE{_RST}"

    print(
        f"\r{_BOLD}GCS{_RST} | "
        f"{bat_color}🔋 {bat:3.0f}%{_RST} | "
        f"⛰️ {alt:5.1f}m | "
        f"🧲 Yaw:{yaw:5.1f}° | "
        f"{sats_color}📡 {sats} sats{_RST} | "
        f"Last: {_B}{last_intent}{_RST} | "
        f"{track_str}     ",
        end="", flush=True
    )

async def gcs_listener_loop(server_uri: str, token: str, controller: UAVController, state: DroneState):
    """Mở WebSocket, lắng nghe lệnh và gửi Telemetry định kỳ."""
    logger.info(f"Kết nối WebSocket tới API Gateway: {server_uri}")
    
    blackbox = BlackboxLogger()
    last_executed_intent = "none"
    last_telemetry: dict = {}

    while not _shutdown_event.is_set():
        try:
            async with websockets.connect(server_uri) as ws:
                logger.info(f"\n{_G}✅ Đã kết nối WebSocket! Đang gửi xác thực...{_RST}")
                await ws.send(json.dumps({"event": "auth", "token": token}))
                logger.info(f"{_G}✅ Đang chờ lệnh từ App...{_RST}")

                async def receive_commands_task():
                    nonlocal last_executed_intent
                    while True:
                        response = await ws.recv()
                        msg = json.loads(response)
                        msg_type = msg.get("type")

                        if msg_type == "partial":
                            print(f"  [{_C}STT...{_RST}] {msg.get('text', '')}       ", end="\r")

                        elif msg_type == "command":
                            intent = msg.get("intent")
                            entities = msg.get("entities", {})
                            raw_text = msg.get("raw_text")
                            conf = msg.get("confidence")
                            print()
                            import time
                            now = time.time()
                            if now - state.last_command_time < 0.8:
                                logger.warning(f"⏳ Debounce: Bỏ qua lệnh '{raw_text}' do lệnh trước đến quá gần (<800ms)")
                                continue
                            state.last_command_time = now

                            logger.info(f"🎯 [{_G}COMMAND{_RST}] '{raw_text}' → {_B}{intent}{_RST} (conf: {conf}%)")
                            
                            last_executed_intent = intent
                            
                            state.command_queue.clear()
                            state.command_queue.append({"intent": intent, "entities": entities})

                        elif msg_type == "command_list":
                            commands = msg.get("commands", [])
                            raw_text = msg.get("raw_text")
                            print()
                            import time
                            now = time.time()
                            if now - state.last_command_time < 0.8:
                                logger.warning(f"⏳ Debounce: Bỏ qua chuỗi lệnh '{raw_text}' do đến quá gần (<800ms)")
                                continue
                            state.last_command_time = now

                            logger.info(f"🎯 [{_B}LIST{_RST}] Nhận chuỗi lệnh ({len(commands)} lệnh): '{raw_text}'")
                            
                            if commands:
                                last_executed_intent = commands[-1].get("intent", "none")
                                
                            state.command_queue.clear()
                            for c in commands:
                                state.command_queue.append(c)

                        elif msg_type == "unknown":
                            print()
                            logger.warning(f"{_Y}❓ Không rõ lệnh{_RST}: '{msg.get('raw_text', '')}'")

                async def send_telemetry_task():
                    """Gửi Telemetry mỗi giây và in status bar."""
                    nonlocal last_telemetry
                    tick = 0
                    while True:
                        try:
                            if controller.vehicle:
                                bat = controller.vehicle.battery
                                loc = controller.vehicle.location.global_relative_frame
                                att = controller.vehicle.attitude
                                gps = controller.vehicle.gps_0
                                
                                data = {
                                    "battery": bat.level if bat else 0,
                                    "voltage": bat.voltage if bat else 0,
                                    "alt": loc.alt if loc else 0,
                                    "pitch": att.pitch if att else 0,
                                    "roll": att.roll if att else 0,
                                    "yaw": att.yaw if att else 0,
                                    "satellites": gps.satellites_visible if gps else 0,
                                }
                                last_telemetry = data
                                await ws.send(json.dumps({"event": "telemetry", "data": data}))
                                
                                blackbox.log(data, last_executed_intent)

                                if tick % 5 == 0:
                                    _print_status(state, last_executed_intent, data)
                                tick += 1
                        except Exception as e:
                            logger.error(f"Lỗi gửi telemetry: {e}")
                        await asyncio.sleep(1.0)

                recv_task = asyncio.create_task(receive_commands_task())
                telemetry_task = asyncio.create_task(send_telemetry_task())

                done, pending = await asyncio.wait(
                    [recv_task, telemetry_task], return_when=asyncio.FIRST_EXCEPTION
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    if task.exception():
                        raise task.exception()

        except websockets.exceptions.ConnectionClosed:
            logger.error("Mất kết nối Websocket. Thử lại sau 3s...")
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Lỗi WebSocket: {e}")
            await asyncio.sleep(3)


def main():
    parser = argparse.ArgumentParser(description="PC Ground Control Station (GCS) Engine")
    parser.add_argument("--server", default="http://192.168.1.100:8056", help="HTTP URI API Gateway")
    parser.add_argument("--ws-server", default="ws://192.168.1.100:8765/drone/stream", help="WS URI")
    parser.add_argument("--client-id", default="drone-01", help="Client ID")
    parser.add_argument("--client-secret", default="drone-secret", help="Client Secret")
    parser.add_argument("--drone-id", default="UAV-01", help="ID của Drone")
    parser.add_argument("--lang", default="vi", choices=["en", "vi"], help="Ngôn ngữ STT")
    parser.add_argument("--port", default="COM3", help="Cổng kết nối Telemetry USB (ví dụ: COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", default=57600, type=int, help="Baud rate MAVLink")
    parser.add_argument("--video-source", default=1, type=int, help="ID thiết bị Video Capture")
    args = parser.parse_args()

    def _handle_shutdown(sig, frame):
        print(f"\n{_Y}\u26a0️  Nhận tín hiệu shutdown ({sig}). GCS đang tắt an toàn...{_RST}")
        _shutdown_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    print(f"""
{_B}╭────────────────────────────────────────────────────╮
│  🚁 GCS Engine v2.0 — UAV Voice Control System        │
│  Drone ID : {args.drone_id:<42}│
│  Server   : {args.server:<42}│
│  Port     : {args.port:<42}│
│  Language : {args.lang:<42}│
╰────────────────────────────────────────────────────╯{_RST}
""")

    global_state = DroneState()

    controller = UAVController(args.port, args.baud)
    controller.connect_vehicle(global_state)

    vision_thread = threading.Thread(
        target=vision_tracking_loop, args=(global_state, controller, args.video_source), daemon=True
    )
    vision_thread.start()

    executor_thread = threading.Thread(
        target=command_executor_loop, args=(global_state, controller), daemon=True
    )
    executor_thread.start()

    try:
        req = urllib.request.Request(
            f"{args.server}/auth/token",
            data=json.dumps({"client_id": args.client_id, "client_secret": args.client_secret}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            token_data = json.loads(response.read().decode())
            token = token_data.get("access_token")
            logger.info(f"{_G}✅ Đã xác thực JWT Token thành công!{_RST}")
    except Exception as e:
        logger.error(f"{_R}❌ Không thể lấy JWT Token từ server: {e}{_RST}")
        sys.exit(1)

    uri = f"{args.ws_server}?token={token}&drone_id={args.drone_id}&lang={args.lang}"

    try:
        asyncio.run(gcs_listener_loop(uri, token, controller, global_state))
    except KeyboardInterrupt:
        logger.info(f"{_Y}Đã dừng GCS Engine (Ctrl+C).{_RST}")

if __name__ == "__main__":
    main()
