import asyncio
import websockets
import sounddevice as sd
import numpy as np
import base64
import requests
import json
import threading
import queue
import sys

# --- CẤU HÌNH ---
WS_URI = "ws://localhost:8001/stream"
HTTP_URI = "http://localhost:8001/transcribe"
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.2  # 200ms mỗi chunk
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

# VAD Đơn giản bằng Năng lượng (Âm lượng)
RMS_THRESHOLD = 0.015 
MAX_SILENCE_CHUNKS = 4  # 4 * 0.2s = 0.8s im lặng thì ngắt câu

def get_best_input_device():
    devices = sd.query_devices()
    
    # 1. Ưu tiên số 1: TÌM ĐÍCH DANH CHỮ "monitor" ĐỂ LẤY ÁP LỰC LOA MÁY TÍNH (Visual Device / System Audio)
    for idx, d in enumerate(devices):
        if d['max_input_channels'] > 0 and 'monitor' in d['name'].lower():
            return idx
            
    # 2. Virtual Cable / Stereo Mix trên Windows
    for idx, d in enumerate(devices):
        if d['max_input_channels'] > 0 and ('cable' in d['name'].lower() or 'stereo mix' in d['name'].lower()):
            return idx
            
    # 3. Fallback dùng 'pulse' thường (nhưng tránh lỗi upmix ALSA)
    for idx, d in enumerate(devices):
        if d['max_input_channels'] > 0 and ('pulse' in d['name'].lower() and 'upmix' not in d['name'].lower()):
            return idx
            
    return None

q = queue.Queue()

def audio_callback(indata, frames, time, status):
    """Bắt âm thanh từ Mic và ném vào hàng đợi (Queue)"""
    if status:
        print(status, file=sys.stderr)
    q.put(indata.copy())

def send_http_post(audio_data):
    """Hàm gửi cục Audio tĩnh chốt qua HTTP POST"""
    print("\n[VAD] Đang ngắt câu... Bắn HTTP POST gửi cho hệ thống nghiệp vụ!")
    f32 = audio_data.astype(np.float32) / 32768.0
    b64 = base64.b64encode(f32.tobytes()).decode()
    
    try:
        resp = requests.post(HTTP_URI, json={
            "audio_b64": b64,
            "language": "auto",
            "vad_filter": True
        })
        result = resp.json()
        print(f"✅ [CHỐT CÂU IN ĐẬM]: {result.get('text')}\n")
        print("-" * 50)
    except Exception as e:
        print(f"❌ [Lỗi HTTP]: {e}")

async def async_main():
    print("🔄 Đang kết nối tới WebSocket Server...")
    
    device_idx = get_best_input_device()
    if device_idx is not None:
        device_name = sd.query_devices()[device_idx]['name']
        print(f"🎯 Đã khóa mục tiêu: Sẽ lấy âm thanh từ Loa Ảo [{device_name}]")
    else:
        print("⚠️ Không tìm thấy Monitor/Cable ảo. Dùng Input mặc định!")

    try:
        async with websockets.connect(WS_URI) as ws:
            print("🚀 Đã liên kết! Hệ thống đang lắng nghe âm thanh đầu vào (Micro hoặc Loa Ảo mặc định)...\n")
            print("🎙 Mẹo test: Hãy bắt đầu nói, hoặc bật một bản nhạc lên nếu đây là thiết bị Stereo Mix/Monitor!\n")
            
            # Khởi tạo Rổ đựng Audio
            full_sentence_buffer = []
            is_speaking = False
            silence_count = 0
            
            # --- TÁC VỤ 1: Lắng nghe chữ mờ từ Server ---
            async def receive_partial():
                try:
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get("type") == "partial":
                            # In đè lên giao diện tạo cảm giác Typewriter
                            text = data['text']
                            # Dùng \r để xóa dòng cũ và in đè lên
                            print(f"\r\033[K[Gõ mờ...]: {text}", end="", flush=True)
                except websockets.exceptions.ConnectionClosed:
                    pass

            asyncio.create_task(receive_partial())
            
            # --- TÁC VỤ 2: Đọc Audio và phân luồng gửi ---
            loop = asyncio.get_running_loop()
            with sd.InputStream(device=device_idx, samplerate=SAMPLE_RATE, channels=1, dtype='int16', 
                                blocksize=CHUNK_SAMPLES, callback=audio_callback):
                while True:
                    # Lấy Chunk ra khỏi hàng đợi
                    chunk = await loop.run_in_executor(None, q.get)
                    
                    # Tính độ ồn (VAD test)
                    rms = np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2))
                    is_silence = rms < RMS_THRESHOLD
                    
                    if not is_silence:
                        is_speaking = True
                        silence_count = 0
                        full_sentence_buffer.append(chunk) # Bỏ vào rổ
                        
                        # 1. Bắn liên tục byte âm thanh bằng WebSockets
                        await ws.send(chunk.tobytes())
                        
                    else:
                        if is_speaking:
                            full_sentence_buffer.append(chunk) # Thu thêm tí đuôi im lặng
                            silence_count += 1
                            
                            # Vẫn tiếp tục truyền cho WebSockets để nó dịch nốt cái âm đuôi
                            await ws.send(chunk.tobytes())
                            
                            # NẾU IM LẶNG ĐỦ LÂU -> CUT CÂU!
                            if silence_count >= MAX_SILENCE_CHUNKS:
                                is_speaking = False
                                
                                # 2. Báo cho WebSocket Server dọn dẹp bộ đệm
                                await ws.send(json.dumps({"event": "endpoint"}))
                                
                                # 3. Cất chung cả rổ này đem đi bắn bằng HTTP POST
                                # (Chạy ở luồng riêng để không kẹt vòng thu âm)
                                full_audio = np.concatenate(full_sentence_buffer)
                                threading.Thread(target=send_http_post, args=(full_audio,)).start()
                                
                                # Xóa rổ chuẩn bị cho vòng lặp hội thoại tiếp theo
                                full_sentence_buffer = []

    except ConnectionRefusedError:
        print("❌ Lỗi: Server chưa bật hoặc chặn kết nối ở cổng 8001!")
    except KeyboardInterrupt:
        print("\nTắt thu âm.")

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Thoát.")
