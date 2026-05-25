# 🚁 UAV Voice Control Edge Server

Hệ thống **Tầng 3 (Edge AI Server)** dành cho đồ án điều khiển máy bay không người lái (UAV/Drone) bằng giọng nói tự nhiên, tái cấu trúc từ nền tảng *paraline-msagent*.

Đây là bộ não trung tâm xử lý AI, giúp giảm tải hoàn toàn cho **Raspberry Pi 5** trên Drone, đưa tốc độ nhận diện lệnh và phản hồi xuống mức `< 300ms`.

---

## 🌟 Kiến trúc 4 Bước Xử Lý AI (Pipeline)

Hệ thống hoạt động qua giao thức **WebSocket** (`ws://<IP>:8765/drone/stream`), nhận âm thanh từ Raspberry Pi 5 và trả về lệnh điều khiển (JSON).

1. **🎙️ Speech-to-Text (Faster-Whisper):** Nhận diện âm thanh giọng nói (Hỗ trợ model Tiny/Small INT8 tối ưu cho CPU hoặc Float16 cho GPU).
2. **🌐 Translation (NLLB-200):** Dịch tự động lệnh Tiếng Việt sang Tiếng Anh để xử lý đồng nhất.
3. **⚡ Intent Regex (Rule-based):** Xử lý cực nhanh (`<5ms`) 28 intent bay cơ bản (Cất cánh, hạ cánh, xoay, tiến lùi, v.v.). Trích xuất trực tiếp số liệu (khoảng cách, góc quay).
4. **🧠 LLM Fallback (Ollama):** Nếu câu lệnh quá phức tạp hoặc mơ hồ, Llama3/Gemma3 sẽ phân tích ngữ nghĩa và đoán ý định (Confidence > 0.7).

---

## 🛠️ Cấu trúc Thư mục

```text
paraline-msagent/
├── docker-compose.yml       # Khởi động cụm AI server (Microservices)
├── .env.drone.example       # File biến môi trường (Config model, API Key)
├── docs/
│   └── DRONE_SETUP.md       # 📖 Hướng dẫn chi tiết cách Setup & Cài đặt
├── scripts/
│   └── drone_edge_client.py # Mã nguồn chạy thực tế trên Raspberry Pi 5 (VAD + MAVLink)
│   └── test_drone_client.py # Mã nguồn test giả lập (Mic, File WAV, Text)
└── services/
    ├── api-gateway          # Cổng WebSocket nhận/trả tín hiệu từ Drone
    ├── agent-service        # Service gọi Ollama LLM
    ├── translation-service  # NLLB dịch tự động
    └── whisperlive-wrapper  # STT Whisper
```

---

## 🚀 Khởi động Nhanh

**1. Chuẩn bị biến môi trường**
```bash
cp .env.drone.example .env.drone
```
*Chỉnh sửa file `.env.drone` để chọn loại Model Whisper (cpu/cuda, int8/float16).*

**2. Khởi động AI Server**
```bash
docker-compose --env-file .env.drone up -d
```

**3. Tải Model LLM (Chỉ chạy lần đầu)**
```bash
docker exec drone-ollama ollama pull llama3:8b
```

**4. Test thử Server (Không cần mic)**
```bash
python scripts/test_drone_client.py --text "bay tới trước 3 mét" --lang vi
```

---

## 📖 Hướng dẫn chi tiết
Xem chi tiết cách cài đặt lên máy bay (Raspberry Pi 5) và kết nối với **MAVLink (Pixhawk/ArduPilot)** tại:  
👉 **[docs/DRONE_SETUP.md](docs/DRONE_SETUP.md)**

---
*Dự án được tuỳ biến riêng biệt dựa trên mã nguồn mở Paraline.*
