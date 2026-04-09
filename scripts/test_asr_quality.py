import os
import sys
import base64
import wave
import numpy as np
import requests

# URL của whisperlive-wrapper (đang chạy cổng 8001 trong docker-compose)
ASR_URL = "http://localhost:8001/transcribe"

def test_asr_with_wav(wav_path):
    if not os.path.exists(wav_path):
        print(f"❌ File không tồn tại: {wav_path}")
        return

    print(f"📁 Đang đọc: {wav_path}...")
    
    from scipy.io.wavfile import read as wav_read
    
    samplerate, data = wav_read(wav_path)
    
    # Chuyển đổi sang float32 nếu cần
    if data.dtype == np.int16:
        audio_f32 = data.astype(np.float32) / 32768.0
    elif data.dtype == np.float32:
        audio_f32 = data
    else:
        # Thường là int32 hoặc các dạng khác, đưa về float32
        audio_f32 = data.astype(np.float32) / np.max(np.abs(data))

    # Encode sang base64
    audio_b64 = base64.b64encode(audio_f32.tobytes()).decode('utf-8')

    payload = {
        "audio_b64": audio_b64,
        "language": "vie_Latn",  # Hoặc chỉ định "vie_Latn", "jpn_Jpan"...
        "sample_rate": samplerate
    }

    try:
        print(f"🚀 Đang gửi dữ liệu tới {ASR_URL} (ASR Backend)...")
        t0 = os.getloadavg()[0] # Giả lập đo lường đơn giản hơn
        resp = requests.post(ASR_URL, json=payload, timeout=60)
        
        if resp.status_code == 200:
            res = resp.json()
            print("\n" + "="*50)
            print(f"✅ KẾT QUẢ TỪ MODEL:")
            print(f"  - Văn bản: {res['text']}")
            print(f"  - Ngôn ngữ: {res['language']}")
            print(f"  - Độ trễ xử lý: {res['latency_ms']:.2f}ms")
            print("="*50)
        else:
            print(f"❌ Lỗi HTTP {resp.status_code}: {resp.text}")
            
    except Exception as e:
        print(f"❌ Lỗi kết nối tới ASR Backend: {e}")
        print("Mẹo: Hãy đảm bảo Docker đang chạy (`docker compose up -d`) và cổng 8001 đang mở.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Sử dụng: python scripts/test_asr_quality.py <đường_dẫn_file_wav>")
    else:
        # Nếu chưa có file WAV, bạn hãy dùng ghi âm máy tính hoặc lấy 1 file mẫu
        test_asr_with_wav(sys.argv[1])
