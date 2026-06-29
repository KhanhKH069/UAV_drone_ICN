"""
scripts/benchmark_latency.py
Script đo lường độ trễ toàn bộ pipeline cho báo cáo NCKH.

Đo các giai đoạn:
  - STT (Speech-to-Text): Whisper/Qwen3 nhận audio → text
  - NLP (Intent Classify): LLM/Regex phân loại intent
  - E2E (End-to-End): Tổng thời gian từ gửi audio đến nhận lệnh

Cách dùng:
  # Test với WAV samples tự tạo:
  python scripts/benchmark_latency.py

  # Test với thư mục WAV thật:
  python scripts/benchmark_latency.py --wav-dir path/to/wav/folder

  # Kết nối server khác:
  python scripts/benchmark_latency.py --host 192.168.1.100 --port 8765

Output:
  - In bảng kết quả ra terminal (ASCII table)
  - Xuất file: benchmark_results_YYYYMMDD_HHMMSS.csv

Cài dependencies:
  pip install numpy scipy websockets httpx
"""

import argparse
import asyncio
import csv
import json
import os
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False

SERVER_HOST = "localhost"
WS_PORT = 8765
HTTP_PORT = 8005
API_KEY = "drone-secret"
SAMPLE_RATE = 16_000
CHUNK_MS = 500

SAMPLE_COMMANDS = [
    "take off now",
    "lift off and start mapping",
    "take off from platform A",
    "depart and maintain ten meters",
    "launch and hold position",
    "land now",
    "touch down slowly",
    "descend and land at home",
    "set down carefully",
    "hover here",
    "hold position above the road",
    "maintain altitude",
    "stay in place",
    "stop",
    "halt immediately",
    "emergency stop",
    "abort abort abort",
    "return home",
    "go home to base",
    "fly back and check in",
    "move forward 3 meters",
    "advance 6 meters",
    "move backward 2 meters",
    "back up slowly",
    "strafe left 2 meters",
    "slide right 4 meters",
    "move 8 meters left of the building",
    "ascend past the obstacle",
    "fly up to survey altitude",
    "descend to ground level",
    "decrease altitude carefully",
    "turn right 90 degrees",
    "rotate left 45 degrees",
    "yaw right 180 degrees",
    "follow the person",
    "track the red car",
    "chase the moving target",
    "how much battery is left",
    "what is the current altitude",
    "battery level please",
    "fly around the field for coverage",
    "scan the paddy field",
    "loop around the waypoint",
    "spray the fertilizer evenly",
    "which direction should I go",
    "am I near the crop field",
    "is the target in my view",
    "how far to the target from here",
    "am I at the waypoint yet",
    "is the destination in view now",
]


def generate_wav_from_text(text: str, duration_sec: float = 1.5) -> bytes:
    """
    Tạo file WAV giả lập (silence + chirp noise) để test pipeline.
    Trong thực tế, thay thế bằng file WAV ghi âm thật.
    """
    num_samples = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, num_samples)

    signal = np.zeros(num_samples)

    speech_start = int(0.1 * SAMPLE_RATE)
    speech_end = int(1.0 * SAMPLE_RATE)
    speech_t = t[speech_start:speech_end]

    freq_start, freq_end = 200.0, 800.0
    phase = 2 * np.pi * (freq_start * speech_t + 0.5 * (freq_end - freq_start) * speech_t**2)
    chirp = 0.3 * np.sin(phase)

    envelope = np.hanning(len(speech_t))
    signal[speech_start:speech_end] = chirp * envelope

    audio_int16 = (signal * 32767).astype(np.int16)

    import io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


_DEFAULT_WAV_DIR   = Path(__file__).parent.parent / "data" / "wav_clean" / "snr_clean"
_GT_FULL = Path(__file__).parent.parent / "data" / "wav_clean" / "ground_truth_full.json"
_GT_SIMPLE = Path(__file__).parent.parent / "data" / "wav_clean" / "ground_truth.json"


def _load_ground_truth(wav_dir: Path):
    """
    Load ground truth data. Returns a dict:
      { filename -> {"text": str, "intent": str} }
    Priority: ground_truth_full.json (has direct intent field) > ground_truth.json (text only).
    """
    import json

    for full_candidate in [
        wav_dir.parent / "ground_truth_full.json",
        wav_dir / "ground_truth_full.json",
        _GT_FULL,
    ]:
        if full_candidate.exists():
            with open(full_candidate, "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = raw.get("data", raw) if isinstance(raw, dict) else raw
            gt = {e["filename"]: {"text": e["text"], "intent": e.get("intent")} for e in entries}
            print(f"[INFO] Loaded {full_candidate.name}: {len(gt)} entries (with intents)")
            return gt

    for simple_candidate in [
        wav_dir.parent / "ground_truth.json",
        wav_dir / "ground_truth.json",
        _GT_SIMPLE,
    ]:
        if simple_candidate.exists():
            with open(simple_candidate, "r", encoding="utf-8") as f:
                simple = json.load(f)
            gt = {fname: {"text": text, "intent": None} for fname, text in simple.items()}
            print(f"[INFO] Loaded {simple_candidate.name}: {len(gt)} entries (text only, intent from filename)")
            return gt

    return {}


def load_wav_samples(wav_dir: Optional[str], max_samples: int = 50) -> list:
    """Load WAV files from directory (prefer real dataset), or generate synthetic English samples."""
    samples = []

    target_dir: Optional[Path] = None
    if wav_dir and os.path.isdir(wav_dir):
        target_dir = Path(wav_dir)
    elif _DEFAULT_WAV_DIR.is_dir():
        target_dir = _DEFAULT_WAV_DIR
        print(f"[INFO] Auto-detected dataset: {target_dir}")

    if target_dir is not None:
        wav_files = sorted(target_dir.glob("*.wav"))[:max_samples]
        if wav_files:
            gt = _load_ground_truth(target_dir)
            print(f"[INFO] Loading {len(wav_files)} WAV files from {target_dir.name}/")
            for wf in wav_files:
                with open(wf, 'rb') as f:
                    wav_bytes = f.read()
                gt_entry = gt.get(wf.name, {})
                intent = gt_entry.get("intent") or _stem_to_intent(wf.stem)
                text = gt_entry.get("text") or wf.stem.replace("_", " ")
                samples.append({
                    "name": wf.stem,
                    "wav_bytes": wav_bytes,
                    "text": text,
                    "ground_truth_intent": intent,
                })
            return samples

    print(f"[INFO] No WAV files found. Generating {len(SAMPLE_COMMANDS)} synthetic English samples...")
    for i, cmd in enumerate(SAMPLE_COMMANDS):
        wav_bytes = generate_wav_from_text(cmd)
        samples.append({
            "name": f"cmd_{i:02d}",
            "wav_bytes": wav_bytes,
            "text": cmd,
            "ground_truth_intent": None,
        })
    return samples


def _stem_to_intent(stem: str) -> Optional[str]:
    """Fallback: Extract intent label from filename stem like aug_take_off_0063_Aria."""
    parts = stem.split("_")
    if len(parts) >= 4 and parts[0] == "aug":
        intent_parts = parts[1:-2]
        return "_".join(intent_parts) if intent_parts else None
    return None



async def benchmark_rest_endpoint(samples: list, host: str, port: int) -> list:
    """
    Benchmark endpoint REST /drone/classify (chỉ đo NLP latency).
    Không cần audio, gửi thẳng text.
    """
    if not HAS_HTTPX:
        print("❌ Cần cài: pip install httpx")
        return []

    url = f"http://{host}:{port}/drone/classify"
    results = []

    print(f"\n📊 Benchmark REST /drone/classify ({len(samples)} samples)...")
    print(f"   URL: {url}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            await client.post(url, json={"text": "test warmup"})
        except Exception:
            pass

        for i, sample in enumerate(samples):
            text = sample["text"]
            gt_intent = sample.get("ground_truth_intent")
            try:
                t0 = time.perf_counter()
                resp = await client.post(url, json={"text": text})
                latency_ms = (time.perf_counter() - t0) * 1000

                data = resp.json()
                predicted_intent = data.get("intent", "N/A")
                results.append({
                    "sample_id": i,
                    "name": sample.get("name", f"cmd_{i:02d}"),
                    "text": text[:40],
                    "ground_truth_intent": gt_intent,
                    "intent": predicted_intent,
                    "correct": (gt_intent is not None and predicted_intent == gt_intent),
                    "confidence": data.get("confidence", 0),
                    "nlp_latency_ms": round(latency_ms, 1),
                    "stt_latency_ms": 0,
                    "e2e_latency_ms": round(latency_ms, 1),
                    "success": resp.status_code == 200,
                })

                correct_mark = "✓" if (gt_intent and predicted_intent == gt_intent) else ("?" if not gt_intent else "✗")
                bar = "█" * (i * 30 // len(samples)) + "░" * (30 - i * 30 // len(samples))
                print(f"\r  [{bar}] {i+1}/{len(samples)} | {text[:25]:<25} → {predicted_intent:<18} {correct_mark} ({latency_ms:.0f}ms)  ",
                      end="", flush=True)

            except Exception as e:
                results.append({
                    "sample_id": i, "name": sample.get("name", ""), "text": text[:40],
                    "ground_truth_intent": gt_intent, "intent": "ERROR", "correct": False,
                    "confidence": 0, "nlp_latency_ms": -1,
                    "stt_latency_ms": -1, "e2e_latency_ms": -1, "success": False,
                })
                print(f"\r  ⚠️  Sample {i}: {e}                              ", end="", flush=True)

    print()
    return results


async def benchmark_websocket_pipeline(samples: list, host: str, ws_port: int,
                                       lang: str = "vi", api_key: str = "drone-secret") -> list:
    """
    Benchmark toàn bộ pipeline qua WebSocket (đo E2E latency thật).
    Audio → WebSocket → STT → NLP → Response
    """
    if not HAS_WS:
        print("❌ Cần cài: pip install websockets")
        return []

    uri = f"ws://{host}:{ws_port}/drone/stream?api_key={api_key}&drone_id=benchmark-bot&lang={lang}"
    results = []
    chunk_size = int(SAMPLE_RATE * CHUNK_MS / 1000) * 2

    print(f"\n📊 Benchmark WebSocket Pipeline ({len(samples)} samples)...")
    print(f"   URI: {uri}\n")

    for i, sample in enumerate(samples):
        wav_bytes = sample["wav_bytes"]
        import io
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            raw_pcm = wf.readframes(wf.getnframes())

        try:
            stt_latency = 0
            nlp_latency = 0

            t_start = time.perf_counter()

            async with websockets.connect(uri, open_timeout=5) as ws:
                for offset in range(0, len(raw_pcm), chunk_size):
                    chunk = raw_pcm[offset:offset + chunk_size]
                    await ws.send(chunk)
                    await asyncio.sleep(CHUNK_MS / 1000)

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        data = json.loads(msg)
                        if data.get("type") == "partial":
                            stt_latency = (time.perf_counter() - t_start) * 1000
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        pass

                await ws.send(json.dumps({"event": "endpoint"}))

                intent = "timeout"
                confidence = 0.0
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        data = json.loads(msg)
                        t_end = time.perf_counter()
                        e2e_latency = (t_end - t_start) * 1000

                        if data.get("type") == "command_list":
                            cmds = data.get("commands", [])
                            if cmds:
                                intent = cmds[0].get("intent", "unknown")
                                confidence = cmds[0].get("confidence", 0)
                            else:
                                intent = "unknown"
                                confidence = 0.0
                            nlp_latency = data.get("latency_ms", 0)
                            break
                        elif data.get("type") in ("command", "unknown", "error"):
                            intent = data.get("intent", "unknown")
                            confidence = data.get("confidence", 0)
                            nlp_latency = data.get("latency_ms", 0)
                            break
                except asyncio.TimeoutError:
                    e2e_latency = 10000

            results.append({
                "sample_id": i,
                "name": sample["name"],
                "text": sample["text"][:40],
                "ground_truth_intent": sample.get("ground_truth_intent"),
                "intent": intent or "unknown",
                "confidence": confidence,
                "stt_latency_ms": round(stt_latency, 1),
                "nlp_latency_ms": round(nlp_latency, 1),
                "e2e_latency_ms": round(e2e_latency, 1),
                "success": intent not in ("timeout", "ERROR"),
                "correct": (sample.get("ground_truth_intent") is not None
                            and intent == sample.get("ground_truth_intent")),
            })

            bar = "█" * (i * 30 // len(samples)) + "░" * (30 - i * 30 // len(samples))
            print(f"\r  [{bar}] {i+1}/{len(samples)} | E2E: {e2e_latency:.0f}ms  ",
                  end="", flush=True)

        except Exception:
            results.append({
                "sample_id": i, "text": sample["text"][:40], "intent": "ERROR",
                "confidence": 0, "stt_latency_ms": -1, "nlp_latency_ms": -1,
                "e2e_latency_ms": -1, "success": False,
            })

    print()
    return results



def compute_stats(values: list) -> dict:
    """Tính toán thống kê cơ bản từ danh sách latency values."""
    valid = [v for v in values if v >= 0]
    if not valid:
        return {"mean": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0, "count": 0}
    arr = sorted(valid)
    n = len(arr)
    return {
        "mean": round(np.mean(arr), 1),
        "p50":  round(np.percentile(arr, 50), 1),
        "p95":  round(np.percentile(arr, 95), 1),
        "p99":  round(np.percentile(arr, 99), 1),
        "max":  round(max(arr), 1),
        "count": n,
    }


def print_report(results: list, mode: str):
    """In báo cáo kết quả benchmark dạng ASCII table."""
    if not results:
        print("❌ No benchmark results.")
        return

    success = [r for r in results if r["success"]]
    fail_count = len(results) - len(success)

    stt_vals = [r["stt_latency_ms"] for r in success]
    nlp_vals = [r["nlp_latency_ms"] for r in success]
    e2e_vals = [r["e2e_latency_ms"] for r in success]

    stt_s = compute_stats(stt_vals)
    nlp_s = compute_stats(nlp_vals)
    e2e_s = compute_stats(e2e_vals)

    gt_results = [r for r in success if r.get("ground_truth_intent") is not None]
    intent_accuracy: Optional[float] = None
    if gt_results:
        correct = sum(1 for r in gt_results if r.get("correct", False))
        intent_accuracy = correct / len(gt_results) * 100

    stt_target = 250
    nlp_target = 10
    e2e_target = 300

    def status(val, target):
        return "✅ PASS" if val <= target else "❌ FAIL"

    acc_line = (f"  Intent Acc: {intent_accuracy:.1f}% ({sum(1 for r in gt_results if r.get('correct'))}/{len(gt_results)} w/ GT)"
                if intent_accuracy is not None else "  Intent Acc: N/A (no ground truth labels)")

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          BENCHMARK REPORT — UAV Voice Control Pipeline           ║
║          Mode: {mode:<50}║
╠══════════════╦════════╦════════╦════════╦════════╦═══════╦═════════╣
║  Metric      ║  Mean  ║  P50   ║  P95   ║  P99   ║  Max  ║ Target  ║
╠══════════════╬════════╬════════╬════════╬════════╬═══════╬═════════╣
║  STT (ms)    ║{stt_s['mean']:>7.1f} ║{stt_s['p50']:>7.1f} ║{stt_s['p95']:>7.1f} ║{stt_s['p99']:>7.1f} ║{stt_s['max']:>6.1f} ║  <{stt_target}ms  ║
║  NLP (ms)    ║{nlp_s['mean']:>7.1f} ║{nlp_s['p50']:>7.1f} ║{nlp_s['p95']:>7.1f} ║{nlp_s['p99']:>7.1f} ║{nlp_s['max']:>6.1f} ║  <{nlp_target}ms   ║
║  E2E (ms)    ║{e2e_s['mean']:>7.1f} ║{e2e_s['p50']:>7.1f} ║{e2e_s['p95']:>7.1f} ║{e2e_s['p99']:>7.1f} ║{e2e_s['max']:>6.1f} ║  <{e2e_target}ms  ║
╠══════════════╩════════╩════════╩════════╩════════╩═══════╩═════════╣
║  Samples: {len(results):<4} |  Success: {len(success):<4} |  Failed: {fail_count:<4}                  ║
║  {acc_line:<64}║
╠══════════════════════════════════════════════════════════════════╣
║  STT Result : {status(stt_s['mean'], stt_target):<53}║
║  NLP Result : {status(nlp_s['mean'], nlp_target):<53}║
║  E2E Result : {status(e2e_s['mean'], e2e_target):<53}║
╚══════════════════════════════════════════════════════════════════╝""")


def save_csv(results: list, mode: str) -> str:
    """Export benchmark results to CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_results_{mode}_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["sample_id", "name", "text", "ground_truth_intent",
                      "intent", "correct", "confidence",
                      "stt_latency_ms", "nlp_latency_ms", "e2e_latency_ms", "success"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[DONE] Results saved to: {filename}")
    return filename



def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="UAV Voice Control -- Latency Benchmark Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/benchmark_latency.py                        # REST mode, auto-load EN WAVs
  python scripts/benchmark_latency.py --mode ws --lang en   # WebSocket E2E mode
  python scripts/benchmark_latency.py --host 192.168.1.100  # Remote server
  python scripts/benchmark_latency.py --wav-dir samples/    # Custom WAV directory
        """
    )
    parser.add_argument("--host", default="localhost", help="Edge Server IP")
    parser.add_argument("--ws-port", default=8765, type=int, help="WebSocket port")
    parser.add_argument("--http-port", default=8005, type=int, help="HTTP port (agent-service)")
    parser.add_argument("--mode", default="rest", choices=["rest", "ws"],
                        help="rest = NLP-only test | ws = full E2E pipeline test")
    parser.add_argument("--lang", default="en", choices=["en", "vi"],
                        help="Language for STT (default: en for English WAV dataset)")
    parser.add_argument("--wav-dir", default=None,
                        help="WAV directory (default: data/wav_clean/snr_clean/)")
    parser.add_argument("--api-key", default="drone-secret")
    parser.add_argument("--samples", default=50, type=int, help="Max number of samples to test")
    args = parser.parse_args()

    print(
        "\n+------------------------------------------------------+\n"
        "| UAV Voice Control -- Latency Benchmark Tool         |\n"
        f"| Mode   : {args.mode:<43}|\n"
        f"| Server : {args.host}:{args.ws_port if args.mode == 'ws' else args.http_port:<38}|\n"
        f"| Samples: {args.samples:<43}|\n"
        "+------------------------------------------------------+\n"
    )

    samples = load_wav_samples(args.wav_dir, max_samples=args.samples)

    if args.mode == "rest":
        results = asyncio.run(benchmark_rest_endpoint(samples, args.host, args.http_port))
        mode_label = "REST_NLP_ONLY"
    else:
        results = asyncio.run(benchmark_websocket_pipeline(
            samples, args.host, args.ws_port, args.lang, args.api_key
        ))
        mode_label = f"WS_E2E_{args.lang.upper()}"

    print_report(results, mode_label)
    if results:
        save_csv(results, mode_label)


if __name__ == "__main__":
    main()
