# test_silero_debug.py
import numpy as np
import soundfile as sf
import onnxruntime as ort

MODEL_PATH = "/mnt/data/Khanh/KhoaHocMayTinh/project_msi/paraline-msagent/client/audio_router/silero_vad.onnx"
WAV_PATH = "/mnt/data/Khanh/KhoaHocMayTinh/project_msi/paraline-msagent/input.wav"
SAMPLE_RATE = 16000

# Load audio
audio, sr = sf.read(WAV_PATH)
if len(audio.shape) > 1:
    audio = np.mean(audio, axis=1)

if sr != SAMPLE_RATE:
    import librosa
    audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

audio = audio.astype(np.float32)

print(f"Audio shape: {audio.shape}")
print(f"Audio range: [{audio.min():.3f}, {audio.max():.3f}]")
print(f"Audio RMS: {np.sqrt(np.mean(audio**2)):.5f}")

# Load model và inspect
session = ort.InferenceSession(MODEL_PATH)

# Lấy thông tin input/output
print("\n=== Model Info ===")
for input_meta in session.get_inputs():
    print(f"Input: {input_meta.name}, shape: {input_meta.shape}, type: {input_meta.type}")

for output_meta in session.get_outputs():
    print(f"Output: {output_meta.name}, shape: {output_meta.shape}, type: {output_meta.type}")

# Test với audio normalization
print("\n=== Testing different normalizations ===")
window_size = 512
state = np.zeros((2, 1, 128), dtype=np.float32)

for norm_factor in [1.0, 0.5, 0.2, 0.1, 0.05]:
    audio_norm = audio * norm_factor
    state = np.zeros((2, 1, 128), dtype=np.float32)
    probs = []
    
    for i in range(0, min(len(audio_norm), 16000), window_size):  # Chỉ test 1s đầu
        chunk = audio_norm[i:i+window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        
        inp = {
            "input": chunk.reshape(1, -1),
            "state": state,
            "sr": np.array(SAMPLE_RATE, dtype=np.int64),
        }
        out, state = session.run(None, inp)
        probs.append(float(out[0][0]))
    
    avg_prob = np.mean(probs)
    max_prob = np.max(probs)
    print(f"norm={norm_factor:.2f}: avg prob={avg_prob:.5f}, max prob={max_prob:.5f}")

# Test với chunk đầu tiên với nhiều gain khác nhau
print("\n=== Testing with different gains ===")
first_chunk = audio[:window_size]
if len(first_chunk) < window_size:
    first_chunk = np.pad(first_chunk, (0, window_size - len(first_chunk)))

for gain in [1.0, 2.0, 5.0, 10.0, 20.0]:
    chunk = first_chunk * gain
    chunk = np.clip(chunk, -1.0, 1.0)
    state = np.zeros((2, 1, 128), dtype=np.float32)
    
    inp = {
        "input": chunk.reshape(1, -1),
        "state": state,
        "sr": np.array(SAMPLE_RATE, dtype=np.int64),
    }
    out, _ = session.run(None, inp)
    prob = float(out[0][0])
    print(f"gain={gain:.1f}: prob={prob:.5f}, chunk RMS={np.sqrt(np.mean(chunk**2)):.5f}")