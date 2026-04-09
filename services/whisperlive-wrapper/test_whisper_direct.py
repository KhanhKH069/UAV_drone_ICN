import sounddevice as sd
import numpy as np
import base64
import requests
import wave
import time
import argparse

def send_to_whisper(audio_float32, chunk_index=1):
    print(f"\n🚀 Đang gửi Chunk {chunk_index} ({len(audio_float32)/16000:.2f}s) cho Whisper (Cổng 8001)...")
    b64_data = base64.b64encode(audio_float32.tobytes()).decode('utf-8')
    url = "http://127.0.0.1:8001/transcribe"
    payload = {
        "audio_b64": b64_data,
        "language": "en",  # Có thể đổi thành "vi", "ja", "auto"
        "vad_filter": True
    }
    
    t0 = time.time()
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        latency = (time.time() - t0) * 1000
        
        print("*"*50)
        print(f"🎯 KẾT QUẢ TỪ FASTER WHISPER (Chunk {chunk_index}):")
        print(f"- Ngôn ngữ nhận diện : {result.get('language')}")
        print(f"- Văn bản (Text)     : {result.get('text')}")
        print(f"- Thời gian xử lý    : {latency:.0f} ms (Bao gồm mạng)")
        print("*"*50)
        
    except requests.exceptions.ConnectionError:
        print("❌ LỖI KẾT NỐI: Không thể gọi API ở cổng 8001! Hãy chắc chắn server WhisperLive đang chạy.")
    except Exception as e:
        print(f"❌ LỖI VĂNG (Chunk {chunk_index}): {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Chi tiết API trả về: {response.text}")


def test_record_and_transcribe():
    fs = 16000
    duration = 5  # seconds
    
    print("="*50)
    print("🎤 BẮT ĐẦU GHI ÂM (5 GIÂY)...")
    print("Hãy mở âm thanh hoặc tự nói vào Mic!")
    print("="*50)
    
    # Capture audio from default input
    try:
        myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()  # Wait until recording is finished
    except Exception as e:
        print(f"Lỗi khi ghi âm: {e}")
        return

    print("\n✅ Đã ghi âm xong! Đang lưu lại file...")
    
    # Save to WAV to verify locally
    wav_filename = 'test_capture.wav'
    with wave.open(wav_filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 2 bytes for int16
        wf.setframerate(fs)
        wf.writeframes(myrecording.tobytes())
        
    print(f"💾 File ghi âm đã được lưu tại: {wav_filename}")
    
    # Chuyển từ int16 sang float32
    audio_float32 = (myrecording.flatten().astype(np.float32) / 32768.0)
    send_to_whisper(audio_float32, chunk_index=1)


def chunk_and_transcribe_wav(wav_filename):
    """
    Đọc từ file WAV, tìm những đoạn im lặng để cắt thành từng chunk riêng biệt 
    và chuyển lần lượt đến Whisper API thay vì gửi toàn bộ.
    """
    print(f"Bắt đầu đọc file: {wav_filename}")
    try:
        with wave.open(wav_filename, 'rb') as wf:
            fs = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            
            if sampwidth != 2:
                print("Lỗi: Mã nguồn này chỉ hỗ trợ file WAV 16-bit PCM.")
                return
            if fs != 16000:
                print(f"Cảnh báo: Sample rate file là {fs}Hz. Whisper hoạt động tốt nhất ở 16000Hz.")
                
            audio_data = wf.readframes(n_frames)
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            
            if n_channels > 1:
                # Trộn 2 channel (stereo) thành mono nếu cần
                audio_np = audio_np.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
    except FileNotFoundError:
        print(f"❌ Lỗi: Không tìm thấy file tên '{wav_filename}'")
        return

    # -------- THÔNG SỐ VAD (Voice Activity Detection) BẰNG NĂNG LƯỢNG --------
    frame_duration_ms = 30
    frame_size = int(fs * frame_duration_ms / 1000)
    
    # 1. Ngưỡng năng lượng để coi là âm thanh tiếng người nói 
    # (Nếu file ồn quá, hãy tăng số này lên, VD: 1000-2000)
    ENERGY_THRESHOLD = 500  
    
    # 2. Ngưỡng thời gian im lặng tối đa để tiến hành cắt lát (chunk)
    # 500ms im lặng sẽ cắt
    max_silence_frames = int(500 / frame_duration_ms)
    # --------------------------------------------------------------------------
    
    current_chunk = []
    silence_frames = 0
    in_speech = False
    chunk_index = 1
    
    print("⏳ Đang phân tích âm thanh, dò tìm khoảng lặng để cắt chunk...\n")
    
    for i in range(0, len(audio_np), frame_size):
        frame = audio_np[i:i + frame_size]
        if len(frame) < frame_size:
            current_chunk.append(frame) # append the remaining small piece
            break
            
        energy = np.sqrt(np.mean(frame.astype(np.float64)**2))
        is_speech = energy > ENERGY_THRESHOLD
        
        if is_speech:
            if not in_speech:
                in_speech = True  # Bắt đầu phát hiện lời nói
            silence_frames = 0
            current_chunk.append(frame)
        else:
            if in_speech:
                silence_frames += 1
                current_chunk.append(frame)
                
                # NẾU đã im lặng quá lâu -> Tiến hành Cắt chunk hiện tại
                if silence_frames > max_silence_frames:
                    in_speech = False
                    
                    chunk_audio = np.concatenate(current_chunk)
                    
                    # Cần Convert qua float32 để API hiểu
                    audio_float32 = (chunk_audio.astype(np.float32) / 32768.0)
                    
                    # Dịch đoạn cắt này luôn (Nối tiếp chờ kết quả)
                    send_to_whisper(audio_float32, chunk_index)
                    chunk_index += 1
                    
                    # Reset biến để hứng chuỗi mới
                    current_chunk = []
                    
    # Lỡ file kết thúc đột ngột nhưng vẫn còn âm thanh đang nói dở thì gửi nốt
    if len(current_chunk) > 0:
        chunk_audio = np.concatenate(current_chunk)
        # Bỏ qua nếu thời gian quá ngắn (VD dưới 0.2s)
        if len(chunk_audio) > fs * 0.2:
            audio_float32 = (chunk_audio.astype(np.float32) / 32768.0)
            send_to_whisper(audio_float32, chunk_index)
            
    print("\n✅ Hoàn thành toàn bộ quá trình đọc file và dịch tuần tự!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test gửi audio cho Faster-Whisper API")
    parser.add_argument("--file", "-f", type=str, help="Đường dẫn đến file WAV đê đọc và cắt chunk (VD: audio.wav)")
    
    args = parser.parse_args()
    
    if args.file:
        # Chế độ 1: Đọc từ file và cắt đoạn im lặng
        chunk_and_transcribe_wav(args.file)
    else:
        # Chế độ 2: Chỉ ghi âm trực tiếp 5 giây rồi gửi
        test_record_and_transcribe()
