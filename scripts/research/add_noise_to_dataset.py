import os
import glob
import soundfile as sf
import numpy as np
import argparse

def calculate_rms(signal):
    """Tính toán RMS của một mảng tín hiệu âm thanh."""
    return np.sqrt(np.mean(signal**2))

def add_noise(clean_signal, noise_signal, target_snr_db):
    """
    Trộn tiếng ồn vào tín hiệu sạch theo tỷ lệ Signal-to-Noise (SNR).
    """
    rmsclean = calculate_rms(clean_signal)
    rmsnoise = calculate_rms(noise_signal)
    
    if rmsclean == 0 or rmsnoise == 0:
        return clean_signal
        
    snr_linear = 10 ** (target_snr_db / 20)
    noise_factor = rmsclean / (rmsnoise * snr_linear)
    
    noisy_signal = clean_signal + noise_signal * noise_factor
    
    if np.max(np.abs(noisy_signal)) > 1.0:
        noisy_signal = noisy_signal / np.max(np.abs(noisy_signal))
        
    return noisy_signal

def main():
    parser = argparse.ArgumentParser(description="Add background UAV noise to clean audio dataset at specific SNRs.")
    parser.add_argument("--clean_dir", type=str, required=True, help="Path to clean audio directory")
    parser.add_argument("--noise_file", type=str, required=True, help="Path to the noise audio file (e.g., UAV propeller noise)")
    parser.add_argument("--out_dir", type=str, required=True, help="Path to save noisy audio")
    parser.add_argument("--snr", type=int, nargs='+', default=[20, 10, 5, 0], help="List of SNRs in dB (e.g., --snr 20 10 5)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    
    print(f"Loading noise file from: {args.noise_file}")
    noise, sr_noise = sf.read(args.noise_file, dtype='float32')
    if noise.ndim > 1:
        noise = noise.mean(axis=1)
    
    clean_files = glob.glob(os.path.join(args.clean_dir, "*.wav"))
    print(f"Found {len(clean_files)} clean audio files.")

    for snr in args.snr:
        snr_dir = os.path.join(args.out_dir, f"snr_{snr}db")
        os.makedirs(snr_dir, exist_ok=True)
        print(f"Processing SNR: {snr}dB...")
        
        for f in clean_files:
            clean_audio, sr_clean = sf.read(f, dtype='float32')
            if clean_audio.ndim > 1:
                clean_audio = clean_audio.mean(axis=1)
            
            if len(noise) < len(clean_audio):
                repeats = int(np.ceil(len(clean_audio) / len(noise)))
                current_noise = np.tile(noise, repeats)[:len(clean_audio)]
            else:
                start_idx = np.random.randint(0, len(noise) - len(clean_audio))
                current_noise = noise[start_idx:start_idx + len(clean_audio)]
                
            noisy_audio = add_noise(clean_audio, current_noise, snr)
            
            out_file = os.path.join(snr_dir, os.path.basename(f))
            sf.write(out_file, noisy_audio, 16000)
            
    print("Done! Noisy datasets created.")

if __name__ == "__main__":
    main()
