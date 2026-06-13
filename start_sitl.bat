@echo off
echo ==============================================
echo 🛸 PARALINE MS-AGENT - START SITL SIMULATOR
echo ==============================================
echo.
echo Kiểm tra và cài đặt thư viện dronekit-sitl...
pip install dronekit-sitl -q

echo.
echo Khởi động máy bay ảo (SITL Copter)...
echo Lưu ý: Máy bay ảo sẽ lắng nghe kết nối tại tcp:127.0.0.1:5760
echo Giữ nguyên cửa sổ này trong suốt quá trình bay.
echo.
dronekit-sitl copter
pause
