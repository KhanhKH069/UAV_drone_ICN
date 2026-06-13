@echo off
echo ==============================================
echo 🛸 PARALINE MS-AGENT - START GCS (SITL MODE)
echo ==============================================
echo.
echo Đang kết nối GCS Engine tới máy bay ảo SITL qua cổng TCP 5760...
echo.

python scripts\gcs\gcs_main.py --port tcp:127.0.0.1:5760

pause
