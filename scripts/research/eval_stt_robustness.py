"""
scripts/research/eval_stt_robustness.py
========================================
Đánh giá độ bền vững STT theo mức độ nhiễu (SNR).
Tương thích với ground_truth.json sinh bởi tts_generate_dataset.py.

Sử dụng:
    # Không có server (chỉ in warning):
    python scripts/research/eval_stt_robustness.py \\
        --noisy_dir data/wav_noisy \\
        --ground_truth data/wav_clean/ground_truth.json

    # Có Edge Server đang chạy:
    python scripts/research/eval_stt_robustness.py \\
        --noisy_dir data/wav_noisy \\
        --ground_truth data/wav_clean/ground_truth.json \\
        --server http://localhost:8000 \\
        --out_csv wer_results.csv
"""
import os
import glob
import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from jiwer import wer
except ImportError:
    print("ERROR: jiwer not installed.  pip install jiwer")
    sys.exit(1)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DEFAULT_SERVER = "http://localhost:8000"
TRANSCRIBE_ENDPOINT = "/transcribe"


def transcribe_audio(audio_path: str, server_url: str) -> str:
    """Gọi Whisper API trên Edge Server để transcribe một file WAV."""
    if not HAS_REQUESTS:
        return ""
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            resp = requests.post(f"{server_url}{TRANSCRIBE_ENDPOINT}", files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("text", "")
            else:
                print(f"  HTTP {resp.status_code}: {audio_path}")
                return ""
    except Exception as e:
        print(f"  Connection error: {e}")
        return ""


def compute_wer_report(
    audio_dir: str,
    ground_truth: dict,
    server_url: str,
    snr_label: str,
) -> dict:
    """Đánh giá WER trên tất cả WAV trong audio_dir."""
    audio_files = glob.glob(os.path.join(audio_dir, "*.wav"))
    if not audio_files:
        return {}

    all_wers = []
    per_intent: dict = defaultdict(list)

    for fpath in sorted(audio_files):
        fname = os.path.basename(fpath)
        if fname not in ground_truth:
            continue

        entry = ground_truth[fname]
        if isinstance(entry, dict):
            truth_text = entry.get("text", "").lower().strip()
            intent = entry.get("intent", "unknown")
        else:
            truth_text = str(entry).lower().strip()
            intent = "unknown"

        if not truth_text:
            continue

        pred_text = transcribe_audio(fpath, server_url).lower().strip()
        if not pred_text:
            error_rate = 1.0
        else:
            error_rate = wer(truth_text, pred_text)

        all_wers.append(error_rate)
        per_intent[intent].append(error_rate)

    if not all_wers:
        return {}

    avg_wer = sum(all_wers) / len(all_wers)
    return {
        "snr_label":   snr_label,
        "n_samples":   len(all_wers),
        "avg_wer":     round(avg_wer, 4),
        "avg_wer_pct": round(avg_wer * 100, 2),
        "per_intent":  {k: round(sum(v)/len(v), 4) for k, v in per_intent.items()},
    }


def load_ground_truth(gt_path: str) -> dict:
    """
    Load ground_truth.json. Hỗ trợ 2 format:
    - Simple: {filename: text_string}
    - Full:   {filename: {text, intent, lang, voice}}
    """
    with open(gt_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def main():
    parser = argparse.ArgumentParser(description="Evaluate Whisper WER across SNR levels.")
    parser.add_argument("--noisy_dir", type=str, default="data/wav_noisy",
                        help="Parent dir chứa các thư mục snr_*db/")
    parser.add_argument("--clean_dir", type=str, default="data/wav_clean/snr_clean",
                        help="Thư mục chứa clean WAV (baseline, SNR=∞)")
    parser.add_argument("--ground_truth", type=str, default="data/wav_clean/ground_truth.json",
                        help="Path đến ground_truth.json")
    parser.add_argument("--server", type=str, default=DEFAULT_SERVER,
                        help=f"URL Edge Server (default: {DEFAULT_SERVER})")
    parser.add_argument("--out_csv", type=str, default="wer_results.csv",
                        help="Output CSV file")
    args = parser.parse_args()

    if HAS_REQUESTS:
        try:
            requests.get(f"{args.server}/health", timeout=3)
            print(f"✓ Server reachable: {args.server}")
        except Exception:
            print(f"⚠ Server không phản hồi: {args.server}")
            print("  Kết quả WER sẽ là 100% (không thể transcribe).")
            print("  Chạy lại khi Edge Server đang chạy.\n")

    if not os.path.exists(args.ground_truth):
        print(f"ERROR: ground_truth.json not found: {args.ground_truth}")
        print("  Chạy tts_generate_dataset.py trước để tạo ground_truth.json")
        sys.exit(1)

    gt = load_ground_truth(args.ground_truth)
    print(f"Loaded {len(gt)} ground truth entries from {args.ground_truth}")

    results = []

    if os.path.isdir(args.clean_dir):
        print(f"\nEvaluating CLEAN baseline ({args.clean_dir})...")
        res = compute_wer_report(args.clean_dir, gt, args.server, "clean (∞ dB)")
        if res:
            results.append(res)
            print(f"  → WER: {res['avg_wer_pct']:.2f}%  (n={res['n_samples']})")

    noisy_parent = Path(args.noisy_dir)
    if noisy_parent.is_dir():
        snr_dirs = sorted(
            [d for d in noisy_parent.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        for snr_dir in snr_dirs:
            label = snr_dir.name
            print(f"Evaluating {label}...")
            res = compute_wer_report(str(snr_dir), gt, args.server, label)
            if res:
                results.append(res)
                print(f"  → WER: {res['avg_wer_pct']:.2f}%  (n={res['n_samples']})")

    if not results:
        print("\nKhông có kết quả nào. Kiểm tra lại thư mục và file WAV.")
        return

    print(f"\n{'='*55}")
    print("WER vs SNR SUMMARY (cho báo cáo NCKH)")
    print(f"{'='*55}")
    print(f"{'SNR Level':<20} {'WER':>8} {'Samples':>8}")
    print("-" * 40)
    for r in results:
        print(f"  {r['snr_label']:<18} {r['avg_wer_pct']:>7.2f}%  {r['n_samples']:>6}")
    print(f"{'='*55}")
    print("\nGhi chú: WER thấp = STT chính xác cao.")
    print("         WER tăng khi SNR giảm → chứng minh cần Mic foam chống gió.")

    if pd is not None:
        rows = []
        for r in results:
            row = {
                "SNR_Level": r["snr_label"],
                "Avg_WER": r["avg_wer"],
                "Avg_WER_Pct": r["avg_wer_pct"],
                "N_Samples": r["n_samples"],
            }
            for intent, wer_val in r.get("per_intent", {}).items():
                row[f"WER_{intent}"] = wer_val
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(args.out_csv, index=False)
        print(f"\nSaved to: {args.out_csv}")
    else:
        with open(args.out_csv, "w", encoding="utf-8") as f:
            f.write("SNR_Level,Avg_WER,Avg_WER_Pct,N_Samples\n")
            for r in results:
                f.write(f"{r['snr_label']},{r['avg_wer']},{r['avg_wer_pct']},{r['n_samples']}\n")
        print(f"\nSaved to: {args.out_csv}")


if __name__ == "__main__":
    main()
