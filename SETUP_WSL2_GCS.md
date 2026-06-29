# HƯỚNG DẪN TÍCH HỢP MÔ HÌNH LAI (WSL2 + WINDOWS) CHO UAV GCS

Kiến trúc này cho phép bạn tận dụng **sức mạnh AI 100% của Linux (WSL2)** trên GPU RTX 16GB, trong khi vẫn giữ được sự **tiện lợi khi kết nối Mic và Telemetry (COM Port) của Windows**. 

Dưới đây là các bước setup chuẩn chỉ nhất:

---

## PHẦN 1: CÀI ĐẶT WSL2 VÀ GPU DRIVER TRÊN WINDOWS SERVER

**Lưu ý quan trọng:** Bạn KHÔNG cần (và không nên) cài driver NVIDIA bên trong Ubuntu/WSL2. Bạn chỉ cần cài NVIDIA Driver trên bản Windows Server gốc. WSL2 sẽ tự động nhận diện phần cứng đồ họa thông qua Windows.

1. **Cài đặt WSL2:**
   - Mở **PowerShell (Run as Administrator)** trên Windows.
   - Chạy lệnh:
     ```powershell
     wsl --install -d Ubuntu-22.04
     ```
   - Khởi động lại máy chủ Windows nếu được yêu cầu.
   - Sau khi khởi động lại, mở Ubuntu từ Start Menu, thiết lập Username và Password.

2. **Xác nhận GPU đã nhận trong WSL2:**
   - Trong terminal của Ubuntu, gõ lệnh:
     ```bash
     nvidia-smi
     ```
   - Nếu bạn thấy bảng thông số của GPU hiện ra, chúc mừng, WSL2 đã thông với GPU!

---

## PHẦN 2: CHẠY EDGE SERVER (AI) BÊN TRONG WSL2 (UBUNTU)

Mục đích: Chạy `Faster-Whisper` và `Llama 3` trên Linux để cài đặt `bitsandbytes` và `vLLM` mượt mà.

1. **Truy cập source code từ WSL2:**
   - WSL2 tự động mount các ổ đĩa của Windows. Thư mục code của bạn ở ổ `D:\` sẽ nằm tại đường dẫn: `/mnt/d/paraline-msagent`.
   - Trong terminal Ubuntu, chạy lệnh:
     ```bash
     cd /mnt/d/paraline-msagent
     ```

2. **Cài đặt môi trường Python (Bên trong Ubuntu):**
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv ffmpeg -y
   
   # Tạo môi trường ảo
   python3 -m venv venv_linux
   source venv_linux/bin/activate
   
   # Cài PyTorch chuẩn CUDA
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   
   # Cài các thư viện AI nặng (Sẽ không bị lỗi build C++ như trên Windows)
   pip install bitsandbytes faster-whisper transformers accelerate
   pip install fastapi uvicorn websockets
   ```

3. **Khởi động AI Server:**
   ```bash
   uvicorn services.api-gateway.main:app --host 0.0.0.0 --port 8000
   ```
   - *Lúc này, server AI đang lắng nghe ở `localhost:8000` bên trong Linux. Tin vui là Windows 10/11/Server tự động "thông chốt" mạng `localhost` giữa Windows và WSL2.*

---

## PHẦN 3: CHẠY GCS CLIENT BÊN TRÊN WINDOWS (NATIVE)

Mục đích: Thu âm từ Micro máy tính và gửi lệnh bay qua cắm USB Telemetry (COM Port) - việc này Windows làm tốt hơn WSL2 rất nhiều.

1. **Xác định cổng Telemetry:**
   - Cắm Anten Telemetry (SiK Radio) vào cổng USB của PC.
   - Mở **Device Manager (Windows)** > mục *Ports (COM & LPT)*. Bạn sẽ thấy thiết bị tên kiểu *USB Serial Port (COM3)*. Ghi nhớ tên cổng này (ví dụ `COM3`).

2. **Cài đặt môi trường Client (Bên trên Windows CMD/PowerShell):**
   - Mở cửa sổ **PowerShell** hoặc **Command Prompt** bình thường của Windows.
   - Di chuyển tới thư mục dự án: `cd D:\paraline-msagent`
   - Cài đặt thư viện vận hành nhẹ:
     ```powershell
     pip install pyaudio dronekit websockets requests
     ```
   - *(Lưu ý: Môi trường pip này của Windows độc lập hoàn toàn với pip trong Ubuntu bên trên).*

3. **Khởi động GCS Client:**
   - Chạy lệnh sau (giả sử cổng của bạn là `COM3`):
     ```powershell
     python scripts\gcs_direct_client.py --server ws://localhost:8000/ws/audio --uav COM3
     ```

---

## 🎯 TỔNG KẾT LUỒNG HOẠT ĐỘNG (WORKFLOW)

Khi mọi thứ đã chạy, hệ thống sẽ phối hợp hoàn hảo như sau:
1. Bạn nói *"Cất cánh lên 10 mét"* vào Micro của máy tính Windows.
2. `gcs_direct_client.py` (Windows) bắt đoạn âm thanh, gửi nó vào URL `ws://localhost:8000/ws/audio`.
3. Gói tin tự động xuyên qua màn chắn mạng, đi vào môi trường Ubuntu (WSL2).
4. FastAPI (Ubuntu) nhận audio, ném cho GPU 16GB xử lý Whisper siêu tốc, sau đó đưa chữ "Cất cánh lên 10 mét" qua `Llama 3` để xuất ra Intent `TAKEOFF`.
5. Kết quả (JSON) trả ngược về cho `gcs_direct_client.py` bên Windows.
6. Script Windows lập tức gọi `dronekit`, bắn tín hiệu MAVLink ra cổng `COM3`.
7. Ăng-ten Telemetry phát sóng, UAV nhận lệnh bay lên không trung!

Thiết kế này hoàn hảo không có độ trễ do mạng, không bị lỗi phần cứng USB của Linux, và GPU được xả hết công suất nhờ môi trường Ubuntu ảo.
