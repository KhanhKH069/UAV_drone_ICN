# Hướng dẫn toàn bộ cách sử dụng Giả lập Drone (ArduPilot SITL)

Do bạn chưa có phần cứng thực tế (Raspberry Pi, Pixhawk, Frame, Motor), việc sử dụng phần mềm giả lập **SITL (Software In The Loop)** là cách tốt nhất để kiểm tra độ chính xác của toàn bộ chuỗi hệ thống: *từ việc nhận diện giọng nói -> dịch thuật -> phân tích ý định -> điều khiển tín hiệu MAVLink*. 

Mọi tín hiệu điều khiển sinh ra từ code Python của bạn sẽ được truyền vào một chiếc Drone ảo có cơ chế vật lý giống y hệt ngoài đời thật.

Dưới đây là các bước thiết lập từ A-Z dành riêng cho hệ điều hành **Windows**.

---

## BƯỚC 1: Cài đặt Mission Planner và Drone ảo (SITL)

Mission Planner là phần mềm trạm điều khiển mặt đất (Ground Control Station) phổ biến nhất của hệ sinh thái ArduPilot. Nó được tích hợp sẵn công cụ giả lập.

1. Tải và cài đặt **Mission Planner (Latest)** từ trang chủ: 
   👉 [Tải Mission Planner](https://firmware.ardupilot.org/Tools/MissionPlanner/MissionPlanner-latest.msi)
2. Mở phần mềm Mission Planner.
3. Trên thanh menu trên cùng, bấm vào tab **SIMULATION** (Giả lập).
4. Bạn sẽ thấy biểu tượng các loại máy bay. Nhấp vào biểu tượng **Multirotor** (Máy bay 4 cánh quạt - Quadcopter).
5. Mission Planner sẽ tự động tải các mã nguồn giả lập (SITL) về (có thể mất vài phút).
6. Khi có thông báo hiện lên hỏi về việc chạy mã độc hoặc firewall, hãy chọn **Allow access / Cho phép**.
7. Khi màn hình hiện ra một **bản đồ (Map)** với một chiếc Drone nằm ở vị trí nào đó (thường là tại Mỹ hoặc Úc), tức là Drone ảo đã được khởi động thành công và đang lắng nghe lệnh điều khiển tại địa chỉ: `tcp:127.0.0.1:5760`.

> [!NOTE]
> Mặc dù Drone ảo đang chạy ngầm, bạn có thể xem các thông số về độ cao (Alt), hướng (Yaw), và tốc độ (Speed) trên bảng HUD (bên trái màn hình Mission Planner).

---

## BƯỚC 2: Khởi động Server AI (Backend)

Server AI là bộ não xử lý giọng nói, chạy trên Docker. Bạn cần khởi động nó để nó phân tích giọng nói trước khi gửi lệnh về cho client.

1. Bật phần mềm **Docker Desktop** trên Windows của bạn.
2. Mở Terminal (Command Prompt hoặc PowerShell).
3. Di chuyển vào thư mục dự án `UAV_drone_ICN`:
   ```powershell
   cd d:\UAV_drone_ICN
   ```
4. Khởi chạy cụm Microservices bằng docker-compose:
   ```powershell
   docker-compose --env-file .env.drone up -d
   ```
5. Đảm bảo toàn bộ các services (gateway, whisper, nllb, ollama) đã báo trạng thái `Up` hoặc `Running`.

---

## BƯỚC 3: Kết nối Python Script với Drone Ảo

Bây giờ bạn sẽ chạy file Client (code đáng lẽ sẽ nằm trên Raspberry Pi) nhưng chạy thẳng trên Windows của bạn. Máy tính sẽ đóng vai trò vừa là Pi, vừa là bộ điều khiển.

1. Mở một cửa sổ Terminal mới, vẫn đứng ở thư mục dự án `UAV_drone_ICN`.
2. Khởi chạy file client, nhưng thay vì chỉ định cổng UART thật, chúng ta trỏ tới cổng TCP của bộ giả lập:
   ```powershell
   python scripts/drone_edge_client.py --connect tcp:127.0.0.1:5760
   ```
3. Nếu mọi thứ thành công, Terminal sẽ hiển thị:
   ```text
   [INFO] Đang kết nối tới UAV tại tcp:127.0.0.1:5760...
   [INFO] ✅ Kết nối UAV thành công!
   [INFO] ✅ Edge Server Connected! Bắt đầu nghe lệnh...
   ```

---

## BƯỚC 4: Ra lệnh bằng giọng nói và theo dõi

Bạn có thể bắt đầu nói tiếng Việt vào microphone của máy tính. Hãy thử theo thứ tự sau để xem Drone ảo thực hiện:

### Kịch bản 1: Cất cánh và hạ cánh an toàn
1. **Bạn nói:** "Máy bay, chuẩn bị cất cánh."
   - **Terminal:** Sẽ hiện log ghi nhận lệnh `take_off`.
   - **Mission Planner:** Bạn sẽ nghe thấy tiếng loa thông báo "Arming Motors", cánh quạt sẽ quay và Drone ảo bắt đầu nâng độ cao lên 3 mét. (Chỉ số Alt trên bảng HUD sẽ nhảy lên 3).
2. **Bạn nói:** "Hạ cánh xuống đất ngay."
   - **Terminal:** Hiện intent `land`.
   - **Mission Planner:** Drone từ từ giảm độ cao (Alt giảm về 0) và ngắt động cơ (Disarmed).

### Kịch bản 2: Di chuyển các hướng
*(Lưu ý: Bạn phải ra lệnh cất cánh trước khi di chuyển ngang)*
1. **Bạn nói:** "Bay lên cao nhé."
2. **Bạn nói:** "Bay tiến lên phía trước khoảng 2 mét."
   - **Mission Planner:** Drone nghiêng về phía trước, tăng tốc độ và di chuyển trên bản đồ.
3. **Bạn nói:** "Xoay sang trái 90 độ."
   - **Mission Planner:** Trên bảng HUD, la bàn sẽ quay ngang sang trái một góc 90 độ.
4. **Bạn nói:** "Đứng im tại chỗ."
   - **Terminal:** Hiện intent `stop` / `hover`.
   - **Mission Planner:** Drone chuyển sang chế độ LOITER, phanh lại và giữ nguyên vị trí, không trôi đi nữa.
5. **Bạn nói:** "Quay về nhà đi."
   - **Terminal:** Hiện intent `return_home`.
   - **Mission Planner:** Drone tự bay về điểm ban đầu lúc xuất phát (Return To Launch - RTL) và tự hạ cánh.

---

> [!TIP]
> **Khắc phục sự cố thường gặp:**
> - **Lỗi không kết nối được MAVLink (Connection Refused):** Đảm bảo Mission Planner đang ở tab Simulation và đã chạy Multirotor. Bạn không thể kết nối nếu Simulation chưa bắt đầu.
> - **Drone không chịu cất cánh (Pre-arm Check Failed):** Trong môi trường giả lập, đôi lúc Drone ảo báo la bàn (compass) chưa cân bằng. Vào mục Config/Tuning của Mission Planner tắt "Arming Checks" đi là được.
> - **Nói nhưng Terminal không hiện gì:** Hãy kiểm tra lại microphone trên máy tính (có thể Windows chưa cấp quyền cho Python sử dụng micro).
