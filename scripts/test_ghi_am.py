import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write

fs = 16000  # sample rate chuẩn cho AI
seconds = 5

print(f"Recording {seconds} seconds...")
audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
sd.wait()

# Chuyển đổi từ float32 sang int16
audio_int16 = (audio * 32767).astype(np.int16)

write("output.wav", fs, audio_int16)
print("Done! Saved as output.wav (PCM Int16)")