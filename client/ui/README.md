# client/ui — UI Layer của Paraline MSAgent

Đây là tầng giao diện người dùng (GUI) của ứng dụng Paraline MSAgent, được xây dựng bằng **PyQt6**.

---

## 📁 Cấu trúc thư mục

```
client/ui/
├── main_app.py         # Entry point — khởi động QApplication
├── main_window.py      # Cửa sổ chính, điều phối toàn bộ session
├── ui_test.py          # Cửa sổ (chế độ test) với đầy đủ các Frame
├── config.py           # Cấu hình toàn cục (server URL, API key, CSS)
├── styles.py           # Các hằng số style bổ sung
├── meeting_minutes.py  # Màn hình Biên bản cuộc họp (Meeting Minutes)
└── components/         # Các widget tái sử dụng (xem bên dưới)
```

---

## 🧩 Các Component (components/)

| File | Mô tả |
|---|---|
| `frame_trans.py` | **Frame Dịch thuật** — hiển thị bong bóng văn bản Inbound/Outbound |
| `frame_chat.py` | **Frame Chat** — giao diện trò chuyện với AI |
| `frame_minutes.py` | **Frame Biên bản** — hiển thị Meeting Minutes |
| `image_panel.py` | **Panel Slide** — hiển thị ảnh chụp màn hình slide |
| `splash_screen.py` | **Splash Screen** — màn hình chờ tải ứng dụng |
| `pulse_dot.py` | **Pulse Dot** — chấm xanh nhấp nháy báo hiệu đang thu âm |
| `helpers.py` | Các hàm tiện ích dùng chung cho component |

---

## 🚀 Cách chạy

### Chạy ứng dụng chính
```bash
python -m client.ui.main_app
```

### Chạy ở chế độ test UI (không cần backend)
```bash
python -m client.ui.ui_test
```

---

## 🏗️ Kiến trúc

```
main_app.py
    └── main_window.py (ParalineMainWindow)
            ├── FrameTrans       — Dịch thuật Inbound/Outbound
            ├── FrameChat        — Chat AI
            ├── FrameMinutes     — Biên bản họp
            └── ImagePanel       — Slide từ presentation
```

Luồng dữ liệu:
1.  `AudioManager` thu âm từ phần cứng và gọi callback.
2.  `WebSocket Client` gửi chunk âm thanh lên server và nhận kết quả.
3.  `MainWindow` nhận kết quả qua Qt Signal và đẩy vào các Frame tương ứng.

---

## ⚙️ Cấu hình

Các biến môi trường trong file `.env` ảnh hưởng đến UI:

| Biến | Mô tả | Mặc định |
|---|---|---|
| `PARALINE_SERVER_WS` | Địa chỉ WebSocket server | `ws://127.0.0.1:8056` |
| `PARALINE_SERVER_REST` | Địa chỉ REST API server | `http://127.0.0.1:8056` |
| `CLIENT_API_KEY` | API key xác thực | `paraline_client_secret_key_local` |
| `DEBUG_AUDIO` | Lưu file WAV debug vào `debug_audio/` | `0` |
