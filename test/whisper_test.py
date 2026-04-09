import time
import requests
from client.audio_router.audio_manager import AudioManager

# 1. Định nghĩa hàm Callback để gửi lên Whisper
import requests
import json
import time

# Cấu hình URL của các microservices
ASR_SERVICE_URL = "http://localhost:8001/transcribe" # Thay bằng port ASR thực tế của bạn
TRANSLATION_SERVICE_URL = "http://localhost:8002/translate"

def on_audio_ready(b64_audio: str):
    """
    Hàm này được gọi tự động mỗi khi VAD cắt xong 1 câu.
    """
    print("\n" + "="*50)
    print(f"🎙️ Nhận được 1 câu audio mới ({len(b64_audio)} bytes)")
    
    # ---------------------------------------------------------
    # BƯỚC 1: Gửi Audio cho ASR (Whisper / Qwen) để lấy Text
    # ---------------------------------------------------------
    t0 = time.time()
    try:
        asr_response = requests.post(
            ASR_SERVICE_URL,
            json={"audio_b64": b64_audio, "language": "ja"}, # Giả sử đang nghe tiếng Nhật
            timeout=5.0
        )
        asr_response.raise_for_status()
        
        # Lấy text nhận dạng được
        original_text = asr_response.json().get("text", "").strip()
        print(f"📝 ASR [{time.time() - t0:.2f}s]: {original_text}")
        
    except Exception as e:
        print(f"❌ Lỗi ASR: {e}")
        return

    # Nếu không nghe thấy gì có nghĩa (chỉ là tiếng ồn rác), thì bỏ qua dịch
    if not original_text:
        return

    # ---------------------------------------------------------
    # BƯỚC 2: Gửi Text cho NLLB để Dịch
    # ---------------------------------------------------------
    t1 = time.time()
    try:
        trans_payload = {
            "text": original_text,
            "src_lang": "jpn_Jpan", # Mã ngôn ngữ nguồn của NLLB (VD: jpn_Jpan, eng_Latn)
            "tgt_lang": "vie_Latn"  # Mã ngôn ngữ đích (Tiếng Việt)
        }
        
        trans_response = requests.post(
            TRANSLATION_SERVICE_URL,
            json=trans_payload,
            timeout=5.0
        )
        trans_response.raise_for_status()
        
        # Lấy text đã dịch
        translated_text = trans_response.json().get("translated_text", "")
        print(f"🌐 NLLB [{time.time() - t1:.2f}s]: {translated_text}")
        
    except Exception as e:
        print(f"❌ Lỗi Translation: {e}")
        return

    print("="*50 + "\n")

# --- Khởi động luồng Audio ---
# manager = InboundAudioManager()
# manager.start(callback=on_audio_ready)
# 2. Khởi động toàn bộ hệ thống
if __name__ == "__main__":
    print("🚀 Khởi động Paraline Audio System...")
    
    # Khởi tạo Manager
    audio_manager = AudioManager()
    
    try:
        # Bắn hàm Whisper vào làm callback
        audio_manager.start(inbound_cb=on_audio_ready)
        
        print("\n✅ HỆ THỐNG ĐÃ SẴN SÀNG!")
        print("🎤 Hãy bật một đoạn video hoặc nói vào luồng Virtual Cable để test.")
        print("Ấn Ctrl+C để thoát...\n")
        
        # Giữ cho main thread sống để background threads (VAD, âm thanh) chạy
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Nhận lệnh tắt từ người dùng...")
    finally:
        audio_manager.stop()
        print("👋 Đã tắt hệ thống an toàn.")