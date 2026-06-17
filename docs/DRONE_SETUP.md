# Drone Edge Server — Hướng dẫn Setup

## Tổng quan

Tài liệu này hướng dẫn cách khởi động `UAV_drone_ICN` như một **Tầng 3 Edge Server** cho hệ thống điều khiển UAV bằng ngôn ngữ tự nhiên (theo kiến trúc đồ án *Vũ Nam Khánh et al., 2026*).

```
Raspberry Pi 5 (Tầng 1 + 2)          Edge Server / RTX A4000 (Tầng 3)
┌─────────────────────────┐           ┌─────────────────────────────────┐
│  Mic → Thu âm lệnh bay  │ ────────► │  ws://<SERVER_IP>:8765          │
│  Cảm biến IMU/GPS       │  WebSocket │  /drone/stream                  │
│  Camera (YOLOv8 + PID)  │           │                                 │
│  MAVLink → ESP32-S3     │ ◄──────── │  Step 1: Faster-Whisper STT     │
│                         │  JSON cmd  │  Step 2: NLLB (VI→EN nếu cần)  │
└─────────────────────────┘           │  Step 3: Regex Intent (< 10ms)  │
                                      │  Step 4: Ollama LLM (fallback)  │
                                      │                                 │
                                      │  Response:                      │
                                      │  {"intent":"move_forward",      │
                                      │   "entities":{"distance_cm":200}}│
                                      └─────────────────────────────────┘
```

---

## Yêu cầu hệ thống

| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB |
| GPU | Không bắt buộc | NVIDIA RTX (VRAM ≥ 8GB) |
| Disk | 20 GB | 50 GB (models cache) |
| Docker | 24+ | 24+ |
| Python | 3.11+ (test client) | 3.11+ |

---

## Bước 1 — Clone & Cấu hình

```bash
# Clone repo (nếu chưa có)
git clone https://github.com/KhanhKH069/UAV_drone_ICN.git
cd UAV_drone_ICN
git checkout real-time-text

# Tạo file cấu hình cho Drone
cp .env.drone.example .env.drone
```

Mở `.env.drone` và chỉnh các giá trị:

```bash
# Nếu chạy trên CPU (không có GPU):
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

# Nếu có NVIDIA GPU:
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# API key — Đổi thành chuỗi ngẫu nhiên
CLIENT_API_KEY=<chuỗi ngẫu nhiên mạnh>
```

---

## Bước 2 — Tải AI Models

```bash
# Tải Whisper model
docker run --rm -v UAV_drone_ICN_models-cache:/models \
  python:3.11-slim bash -c \
  "pip install faster-whisper && python -c \"
from faster_whisper import WhisperModel
WhisperModel('small', device='cpu', compute_type='int8', download_root='/models/whisper')
print('✅ Whisper downloaded')
\""

# Pull Ollama model (llama3:8b ~4.7GB)
docker-compose -f docker-compose.drone.yml up -d ollama
docker exec drone-ollama ollama pull llama3:8b
```

---

## Bước 3 — Khởi động Drone Edge Server

```bash
# Khởi động toàn bộ stack Drone
docker-compose -f docker-compose.drone.yml --env-file .env.drone up -d

# Kiểm tra logs
docker-compose -f docker-compose.drone.yml logs -f

# Kiểm tra health
curl http://localhost:8056/health      # API Gateway
curl http://localhost:8001/health      # Whisper STT
curl http://localhost:8005/health      # Agent (LLM)
```

---

## Bước 4 — Test kết nối từ PC/Laptop

```bash
# Cài dependencies test client
pip install websockets numpy httpx scipy sounddevice

# Test nhanh lệnh tiếng Anh (REST mode)
python scripts/test_drone_client.py --text "fly forward 2 meters"

# Test lệnh tiếng Việt
python scripts/test_drone_client.py --text "bay tới trước 3 mét" --lang vi

# Test lệnh tracking
python scripts/test_drone_client.py --text "follow the person in red"

# Test với server từ xa (thay IP)
python scripts/test_drone_client.py --host 192.168.1.100 --text "take off"
```

**Ví dụ output mong đợi:**
```
============================================================
  🚁 Drone Edge Server — Test Client
  Server : ws://localhost:8765
  Lang   : en
============================================================

🚁 Test REST endpoint: POST http://localhost:8005/drone/classify
📝 Text: 'fly forward 2 meters' (lang=en)

  ✅ Kết quả (215ms):
     Intent    : move_forward
     Entities  : {'distance_cm': 200}
     Confidence: 95%
     Latency   : 205ms (LLM)
```

---

## Bước 5 — Tích hợp vào Raspberry Pi 5

Trên Raspberry Pi 5, thêm đoạn code sau vào module điều khiển (thay thế hoặc bổ sung bên cạnh module STT/NLP hiện có):

```python
# drone_edge_client.py — chạy trên Raspberry Pi 5
import asyncio, json, numpy as np, sounddevice as sd, websockets

EDGE_SERVER = "ws://192.168.1.100:8765/drone/stream"
API_KEY = "<client-api-key>"
SAMPLE_RATE = 16000

async def stream_commands():
    uri = f"{EDGE_SERVER}?api_key={API_KEY}&drone_id=rpi5-01&lang=vi"
    async with websockets.connect(uri) as ws:
        def callback(indata, frames, t, status):
            asyncio.get_event_loop().call_soon_threadsafe(
                send_chunk, bytes(indata)
            )
        
        audio_queue = asyncio.Queue()

        def send_chunk(data):
            audio_queue.put_nowait(data)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, 
                           dtype="int16", blocksize=8000, callback=callback):
            while True:
                chunk = await audio_queue.get()
                await ws.send(chunk)
                
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 0.01))
                    if msg["type"] == "command":
                        # Đưa vào MAVLink / PID controller
                        handle_command(msg["intent"], msg["entities"])
                except asyncio.TimeoutError:
                    pass

def handle_command(intent: str, entities: dict):
    """Map intent → MAVLink command."""
    print(f"→ MAVLink: {intent} {entities}")
    # Tích hợp với DroneKit / MAVLink ở đây
    if intent == "take_off":
        vehicle.simple_takeoff(entities.get("distance_cm", 100) / 100)
    elif intent == "move_forward":
        # ... gửi lệnh MAVLink SET_POSITION_TARGET_LOCAL_NED
        pass

asyncio.run(stream_commands())
```

---

## So sánh: Trước vs Sau khi tích hợp Edge Server

| | v1.0 (Chỉ RPi5) | v2.0 (+ Edge Server) |
|---|---|---|
| **STT Model** | Faster-Whisper tiny (CPU) | Faster-Whisper small/large (GPU) |
| **STT Latency** | 200–400ms | 150–250ms (GPU) |
| **NLP** | Regex 28 intent | Regex + LLM Fallback |
| **Lệnh tiếng Việt** | ❌ Không hỗ trợ | ✅ NLLB tự dịch sang EN |
| **CPU load trên RPi5** | ~85% (STT+Vision+PID) | ~40% (chỉ Vision+PID) |
| **Mở rộng intent** | Cần sửa code | Cập nhật prompt Ollama |

---

## Troubleshooting

### Lỗi kết nối WebSocket: `Connection refused`
```bash
# Kiểm tra container đang chạy
docker ps | grep drone

# Xem log lỗi
docker logs drone-api-gateway
```

### Whisper trả về text rỗng
```bash
# Kiểm tra audio đầu vào có đúng format 16kHz mono int16 không
# Kiểm tra log Whisper
docker logs drone-whisperlive
```

### Ollama timeout (LLM Fallback chậm)
```bash
# Pull model nhẹ hơn
docker exec drone-ollama ollama pull phi3:mini

# Cập nhật .env.drone
LLM_MODEL=phi3:mini
docker-compose -f docker-compose.drone.yml --env-file .env.drone restart agent-service
```

### NLLB không dịch được tiếng Việt
```bash
# Kiểm tra model đã tải chưa
curl http://localhost:8002/health

# Xem log
docker logs drone-nllb
```
