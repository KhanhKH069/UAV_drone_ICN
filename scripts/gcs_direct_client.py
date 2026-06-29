import asyncio
import websockets
import pyaudio
import json
import argparse
from dronekit import connect, VehicleMode

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 4096

async def audio_stream(websocket, stream):
    """Bắt âm thanh từ Mic PC và gửi nội bộ qua WebSocket"""
    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            await websocket.send(data)
            await asyncio.sleep(0.01)
    except Exception as e:
        print(f"Audio stream error: {e}")

async def receive_commands(websocket, vehicle):
    """Nhận lệnh từ AI và điều khiển UAV qua Telemetry/MAVLink"""
    try:
        async for message in websocket:
            data = json.loads(message)
            print(f"Received Command: {data}")
            
            intent = data.get("intent")
            if not intent:
                continue
                
            if intent == "TAKEOFF":
                alt = data.get("entities", {}).get("altitude", 10)
                print(f"Taking off to {alt}m...")
                vehicle.mode = VehicleMode("GUIDED")
                vehicle.armed = True
                
                timeout = 15
                while not vehicle.armed and timeout > 0:
                    print("Waiting for arming...")
                    await asyncio.sleep(1)
                    timeout -= 1
                    
                if not vehicle.armed:
                    print("Error: Drone failed to arm. Check GPS lock or pre-arm sensors.")
                    continue
                    
                vehicle.simple_takeoff(alt)
                
            elif intent == "LAND":
                print("Landing...")
                vehicle.mode = VehicleMode("LAND")
                
            elif intent == "RETURN_TO_LAUNCH":
                print("Returning to Launch...")
                vehicle.mode = VehicleMode("RTL")
                
    except Exception as e:
        print(f"Command receiver error: {e}")

async def main_loop(server_uri, connection_string):
    print(f"Connecting to UAV Telemetry on {connection_string}...")
    vehicle = connect(connection_string, wait_ready=True, baud=57600)
    print("UAV Connected!")

    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

    print(f"Connecting to Local Edge Server: {server_uri}...")
    async with websockets.connect(server_uri) as websocket:
        print("WebSocket connected. Starting bidirectional streaming...")
        audio_task = asyncio.create_task(audio_stream(websocket, stream))
        cmd_task = asyncio.create_task(receive_commands(websocket, vehicle))
        await asyncio.gather(audio_task, cmd_task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCS Direct Client (Mic + MAVLink)")
    parser.add_argument("--server", type=str, default="ws://localhost:8000/ws/audio", help="Local WebSocket URI")
    parser.add_argument("--uav", type=str, default="COM3", help="COM Port of Telemetry Radio (e.g., COM3, /dev/ttyUSB0)")
    args = parser.parse_args()
    
    asyncio.run(main_loop(args.server, args.uav))
