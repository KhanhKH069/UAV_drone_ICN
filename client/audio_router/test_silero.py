# test_silero_torch.py
import numpy as np
import soundfile as sf
import torch
import torchaudio

# ===== CONFIG =====
SAMPLE_RATE = 16000
THRESHOLD = 0.5

# ===== LOAD AUDIO =====
audio, sr = sf.read("/mnt/data/Khanh/KhoaHocMayTinh/project_msi/paraline-msagent/input.wav")

print("==== DEBUG ====")
print("sr:", sr)
print("max:", np.max(audio))
print("min:", np.min(audio))
print("mean abs:", np.mean(np.abs(audio)))
print("================")

# convert mono
if len(audio.shape) > 1:
    audio = np.mean(audio, axis=1)

# resample
if sr != SAMPLE_RATE:
    import librosa
    audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

# ===== LOAD SILERO TORCH =====
try:
    import torch
    import torchaudio
    
    # Tải model từ torch.hub
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False,
        verbose=True
    )
    
    # Lấy functions
    (get_speech_timestamps, 
     save_audio, 
     read_audio, 
     VADIterator, 
     collect_chunks) = utils
    
    # Chuyển audio sang tensor
    audio_tensor = torch.from_numpy(audio).float().unsqueeze(0)
    
    # Get speech timestamps
    speech_timestamps = get_speech_timestamps(
        audio_tensor, 
        model,
        sampling_rate=SAMPLE_RATE,
        threshold=THRESHOLD
    )
    
    print("\n=== Speech segments ===")
    for seg in speech_timestamps:
        start = seg['start'] / SAMPLE_RATE
        end = seg['end'] / SAMPLE_RATE
        print(f"{start:.2f}s → {end:.2f}s")
    
    if len(speech_timestamps) == 0:
        print("No speech detected!")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()