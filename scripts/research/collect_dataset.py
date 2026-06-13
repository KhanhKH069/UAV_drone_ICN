import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import os
import time

def record_audio(filename, duration, fs=16000):
    print(f"Bắt đầu ghi âm trong {duration} giây...")
    # Ghi âm mono, 16kHz
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()  # Chờ đến khi ghi âm xong
    wav.write(filename, fs, recording)
    print(f"Đã lưu: {filename}")

if __name__ == "__main__":
    output_dir = "dataset/wav_vi"
    os.makedirs(output_dir, exist_ok=True)

    print("=== Công cụ thu thập Dataset Lệnh Thoại Tiếng Việt ===")
    print("Nhấn Enter để bắt đầu thu âm một mẫu, gõ 'q' để thoát.")
    
    sample_id = 1
    while True:
        cmd = input(f"Chuẩn bị thu mẫu #{sample_id}. Nhấn Enter để bắt đầu (hoặc 'q' để thoát): ")
        if cmd.lower() == 'q':
            break
            
        intent_label = input("Nhập nhãn intent (vd: take_off, move_forward): ").strip()
        if not intent_label:
            intent_label = "unknown"

        filename = os.path.join(output_dir, f"{intent_label}_{sample_id}.wav")
        record_audio(filename, duration=3.0) # Thu mặc định 3 giây mỗi lệnh
        sample_id += 1
