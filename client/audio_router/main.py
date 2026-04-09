import time
import logging
import base64
import io
import os
import wave
import numpy as np
from audio_manager import AudioManager  # Đảm bảo import đúng tên file của bạn
from dotenv import find_dotenv
import os

print("👉 Đường dẫn file .env đang được đọc:", find_dotenv())
print("👉 Giá trị AUDIO_CHUNK_MS thực tế lấy được:", os.environ.get("AUDIO_CHUNK_MS"))
# Cấu hình logging để nhìn thấy hoạt động của luồng
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TestApp")

# Config: Bật/tắt playback test
ENABLE_TEST_PLAYBACK = os.getenv("ENABLE_TEST_PLAYBACK", "0") == "1"

def mock_inbound_handler(b64_data: str):
    """Giả lập hàm nhận dữ liệu từ loa (Teams/Meet) gửi lên Server"""
    logger.info(f"🎤 [INBOUND VAD] Đã ngắt câu từ Virtual Cable. Gửi Base64 dài: {len(b64_data)} chars")

def mock_outbound_handler(b64_data: str):
    """Giả lập hàm nhận dữ liệu từ Micro thật gửi lên Server"""
    logger.info(f"🎙️ [OUTBOUND VAD] Đã ngắt câu từ Micro. Gửi Base64 dài: {len(b64_data)} chars")

def generate_test_wav_b64() -> str:
    """Tạo một file WAV (tiếng Beep 440Hz) trên RAM và chuyển thành Base64 để test luồng Playback"""
    sample_rate = 16000
    duration = 0.5  # Bíp dài nửa giây
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Tạo sóng sine (nốt A4) và ép về PCM 16-bit
    audio_data = (0.3 * 32767 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)

    # Đóng gói thành chuẩn file WAV
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    
    return base64.b64encode(wav_io.getvalue()).decode('utf-8')

if __name__ == "__main__":
    manager = AudioManager()
    
    logger.info("🚀 Khởi động Audio Manager...")
    manager.start(inbound_cb=mock_inbound_handler)


    print("👉 Đường dẫn file .env đang được đọc:", find_dotenv())
    print("👉 Giá trị AUDIO_CHUNK_MS thực tế lấy được:", os.environ.get("AUDIO_CHUNK_MS"))
        

    logger.info("✅ Đang chạy... Hãy thử nói vào Micro và dừng lại để test ngắt câu!")
    if ENABLE_TEST_PLAYBACK:
        logger.info("🔊 Hệ thống sẽ phát một tiếng Beep (giả lập TTS) mỗi 5 giây để test loa.")
    else:
        logger.info("🔇 TEST PLAYBACK TẮT - Không phát tiếng Beep (đặt ENABLE_TEST_PLAYBACK=1 để bật)")

    try:
        while True:
            time.sleep(5)
            # Test luồng Playback: Đẩy file WAV base64 giả lập vào hàng đợi phát
            if ENABLE_TEST_PLAYBACK:
                logger.info("▶️ [PLAYBACK] Đang đẩy tiếng Beep giả lập TTS ra loa...")
                test_wav_b64 = generate_test_wav_b64()
                manager.play_tts(test_wav_b64)
            
    except KeyboardInterrupt:
        logger.info("🛑 Đang tắt hệ thống (Ctrl+C)...")
        manager.stop()
        logger.info("👋 Đã thoát an toàn.")