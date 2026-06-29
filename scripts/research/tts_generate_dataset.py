"""
scripts/research/tts_generate_dataset.py
=========================================
Tổng hợp WAV dataset từ text data trong data/aug_all_groups.json
bằng Microsoft Edge TTS (free, neural quality, no API key needed).

Cài đặt:
    pip install edge-tts librosa soundfile tqdm

Sử dụng nhanh (quick test ~50 WAV):
    python scripts/research/tts_generate_dataset.py --max-per-intent 4

Chuẩn báo cáo NCKH (~400 WAV):
    python scripts/research/tts_generate_dataset.py --max-per-intent 15

Đầy đủ nhất (~3300 WAV, 3 giọng):
    python scripts/research/tts_generate_dataset.py --max-per-intent 85 --voices en-US-AriaNeural en-GB-RyanNeural en-AU-NatashaNeural

Sau khi sinh WAV, thêm noise:
    python scripts/research/add_noise_to_dataset.py \\
        --clean_dir data/wav_clean/snr_clean \\
        --noise_file data/wav_clean/uav_propeller_noise.wav \\
        --out_dir data/wav_noisy \\
        --snr 20 10 5 0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import edge_tts
except ImportError:
    print("ERROR: edge-tts chưa được cài.\n  pip install edge-tts")
    sys.exit(1)

try:
    import soundfile as sf
except ImportError:
    print("ERROR: soundfile chưa được cài.\n  pip install soundfile")
    sys.exit(1)

try:
    from tqdm.asyncio import tqdm as atqdm
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    class tqdm:
        def __init__(self, iterable=None, **kw): self._it = iterable or []
        def __iter__(self): return iter(self._it)
        def update(self, n=1): pass
        def close(self): pass
        def set_postfix_str(self, s): print(f"  {s}")

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
AUG_DATASET  = DATA_DIR / "aug_all_groups.json"

DEFAULT_VOICES_EN = [
    "en-US-AriaNeural",
    "en-GB-RyanNeural",
]

VI_COMMANDS: list[dict] = [
    {"text": "cất cánh",                    "intent": "take_off"},
    {"text": "bay lên ngay",                "intent": "take_off"},
    {"text": "cất cánh lên hai mét",        "intent": "take_off"},
    {"text": "bay lên đi",                  "intent": "take_off"},
    {"text": "hạ cánh",                     "intent": "land"},
    {"text": "đáp xuống ngay",              "intent": "land"},
    {"text": "hạ cánh an toàn",             "intent": "land"},
    {"text": "đứng yên",                    "intent": "hover"},
    {"text": "giữ vị trí",                  "intent": "hover"},
    {"text": "giữ nguyên chỗ đó",           "intent": "hover"},
    {"text": "dừng khẩn cấp",               "intent": "emergency_stop"},
    {"text": "dừng ngay lập tức",           "intent": "emergency_stop"},
    {"text": "khẩn cấp dừng lại",           "intent": "emergency_stop"},
    {"text": "dừng ngay",                   "intent": "emergency_stop"},
    {"text": "về nhà",                      "intent": "return_home"},
    {"text": "quay về điểm xuất phát",      "intent": "return_home"},
    {"text": "bay về nhà",                  "intent": "return_home"},
    {"text": "tiến lên hai mét",            "intent": "move_forward"},
    {"text": "bay thẳng về phía trước",     "intent": "move_forward"},
    {"text": "đi thẳng mười mét",           "intent": "move_forward"},
    {"text": "lùi lại",                     "intent": "move_backward"},
    {"text": "bay lùi ba mét",              "intent": "move_backward"},
    {"text": "sang trái hai mét",           "intent": "move_left"},
    {"text": "bay sang bên trái",           "intent": "move_left"},
    {"text": "sang phải ba mét",            "intent": "move_right"},
    {"text": "bay sang bên phải",           "intent": "move_right"},
    {"text": "lên cao hơn",                 "intent": "ascend"},
    {"text": "bay cao thêm năm mét",        "intent": "ascend"},
    {"text": "nâng độ cao lên",             "intent": "ascend"},
    {"text": "hạ thấp xuống",               "intent": "descend"},
    {"text": "giảm độ cao",                 "intent": "descend"},
    {"text": "bay xuống thấp hơn",          "intent": "descend"},
    {"text": "xoay phải chín mươi độ",      "intent": "rotate_right"},
    {"text": "quay phải",                   "intent": "rotate_right"},
    {"text": "xoay trái bốn mươi lăm độ",  "intent": "rotate_left"},
    {"text": "quay trái",                   "intent": "rotate_left"},
    {"text": "bám theo người đó",           "intent": "follow_target"},
    {"text": "theo dõi xe màu đỏ",          "intent": "follow_target"},
    {"text": "đuổi theo mục tiêu",          "intent": "follow_target"},
    {"text": "pin còn bao nhiêu",           "intent": "get_battery"},
    {"text": "kiểm tra mức pin",            "intent": "get_battery"},
    {"text": "độ cao hiện tại là bao nhiêu","intent": "get_altitude"},
    {"text": "kiểm tra độ cao",             "intent": "get_altitude"},
    {"text": "bay vòng quanh tòa nhà",      "intent": "orbit"},
    {"text": "dừng lại",                    "intent": "stop"},
    {"text": "ngừng lại",                   "intent": "stop"},
]

VI_VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]



async def _synthesize_one(
    text: str,
    voice: str,
    out_wav: Path,
    rate: str = "+0%",
    retry: int = 3,
) -> bool:
    """Tong hop mot cau -> WAV 16kHz mono. Tra ve True neu thanh cong."""
    mp3_tmp = out_wav.with_suffix(".mp3")
    for attempt in range(retry):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(mp3_tmp))

            loop = asyncio.get_event_loop()
            returncode = await loop.run_in_executor(
                None,
                _ffmpeg_convert,
                str(mp3_tmp),
                str(out_wav),
            )
            mp3_tmp.unlink(missing_ok=True)

            if returncode != 0 or not out_wav.exists() or out_wav.stat().st_size < 100:
                raise RuntimeError(f"ffmpeg convert failed (code={returncode})")
            return True
        except Exception as e:
            if attempt < retry - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
            else:
                print(f"\n  [WARN] Failed: {out_wav.name} — {e}")
                mp3_tmp.unlink(missing_ok=True)
    return False


async def synthesize_batch(
    jobs: list[dict],
    concurrency: int = 6,
) -> list[bool]:
    """Chạy nhiều TTS job song song với giới hạn concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[bool] = []
    bar = tqdm(total=len(jobs), unit="wav", desc="TTS", ncols=80)

    async def _worker(job: dict) -> bool:
        async with semaphore:
            ok = await _synthesize_one(
                text=job["text"],
                voice=job["voice"],
                out_wav=job["out_wav"],
                rate=job.get("rate", "+0%"),
            )
            bar.update(1)
            bar.set_postfix_str(job["out_wav"].name[:40])
            return ok

    tasks = [asyncio.create_task(_worker(j)) for j in jobs]
    results = await asyncio.gather(*tasks)
    bar.close()
    return list(results)



def generate_propeller_noise(
    duration_sec: float = 30.0,
    sr: int = 16000,
    fundamental_hz: float = 160.0,
    seed: int = 42,
) -> np.ndarray:
    """
    Tạo tiếng ồn cánh quạt UAV tổng hợp.
    Gồm: fundamental + harmonics + broadband noise + amplitude modulation.
    """
    rng = np.random.default_rng(seed)
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    signal = np.zeros(n)
    for k, amp in enumerate([0.35, 0.20, 0.12, 0.07, 0.04, 0.02], start=1):
        wobble = 1 + 0.003 * np.sin(2 * np.pi * 0.3 * t)
        signal += amp * np.sin(2 * np.pi * k * fundamental_hz * wobble * t)

    broadband = rng.standard_normal(n) * 0.25
    from scipy.signal import butter, lfilter
    b, a = butter(4, 3000 / (sr / 2), btype="low")
    broadband = lfilter(b, a, broadband)

    signal += broadband

    bpf = fundamental_hz * 4
    am = 1.0 + 0.15 * np.sin(2 * np.pi * bpf * t)
    signal *= am

    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.25

    return signal.astype(np.float32)



def load_and_sample_en(
    dataset_path: Path,
    max_per_intent: int,
    seed: int = 42,
) -> list[dict]:
    """Đọc dataset JSON, sample đều mỗi intent."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    by_intent: dict[str, list] = {}
    for r in records:
        intent = r.get("intent_confirmed") or r.get("intent_auto")
        text   = r.get("clean_text", "").strip()
        if not intent or not text:
            continue
        by_intent.setdefault(intent, []).append(
            {"id": r["id"], "text": text, "intent": intent, "lang": "en"}
        )

    rng = random.Random(seed)
    selected = []
    for intent, items in sorted(by_intent.items()):
        rng.shuffle(items)
        selected.extend(items[:max_per_intent])

    return selected


def build_jobs(
    en_records: list[dict],
    vi_records: list[dict],
    en_voices: list[str],
    vi_voices: list[str],
    out_dir: Path,
    skip_existing: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Tạo danh sách TTS jobs và ground_truth entries."""
    jobs: list[dict] = []
    gt: list[dict]   = []

    def _add(record: dict, voice: str):
        voice_short = voice.split("-")[-1].replace("Neural", "")
        safe_id = record.get("id", f"{record['intent']}_{len(gt):04d}")
        lang = record.get("lang", "en")
        filename = f"{safe_id}_{voice_short}.wav"
        out_wav  = out_dir / filename

        gt.append({
            "filename": filename,
            "text":     record["text"],
            "intent":   record["intent"],
            "lang":     lang,
            "voice":    voice,
        })

        if skip_existing and out_wav.exists() and out_wav.stat().st_size > 1000:
            return

        rate = "+0%"
        if lang == "vi":
            rate = "-5%"

        jobs.append({"text": record["text"], "voice": voice, "out_wav": out_wav, "rate": rate})

    for rec in en_records:
        for voice in en_voices:
            _add(rec, voice)

    for rec in vi_records:
        for voice in vi_voices:
            _add(rec, voice)

    return jobs, gt


def save_ground_truth(gt: list[dict], out_path: Path):
    """Lưu ground_truth.json tương thích với eval_stt_robustness.py."""
    gt_simple = {item["filename"]: item["text"] for item in gt}

    gt_full = {"total": len(gt), "data": gt}

    out_path.write_text(
        json.dumps(gt_simple, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out_path.with_name("ground_truth_full.json").write_text(
        json.dumps(gt_full, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved ground_truth.json ({len(gt)} entries) → {out_path}")


def print_summary(gt: list[dict], n_ok: int):
    from collections import Counter
    intents = Counter(r["intent"] for r in gt)
    langs   = Counter(r["lang"] for r in gt)

    print(f"\n{'='*55}")
    print(f"TTS DATASET SUMMARY")
    print(f"{'='*55}")
    print(f"Total WAV files  : {len(gt)}")
    print(f"Successfully syn : {n_ok}")
    print(f"Languages        : {dict(langs)}")
    print(f"\nDistribution by intent:")
    print(f"{'Intent':<28} {'Count':>6}")
    print("-" * 36)
    for intent, count in sorted(intents.items()):
        print(f"  {intent:<26} {count:>6}")
    print(f"{'='*55}")



def parse_args():
    p = argparse.ArgumentParser(
        description="Tổng hợp WAV dataset từ text commands bằng Edge TTS."
    )
    p.add_argument(
        "--dataset", type=str, default=str(AUG_DATASET),
        help="Path đến JSON dataset (aug_all_groups.json hoặc splits/*.json)"
    )
    p.add_argument(
        "--out-dir", type=str, default=str(DATA_DIR / "wav_clean" / "snr_clean"),
        help="Thư mục xuất WAV file"
    )
    p.add_argument(
        "--max-per-intent", type=int, default=15,
        help="Số câu tối đa mỗi intent từ dataset EN (default: 15 → ~390 WAV)"
    )
    p.add_argument(
        "--voices", nargs="+",
        default=DEFAULT_VOICES_EN,
        help="Danh sách giọng đọc tiếng Anh (edge-tts voice names)"
    )
    p.add_argument(
        "--include-vi", action="store_true", default=True,
        help="Thêm câu lệnh tiếng Việt (default: True)"
    )
    p.add_argument(
        "--no-vi", action="store_true",
        help="Tắt tiếng Việt"
    )
    p.add_argument(
        "--vi-voices", nargs="+", default=VI_VOICES,
        help="Giọng tiếng Việt"
    )
    p.add_argument(
        "--gen-noise", action="store_true", default=True,
        help="Tạo file tiếng ồn cánh quạt tổng hợp (default: True)"
    )
    p.add_argument(
        "--no-noise", action="store_true",
        help="Không tạo file noise"
    )
    p.add_argument(
        "--auto-add-noise", action="store_true",
        help="Sau khi sinh WAV, tự động tạo noisy variants (SNR 20/10/5/0 dB)"
    )
    p.add_argument(
        "--concurrency", type=int, default=6,
        help="Số request TTS song song (default: 6)"
    )
    p.add_argument(
        "--seed", type=int, default=42,
        help="Random seed cho sampling"
    )
    p.add_argument(
        "--list-voices", action="store_true",
        help="Liệt kê tất cả giọng tiếng Anh và Việt available, rồi thoát"
    )
    return p.parse_args()


async def list_voices_async():
    voices = await edge_tts.list_voices()
    en_voices = [v for v in voices if v["Locale"].startswith("en-")]
    vi_voices = [v for v in voices if v["Locale"].startswith("vi-")]
    print("\n── Tiếng Anh (en-*) ──────────────────────────────")
    for v in sorted(en_voices, key=lambda x: x["ShortName"]):
        print(f"  {v['ShortName']:<40} {v['Gender']}")
    print("\n── Tiếng Việt (vi-*) ──────────────────────────────")
    for v in sorted(vi_voices, key=lambda x: x["ShortName"]):
        print(f"  {v['ShortName']:<40} {v['Gender']}")


async def main_async(args):
    if args.list_voices:
        await list_voices_async()
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    include_vi = args.include_vi and not args.no_vi
    gen_noise  = args.gen_noise  and not args.no_noise

    print(f"\n{'='*55}")
    print(f"UAV TTS DATASET GENERATOR")
    print(f"{'='*55}")
    print(f"Dataset     : {args.dataset}")
    print(f"Output      : {out_dir}")
    print(f"Max/intent  : {args.max_per_intent}")
    print(f"EN Voices   : {args.voices}")
    print(f"VI included : {include_vi}")
    if include_vi:
        print(f"VI Voices   : {args.vi_voices}")
    print(f"Gen noise   : {gen_noise}")
    print(f"Concurrency : {args.concurrency}")
    print(f"{'='*55}\n")

    print("[1/5] Loading English dataset...")
    en_records = load_and_sample_en(
        Path(args.dataset), args.max_per_intent, seed=args.seed
    )
    print(f"  Sampled {len(en_records)} EN records from {args.dataset}")

    vi_records = VI_COMMANDS if include_vi else []
    if include_vi:
        print(f"  Added {len(vi_records)} VI commands")

    jobs, gt = build_jobs(
        en_records, vi_records,
        en_voices=args.voices,
        vi_voices=args.vi_voices if include_vi else [],
        out_dir=out_dir,
        skip_existing=True,
    )

    total_planned = len(gt)
    n_skip = total_planned - len(jobs)
    print(f"\n[2/5] Total WAV planned : {total_planned}")
    if n_skip:
        print(f"  Skipping (exists)  : {n_skip}")
    print(f"  To synthesize      : {len(jobs)}")

    noise_path = out_dir.parent / "uav_propeller_noise.wav"
    if gen_noise and not noise_path.exists():
        print(f"\n[3/5] Generating synthetic UAV propeller noise -> {noise_path.name}...")
        noise = generate_propeller_noise(duration_sec=60.0, sr=16000, fundamental_hz=160.0)
        sf.write(str(noise_path), noise, 16000, subtype="PCM_16")
        print(f"  Saved: {noise_path} ({noise_path.stat().st_size//1024} KB)")
    elif noise_path.exists():
        print(f"\n[3/5] Noise file exists, skipping: {noise_path.name}")

    if not jobs:
        print("\n[4/5] All files already exist. Nothing to synthesize.")
    else:
        print(f"\n[4/5] Synthesizing {len(jobs)} files (concurrency={args.concurrency})...")
        t0 = time.perf_counter()
        results = await synthesize_batch(jobs, concurrency=args.concurrency)
        elapsed = time.perf_counter() - t0
        n_ok = sum(1 for r in results if r)
        n_fail = len(results) - n_ok
        print(f"\n  Done in {elapsed:.1f}s | OK: {n_ok} | Failed: {n_fail}")

    gt_path = out_dir.parent / "ground_truth.json"
    save_ground_truth(gt, gt_path)

    if args.auto_add_noise and noise_path.exists():
        print("\n[5/5] Running add_noise_to_dataset.py...")
        noisy_dir = out_dir.parent.parent / "wav_noisy"
        add_noise_script = Path(__file__).parent / "add_noise_to_dataset.py"

        cmd = (
            f'python "{add_noise_script}" '
            f'--clean_dir "{out_dir}" '
            f'--noise_file "{noise_path}" '
            f'--out_dir "{noisy_dir}" '
            f'--snr 20 10 5 0'
        )
        print(f"  Running: {cmd}")
        ret = os.system(cmd)
        if ret == 0:
            print(f"  Noisy variants saved to: {noisy_dir}")
        else:
            print(f"  [WARN] add_noise_to_dataset.py returned code {ret}")

    n_ok_total = sum(1 for p in out_dir.glob("*.wav") if p.stat().st_size > 1000)
    print_summary(gt, n_ok_total)

    print(f"\nDone! Dataset ready at: {out_dir}")
    print(f"\nNext steps:")
    print(f"  # Chay WER evaluation (can server dang chay):")
    print(f"  python scripts/research/eval_stt_robustness.py \\")
    print(f"    --noisy_dir data/wav_noisy \\")
    print(f"    --ground_truth data/wav_clean/ground_truth.json \\")
    print(f"    --out_csv wer_results.csv")
    print(f"\n  # Chạy E2E latency benchmark:")
    print(f"  python scripts/benchmark_latency.py --mode ws \\")
    print(f"    --wav-dir data/wav_clean/snr_clean --host localhost")


def _ffmpeg_convert(mp3_path: str, wav_path: str, sample_rate: int = 16000) -> int:
    """Blocking ffmpeg call: MP3 -> WAV 16kHz mono PCM. Returns returncode."""
    import subprocess
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", mp3_path,
            "-ar", str(sample_rate),
            "-ac", "1",
            "-sample_fmt", "s16",
            wav_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    return result.returncode


def main():
    args = parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
