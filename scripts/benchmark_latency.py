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
import struct
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

# ─── Config mặc định ─────────────────────────────────────────────────────────
SERVER_HOST = "localhost"
WS_PORT = 8765
HTTP_PORT = 8005
API_KEY = "drone-secret"
SAMPLE_RATE = 16_000
CHUNK_MS = 500

# Danh sách 50 câu lệnh mẫu tiếng Việt (đa dạng ngữ cảnh)
SAMPLE_COMMANDS = [
    "bay lên",
    "cất cánh",
    "hạ cánh",
    "dừng lại",
    "quay về nhà",
    "tiến lên",
    "lùi lại",
    "qua trái",
    "qua phải",
    "bay lên cao",
    "hạ xuống",
    "xoay phải 90 độ",
    "xoay trái 45 độ",
    "bay lên 2 mét",
    "tiến 3 mét",
    "lùi lại 1 mét",
    "bay tới trước",
    "dừng ngay lập tức",
    "theo dõi người kia",
    "bám theo người đó",
    "pin còn bao nhiêu",
    "độ cao hiện tại",
    "cất cánh lên 1 mét",
    "bay lên rồi tiến",
    "hạ cánh ngay",
    "quay về điểm xuất phát",
    "tiến 5 mét",
    "lên cao 3 mét",
    "xoay vòng 180 độ",
    "bắt đầu bay",
    "dừng lại đi",
    "tiến nhanh hơn",
    "bay chậm lại",
    "giữ nguyên vị trí",
    "hover ở đây",
    "đứng yên",
    "theo dõi xe kia",
    "bám theo đối tượng",
    "kiểm tra pin",
    "độ cao bao nhiêu",
    "bay về nhà ngay",
    "trở về điểm xuất phát",
    "cất cánh đi",
    "hạ cánh xuống",
    "tiến về phía trước",
    "lùi về phía sau",
    "sang trái",
    "sang phải",
    "lên trên",
    "xuống dưới",
]

# ─── WAV generator ────────────────────────────────────────────────────────────

def generate_wav_from_text(text: str, duration_sec: float = 1.5) -> bytes:
    """
    Tạo file WAV giả lập (silence + chirp noise) để test pipeline.
    Trong thực tế, thay thế bằng file WAV ghi âm thật.
    """
    num_samples = int(SAMPLE_RATE * duration_sec)
    t = np.linspace(0, duration_sec, num_samples)

    # Tạo signal: silence + chirp (giả lập giọng nói ngắn)
    signal = np.zeros(num_samples)

    # Chirp giữa (0.1s - 1.0s) để giả lập tiếng nói
    speech_start = int(0.1 * SAMPLE_RATE)
    speech_end = int(1.0 * SAMPLE_RATE)
    speech_t = t[speech_start:speech_end]

    # Sweep frequency 200Hz → 800Hz (chirp)
    freq_start, freq_end = 200.0, 800.0
    phase = 2 * np.pi * (freq_start * speech_t + 0.5 * (freq_end - freq_start) * speech_t**2)
    chirp = 0.3 * np.sin(phase)

    # Envelope (fade in/out)
    envelope = np.hanning(len(speech_t))
    signal[speech_start:speech_end] = chirp * envelope

    # Convert to int16
    audio_int16 = (signal * 32767).astype(np.int16)

    # Pack as WAV bytes
    import io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def load_wav_samples(wav_dir: Optional[str]) -> list:
    """Load WAV files từ thư mục, hoặc tạo synthetic nếu không có."""
    samples = []

    if wav_dir and os.path.isdir(wav_dir):
        wav_files = list(Path(wav_dir).glob("*.wav"))[:50]
        if wav_files:
            print(f"📁 Tìm thấy {len(wav_files)} file WAV trong {wav_dir}")
            for wf in wav_files:
                with open(wf, 'rb') as f:
                    samples.append({
                        "name": wf.stem,
                        "wav_bytes": f.read(),
                        "text": wf.stem,  # dùng tên file làm label
                    })
            return samples

    # Generate synthetic samples
    print(f"🔧 Không có file WAV thật. Tự tạo {len(SAMPLE_COMMANDS)} mẫu synthetic...")
    for i, cmd in enumerate(SAMPLE_COMMANDS):
        wav_bytes = generate_wav_from_text(cmd)
        samples.append({"name": f"cmd_{i:02d}", "wav_bytes": wav_bytes, "text": cmd})
    return samples


# ─── Benchmark Functions ──────────────────────────────────────────────────────

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
        # Warmup call
        try:
            await client.post(url, json={"text": "test warmup"})
        except Exception:
            pass

        for i, sample in enumerate(samples):
            text = sample["text"]
            try:
                t0 = time.perf_counter()
                resp = await client.post(url, json={"text": text})
                latency_ms = (time.perf_counter() - t0) * 1000

                data = resp.json()
                results.append({
                    "sample_id": i,
                    "text": text[:40],
                    "intent": data.get("intent", "N/A"),
                    "confidence": data.get("confidence", 0),
                    "nlp_latency_ms": round(latency_ms, 1),
                    "stt_latency_ms": 0,  # Không có STT trong REST mode
                    "e2e_latency_ms": round(latency_ms, 1),
                    "success": resp.status_code == 200,
                })

                # Progress
                bar = "█" * (i * 30 // len(samples)) + "░" * (30 - i * 30 // len(samples))
                print(f"\r  [{bar}] {i+1}/{len(samples)} | {text[:25]:<25} → {data.get('intent','?'):<15} ({latency_ms:.0f}ms)  ",
                      end="", flush=True)

            except Exception as e:
                results.append({
                    "sample_id": i, "text": text[:40], "intent": "ERROR",
                    "confidence": 0, "nlp_latency_ms": -1,
                    "stt_latency_ms": -1, "e2e_latency_ms": -1, "success": False,
                })
                print(f"\r  ⚠️  Sample {i}: {e}                              ", end="", flush=True)

    print()  # Newline
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
    chunk_size = int(SAMPLE_RATE * CHUNK_MS / 1000) * 2  # bytes (int16)

    print(f"\n📊 Benchmark WebSocket Pipeline ({len(samples)} samples)...")
    print(f"   URI: {uri}\n")

    for i, sample in enumerate(samples):
        wav_bytes = sample["wav_bytes"]
        # Extract raw PCM từ WAV
        import io
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            raw_pcm = wf.readframes(wf.getnframes())

        try:
            stt_latency = 0
            nlp_latency = 0

            t_start = time.perf_counter()

            async with websockets.connect(uri, open_timeout=5) as ws:
                # Stream audio chunks
                for offset in range(0, len(raw_pcm), chunk_size):
                    chunk = raw_pcm[offset:offset + chunk_size]
                    await ws.send(chunk)
                    await asyncio.sleep(CHUNK_MS / 1000)

                    # Đọc partial nếu có
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        data = json.loads(msg)
                        if data.get("type") == "partial":
                            stt_latency = (time.perf_counter() - t_start) * 1000
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        pass

                # Endpoint signal
                await ws.send(json.dumps({"event": "endpoint"}))

                # Nhận kết quả cuối
                intent = "timeout"
                confidence = 0.0
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        data = json.loads(msg)
                        t_end = time.perf_counter()
                        e2e_latency = (t_end - t_start) * 1000

                        if data.get("type") in ("command", "unknown", "error"):
                            intent = data.get("intent", "unknown")
                            confidence = data.get("confidence", 0)
                            nlp_latency = data.get("latency_ms", 0)
                            break
                except asyncio.TimeoutError:
                    e2e_latency = 10000  # timeout marker

            results.append({
                "sample_id": i,
                "text": sample["text"][:40],
                "intent": intent or "unknown",
                "confidence": confidence,
                "stt_latency_ms": round(stt_latency, 1),
                "nlp_latency_ms": round(nlp_latency, 1),
                "e2e_latency_ms": round(e2e_latency, 1),
                "success": intent not in ("timeout", "ERROR"),
            })

            bar = "█" * (i * 30 // len(samples)) + "░" * (30 - i * 30 // len(samples))
            print(f"\r  [{bar}] {i+1}/{len(samples)} | E2E: {e2e_latency:.0f}ms  ",
                  end="", flush=True)

        except Exception as e:
            results.append({
                "sample_id": i, "text": sample["text"][:40], "intent": "ERROR",
                "confidence": 0, "stt_latency_ms": -1, "nlp_latency_ms": -1,
                "e2e_latency_ms": -1, "success": False,
            })

    print()
    return results


# ─── Statistics & Report ──────────────────────────────────────────────────────

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
        print("❌ Không có kết quả benchmark.")
        return

    success = [r for r in results if r["success"]]
    fail_count = len(results) - len(success)

    stt_vals = [r["stt_latency_ms"] for r in success]
    nlp_vals = [r["nlp_latency_ms"] for r in success]
    e2e_vals = [r["e2e_latency_ms"] for r in success]

    stt_s = compute_stats(stt_vals)
    nlp_s = compute_stats(nlp_vals)
    e2e_s = compute_stats(e2e_vals)

    # Targets từ báo cáo NCKH
    stt_target = 250
    nlp_target = 10
    e2e_target = 300

    def status(val, target):
        return "✅ PASS" if val <= target else "❌ FAIL"

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
║  Samples: {len(results)}  |  Success: {len(success)}  |  Failed: {fail_count}          ║
╠══════════════════════════════════════════════════════════════════╣
║  STT Result : {status(stt_s['mean'], stt_target):<53}║
║  NLP Result : {status(nlp_s['mean'], nlp_target):<53}║
║  E2E Result : {status(e2e_s['mean'], e2e_target):<53}║
╚══════════════════════════════════════════════════════════════════╝""")


def save_csv(results: list, mode: str) -> str:
    """Xuất kết quả ra file CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_results_{mode}_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["sample_id", "text", "intent", "confidence",
                      "stt_latency_ms", "nlp_latency_ms", "e2e_latency_ms", "success"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n💾 Đã xuất kết quả ra: {filename}")
    return filename


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🔬 UAV Voice Control — Latency Benchmark Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python scripts/benchmark_latency.py                           # REST mode, localhost
  python scripts/benchmark_latency.py --mode ws --lang vi      # WebSocket mode
  python scripts/benchmark_latency.py --host 192.168.1.100     # Remote server
  python scripts/benchmark_latency.py --wav-dir samples/       # Dùng WAV thật
        """
    )
    parser.add_argument("--host", default="localhost", help="IP Edge Server")
    parser.add_argument("--ws-port", default=8765, type=int, help="WebSocket port")
    parser.add_argument("--http-port", default=8005, type=int, help="HTTP port (agent-service)")
    parser.add_argument("--mode", default="rest", choices=["rest", "ws"],
                        help="rest = chỉ test NLP | ws = test full pipeline E2E")
    parser.add_argument("--lang", default="vi", choices=["en", "vi"])
    parser.add_argument("--wav-dir", default=None, help="Thư mục chứa file WAV thật")
    parser.add_argument("--api-key", default="drone-secret")
    parser.add_argument("--samples", default=50, type=int, help="Số samples cần test")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════╗
║   🔬 UAV Voice Control — Latency Benchmark Tool      ║
║   Mode   : {args.mode:<43}║
║   Server : {args.host}:{args.ws_port if args.mode == 'ws' else args.http_port:<38}║
║   Samples: {args.samples:<43}║
╚══════════════════════════════════════════════════════╝
""")

    # Load samples
    samples = load_wav_samples(args.wav_dir)
    samples = samples[:args.samples]

    if args.mode == "rest":
        results = asyncio.run(benchmark_rest_endpoint(samples, args.host, args.http_port))
        mode_label = "REST_NLP_ONLY"
    else:
        results = asyncio.run(benchmark_websocket_pipeline(
            samples, args.host, args.ws_port, args.lang, args.api_key
        ))
        mode_label = f"WS_E2E_{args.lang.upper()}"

    # Report
    print_report(results, mode_label)
    if results:
        save_csv(results, mode_label)


if __name__ == "__main__":
    main()
