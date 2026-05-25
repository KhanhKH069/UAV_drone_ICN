"""
scripts/drone_edge_client.py
Mã nguồn chạy trên Raspberry Pi 5 (Tầng 1 + 2).

Chức năng:
1. Ghi âm liên tục từ microphone (16kHz, mono).
2. Gửi luồng âm thanh qua WebSocket tới Edge Server (Tầng 3).
3. Nhận lệnh JSON (intent, entities) từ Server.
4. Chuyển đổi lệnh thành tín hiệu MAVLink qua DroneKit-Python.
5. (MỚI) Computer Vision: Chạy YOLOv8 & ByteTrack trên luồng độc lập, sử dụng PID Controller để bám đuổi mục tiêu tự động.

Yêu cầu cài đặt trên Raspberry Pi 5:
  pip install dronekit pymavlink websockets sounddevice numpy webrtcvad scipy opencv-python ultralytics

Chạy script:
  python scripts/drone_edge_client.py --connect /dev/ttyAMA0 --baud 57600 --server ws://192.168.1.100:8765
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import threading
from collections import deque

import cv2
import numpy as np
import sounddevice as sd
import websockets
import webrtcvad
from scipy.signal import butter, lfilter
from ultralytics import YOLO
from dronekit import connect, VehicleMode

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("drone_edge_client")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Trạng thái chia sẻ (Shared State) & PID Controller
# ─────────────────────────────────────────────────────────────────────────────

class DroneState:
    """Quản lý trạng thái chia sẻ giữa luồng Audio (nhận lệnh) và luồng Vision (điều khiển)."""
    def __init__(self):
        self.is_tracking = False
        self.target_class = "person" # Mặc định theo dõi người
        self.target_color = None
        self.command_queue = deque()

class PIDController:
    """Bộ điều khiển PID rời rạc (Discrete PID) theo Ziegler-Nichols."""
    def __init__(self, Kp, Ki, Kd, dt=0.05):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.dt = dt
        self.integral = 0
        self.prev_error = 0

    def compute(self, error):
        self.integral += error * self.dt
        derivative = (error - self.prev_error) / self.dt
        output = (self.Kp * error) + (self.Ki * self.integral) + (self.Kd * derivative)
        self.prev_error = error
        return output

# ─────────────────────────────────────────────────────────────────────────────
# 2. MAVLink / DroneKit Controller
# ─────────────────────────────────────────────────────────────────────────────

class UAVController:
    def __init__(self, connection_string: str, baud: int):
        self.connection_string = connection_string
        self.baud = baud
        self.vehicle = None
        self.target_altitude = 2.0  # Độ cao cất cánh mặc định (mét)

    def connect_vehicle(self):
        logger.info(f"Đang kết nối tới UAV tại {self.connection_string} (Baud: {self.baud})...")
        try:
            self.vehicle = connect(self.connection_string, wait_ready=True, baud=self.baud)
            logger.info("✅ Kết nối UAV thành công!")
        except Exception as e:
            logger.error(f"❌ Không thể kết nối UAV: {e}")
            sys.exit(1)

    def execute_command(self, intent: str, entities: dict, state: DroneState):
        """Map các intent (NLP) sang lệnh điều khiển DroneKit."""
        if not self.vehicle:
            logger.warning("UAV chưa kết nối. Bỏ qua lệnh.")
            return

        # Tính toán tham số
        distance_m = entities.get("distance_cm", 100) / 100.0
        angle_deg = entities.get("angle_deg", 90)

        logger.info(f"Thực thi lệnh: {intent} | Tham số: {entities}")

        # Nếu đang tracking mà nhận lệnh di chuyển tay, thì tắt tracking
        if state.is_tracking and intent not in ["follow_target", "get_battery", "get_altitude"]:
            logger.info("🛑 Hủy chế độ tự động bám đuổi để thực thi lệnh thủ công.")
            state.is_tracking = False

        if intent == "take_off":
            self._arm_and_takeoff(distance_m if "distance_cm" in entities else self.target_altitude)
        elif intent == "land":
            self.vehicle.mode = VehicleMode("LAND")
        elif intent == "return_home":
            self.vehicle.mode = VehicleMode("RTL")
        elif intent == "hover" or intent == "stop":
            state.is_tracking = False
            self.vehicle.mode = VehicleMode("LOITER")
        elif intent == "follow_target":
            state.target_class = entities.get("class", "person")
            state.is_tracking = True
            logger.info(f"🎯 Bật chế độ bám đuổi mục tiêu (PID + YOLO): {state.target_class}")
        elif intent == "move_forward":
            self._send_ned_velocity(distance_m, 0, 0, duration=2)
        elif intent == "move_backward":
            self._send_ned_velocity(-distance_m, 0, 0, duration=2)
        elif intent == "move_left":
            self._send_ned_velocity(0, -distance_m, 0, duration=2)
        elif intent == "move_right":
            self._send_ned_velocity(0, distance_m, 0, duration=2)
        elif intent == "ascend":
            self._send_ned_velocity(0, 0, -distance_m, duration=2) # Z âm là đi lên
        elif intent == "descend":
            self._send_ned_velocity(0, 0, distance_m, duration=2)  # Z dương là đi xuống
        elif intent == "rotate_left":
            self._condition_yaw(angle_deg, relative=True, direction=-1)
        elif intent == "rotate_right":
            self._condition_yaw(angle_deg, relative=True, direction=1)
        elif intent == "get_battery":
            bat = self.vehicle.battery
            logger.info(f"Pin UAV: {bat.voltage}V, {bat.level}%")
        elif intent == "get_altitude":
            alt = self.vehicle.location.global_relative_frame.alt
            logger.info(f"Độ cao hiện tại: {alt}m")
        else:
            logger.warning(f"Lệnh chưa được hỗ trợ trên MAVLink: {intent}")

    # --- Các hàm Helper của DroneKit ---

    def _arm_and_takeoff(self, aTargetAltitude):
        """Mở khóa động cơ và cất cánh."""
        logger.info("Basic pre-arm checks")
        if not self.vehicle.is_armable:
            logger.error("UAV chưa sẵn sàng để arm.")
            return

        logger.info("Chuyển mode GUIDED, arming motors")
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            logger.info(" Chờ arming...")
            time.sleep(1)

        logger.info(f"Cất cánh tới độ cao {aTargetAltitude}m!")
        self.vehicle.simple_takeoff(aTargetAltitude)

    def _send_ned_velocity(self, velocity_x, velocity_y, velocity_z, duration):
        """Di chuyển UAV theo trục NED có giới hạn thời gian (Dùng cho điều khiển thủ công)."""
        from pymavlink import mavutil
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0,       # time_boot_ms (not used)
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED, # Khung tọa độ so với Drone
            0b0000111111000111, # type_mask (chỉ dùng vận tốc)
            0, 0, 0, # x, y, z positions (not used)
            velocity_x, velocity_y, velocity_z, # x, y, z velocity in m/s
            0, 0, 0, # x, y, z acceleration 
            0, 0)    # yaw, yaw_rate 
        
        self.vehicle.send_mavlink(msg)
        time.sleep(duration)
        # Dừng lại
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED, 0b0000111111000111,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.vehicle.send_mavlink(msg)

    def _send_continuous_velocity_and_yaw(self, vx, vy, vz, yaw_rate):
        """Điều khiển PID liên tục không blocking (Dùng cho Tracking vòng lặp)."""
        from pymavlink import mavutil
        # Type mask: Bỏ qua vị trí(1-3), gia tốc(7-9), yaw(11). Dùng vận tốc(4-6) và yaw_rate(12).
        type_mask = 0b0000010111000111
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, 
            mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED, 
            type_mask,
            0, 0, 0, 
            vx, vy, vz, 
            0, 0, 0, 
            0, yaw_rate)
        self.vehicle.send_mavlink(msg)

    def _condition_yaw(self, heading, relative=False, direction=1):
        """Quay UAV thủ công."""
        from pymavlink import mavutil
        is_relative = 1 if relative else 0
        msg = self.vehicle.message_factory.command_long_encode(
            0, 0,       
            mavutil.mavlink.MAV_CMD_CONDITION_YAW, 
            0,          
            heading,    
            0,          
            direction,  
            is_relative,
            0, 0, 0)    
        self.vehicle.send_mavlink(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Luồng Thực Thi Lệnh (Command Executor)
# ─────────────────────────────────────────────────────────────────────────────

def command_executor_loop(state: DroneState, controller: UAVController):
    """Liên tục đọc hàng đợi lệnh và thực thi tuần tự (chặn chờ lệnh bay xong)."""
    logger.info("⚙️ Khởi động luồng Command Executor...")
    while True:
        if state.command_queue:
            cmd = state.command_queue.popleft()
            intent = cmd.get("intent")
            entities = cmd.get("entities", {})
            controller.execute_command(intent, entities, state)
        else:
            time.sleep(0.1)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Computer Vision (YOLOv8 + ByteTrack) & PID Tracking Loop
# ─────────────────────────────────────────────────────────────────────────────

def vision_tracking_loop(state: DroneState, controller: UAVController):
    """Luồng camera chạy YOLOv8, ByteTrack và tính toán PID độc lập."""
    logger.info("📷 Khởi động luồng Computer Vision (YOLOv8 + ByteTrack)...")
    try:
        # Load model YOLOv8 Nano (nhẹ nhất)
        model = YOLO("yolov8n.pt") 
    except Exception as e:
        logger.error(f"Không thể tải model YOLOv8: {e}")
        return

    # Khởi tạo Camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.warning("⚠️ Không thể mở Camera /dev/video0. (Nếu chạy giả lập, bỏ qua lỗi này).")
        # Thay vì crash, ta vẫn giữ thread chạy ngầm mô phỏng (tùy chọn)
        # return

    # Thông số PID theo báo cáo (Ziegler-Nichols)
    dt = 0.05  # Tương đương ~20 FPS (50ms/frame)
    pid_yaw = PIDController(Kp=0.35, Ki=0.00, Kd=0.05, dt=dt)
    pid_throttle = PIDController(Kp=0.40, Ki=0.02, Kd=0.08, dt=dt)
    pid_pitch = PIDController(Kp=0.30, Ki=0.01, Kd=0.06, dt=dt)
    
    # Kích thước khung hình tham chiếu
    REF_WIDTH, REF_HEIGHT = 640, 480
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, REF_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, REF_HEIGHT)

    logger.info("✅ Luồng Vision & PID sẵn sàng.")

    while True:
        if not cap.isOpened():
            time.sleep(1)
            continue

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        if not state.is_tracking or not controller.vehicle:
            # Nếu không có lệnh tracking, chỉ đọc frame bỏ qua xử lý AI để tiết kiệm CPU
            time.sleep(0.05)
            continue

        # Inference YOLOv8 + ByteTrack
        # persist=True giữ track id, verbose=False tắt log rác
        results = model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False)
        
        target_found = False
        velocity_yaw_rate = 0.0
        velocity_z = 0.0
        velocity_x = 0.0

        if results and len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                
                # Chỉ lọc đối tượng khớp với state.target_class ("person", "car")
                if cls_name == state.target_class:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    bbox_h = y2 - y1

                    # 1. Tính toán sai số (Errors)
                    error_x = cx - (REF_WIDTH / 2.0)   # Lệch tâm ngang (pixels)
                    error_y = cy - (REF_HEIGHT / 2.0)  # Lệch tâm dọc (pixels)
                    
                    # Ước lượng depth dựa trên chiều cao bbox (Giả sử H người ở 1.5m là 200px)
                    ref_bbox_h = 200.0 
                    # Sai số chiều Z = ref_bbox_h - bbox_h. (bbox nhỏ -> ở xa -> tiến tới)
                    error_z = ref_bbox_h - bbox_h

                    # 2. Đưa qua 3 bộ PID rời rạc
                    
                    # --- ADAPTIVE PID (Gain Scheduling) ---
                    # Điều chỉnh Kp của Pitch dựa trên độ lớn khung hình (mục tiêu ở quá gần hay quá xa)
                    if bbox_h > 250:
                        # Ở rất gần -> giảm giật cục
                        pid_pitch.Kp = 0.15 
                    elif bbox_h < 100:
                        # Ở rất xa -> tăng tốc bám đuổi
                        pid_pitch.Kp = 0.45
                    else:
                        # Khoảng cách lý tưởng
                        pid_pitch.Kp = 0.30

                    # Yaw (xoay ngang)
                    raw_yaw = pid_yaw.compute(error_x)
                    # Chuyển đổi sang rad/s và giới hạn tốc độ xoay tối đa (Vd: 0.5 rad/s)
                    velocity_yaw_rate = np.clip(raw_yaw / 100.0, -0.5, 0.5) 
                    
                    # Throttle (lên/xuống)
                    raw_z = pid_throttle.compute(error_y)
                    # UAV trục Z âm là đi lên, dương là đi xuống. Giới hạn 1m/s
                    velocity_z = np.clip(raw_z / 100.0, -1.0, 1.0) 
                    
                    # Pitch (tiến/lùi)
                    raw_x = pid_pitch.compute(error_z)
                    velocity_x = np.clip(raw_x / 100.0, -1.0, 1.0)
                    
                    target_found = True
                    break # Chỉ track 1 mục tiêu khớp đầu tiên
        
        if target_found:
            # Gửi vận tốc liên tục qua MAVLink
            controller._send_continuous_velocity_and_yaw(
                vx=velocity_x, 
                vy=0, # Bỏ qua Roll
                vz=velocity_z, 
                yaw_rate=velocity_yaw_rate
            )
        else:
            # Mất dấu mục tiêu -> Hover tại chỗ
            controller._send_continuous_velocity_and_yaw(0, 0, 0, 0)
            
        # Giữ vòng lặp chạy ổn định ở ~20FPS (50ms)
        time.sleep(0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Xử lý âm thanh: High-pass Filter & VAD
# ─────────────────────────────────────────────────────────────────────────────

def butter_highpass(cutoff, fs, order=5):
    """Tạo bộ lọc High-pass để lọc tiếng ồn cánh quạt (tần số thấp)."""
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    return b, a

def apply_highpass_filter(data: bytes, b, a) -> bytes:
    """Áp dụng high-pass filter lên luồng bytes PCM 16-bit."""
    audio_np = np.frombuffer(data, dtype=np.int16)
    filtered = lfilter(b, a, audio_np)
    return filtered.astype(np.int16).tobytes()

# ─────────────────────────────────────────────────────────────────────────────
# 5. WebSocket Audio Streamer
# ─────────────────────────────────────────────────────────────────────────────

async def stream_audio_and_receive_commands(server_uri: str, lang: str, controller: UAVController, state: DroneState):
    """Mở WebSocket, ghi âm (có VAD + Filter), và nhận lệnh."""
    sample_rate = 16000
    chunk_ms = 30  # WebRTC VAD chỉ hỗ trợ frame 10ms, 20ms, 30ms
    block_size = int(sample_rate * chunk_ms / 1000)
    
    vad = webrtcvad.Vad(3)
    b, a = butter_highpass(cutoff=300.0, fs=sample_rate, order=5)
    audio_queue = asyncio.Queue()

    def mic_callback(indata, frames, time_info, status):
        if status:
            logger.warning(f"Mic status: {status}")
        audio_queue.put_nowait(bytes(indata))

    logger.info(f"Kết nối WebSocket tới Edge Server: {server_uri}")
    
    while True:
        try:
            async with websockets.connect(server_uri) as ws:
                logger.info("✅ Edge Server Connected! Bắt đầu nghe lệnh...")
                
                with sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=block_size,
                    callback=mic_callback
                ):
                    
                    async def send_audio_task():
                        num_silence_frames = 0
                        is_speaking = False
                        
                        while True:
                            chunk = await audio_queue.get()
                            clean_chunk = apply_highpass_filter(chunk, b, a)
                            is_speech = vad.is_speech(clean_chunk, sample_rate)
                            
                            if is_speech:
                                if not is_speaking:
                                    logger.info("🗣️ Đã phát hiện giọng nói, bắt đầu gửi lên Edge Server...")
                                is_speaking = True
                                num_silence_frames = 0
                                await ws.send(clean_chunk)
                            else:
                                if is_speaking:
                                    await ws.send(clean_chunk)
                                    num_silence_frames += 1
                                    if num_silence_frames > 50:
                                        logger.info("🤫 Dừng nói (silence timeout). Chốt câu lệnh.")
                                        await ws.send(json.dumps({"event": "endpoint"}))
                                        is_speaking = False
                                        num_silence_frames = 0

                    async def receive_commands_task():
                        while True:
                            response = await ws.recv()
                            msg = json.loads(response)
                            msg_type = msg.get("type")
                            
                            if msg_type == "partial":
                                print(f"  [STT...] {msg.get('text', '')}", end="\r")
                            
                            elif msg_type == "command":
                                intent = msg.get("intent")
                                entities = msg.get("entities", {})
                                raw_text = msg.get("raw_text")
                                conf = msg.get("confidence")
                                logger.info(f"🎯 Lệnh nhận được (single): '{raw_text}' -> Intent: {intent} (conf: {conf})")
                                state.command_queue.clear()
                                state.command_queue.append({"intent": intent, "entities": entities})
                                
                            elif msg_type == "command_list":
                                commands = msg.get("commands", [])
                                raw_text = msg.get("raw_text")
                                logger.info(f"🎯 Lệnh nhận được (chuỗi {len(commands)} lệnh): '{raw_text}'")
                                # Clear queue để hủy các lệnh cũ đang chờ (ưu tiên lệnh mới nhất)
                                state.command_queue.clear()
                                for c in commands:
                                    state.command_queue.append(c)
                                
                            elif msg_type == "unknown":
                                logger.warning(f"❓ Lệnh không xác định: '{msg.get('raw_text', '')}'")

                    send_task = asyncio.create_task(send_audio_task())
                    recv_task = asyncio.create_task(receive_commands_task())
                    
                    done, pending = await asyncio.wait(
                        [send_task, recv_task],
                        return_when=asyncio.FIRST_EXCEPTION
                    )
                    for task in pending:
                        task.cancel()
                        
        except websockets.exceptions.ConnectionClosed:
            logger.error("Mất kết nối tới Edge Server. Thử lại sau 3s...")
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Lỗi WebSocket: {e}")
            await asyncio.sleep(3)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi 5 Drone Edge Client")
    parser.add_argument("--server", default="ws://192.168.1.100:8765/drone/stream", help="WS URI của Edge Server")
    parser.add_argument("--api-key", default="drone-secret", help="API Key")
    parser.add_argument("--drone-id", default="rpi5-uav-01", help="ID của Drone")
    parser.add_argument("--lang", default="vi", choices=["en", "vi"], help="Ngôn ngữ ra lệnh (vi sẽ qua dịch tự động)")
    parser.add_argument("--connect", default="udp:127.0.0.1:14550", help="Chuỗi kết nối MAVLink (vd: /dev/ttyAMA0)")
    parser.add_argument("--baud", default=57600, type=int, help="Baud rate MAVLink")
    args = parser.parse_args()

    # Trạng thái chia sẻ toàn cục
    global_state = DroneState()

    # Khởi tạo Drone Controller
    controller = UAVController(args.connect, args.baud)
    logger.info("Bỏ qua connect_vehicle() ở chế độ mock test.")

    # Khởi động Luồng CV + PID (chạy nền)
    vision_thread = threading.Thread(
        target=vision_tracking_loop, 
        args=(global_state, controller), 
        daemon=True
    )
    vision_thread.start()

    # Khởi động Luồng Command Executor
    executor_thread = threading.Thread(
        target=command_executor_loop,
        args=(global_state, controller),
        daemon=True
    )
    executor_thread.start()

    # URI Websocket
    uri = f"{args.server}?api_key={args.api_key}&drone_id={args.drone_id}&lang={args.lang}"

    # Chạy vòng lặp Audio/WS chính
    try:
        asyncio.run(stream_audio_and_receive_commands(uri, args.lang, controller, global_state))
    except KeyboardInterrupt:
        logger.info("Đã dừng chương trình (Ctrl+C).")

if __name__ == "__main__":
    main()
