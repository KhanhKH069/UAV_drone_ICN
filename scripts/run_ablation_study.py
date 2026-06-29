"""
scripts/run_ablation_study.py
==============================
Chạy Ablation Study trên data/aug_all_groups.json và data/splits/val_unseen.json.
So sánh 3 baseline: Regex-only | LLM-only | Cascade.

Kết quả xuất ra:
  - Console: bảng ASCII đẹp
  - ablation_results.csv: cho báo cáo NCKH

Ví dụ chạy:
    # Chỉ chạy Regex (không cần server):
    python scripts/run_ablation_study.py --mode regex

    # Chạy Cascade (cần Edge Server đang chạy):
    python scripts/run_ablation_study.py --mode cascade --agent-url http://localhost:8005

    # Chạy tất cả 3 mode (cần server):
    python scripts/run_ablation_study.py --mode all --agent-url http://localhost:8005
"""
import importlib.util
import json
import sys
import time
import argparse
import csv
from pathlib import Path
from collections import defaultdict
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

_NLP_PATH = Path(__file__).parent.parent / "services" / "api-gateway" / "nlp.py"
spec = importlib.util.spec_from_file_location("nlp", _NLP_PATH)
nlp_mod = importlib.util.module_from_spec(spec)
sys.modules["nlp"] = nlp_mod
spec.loader.exec_module(nlp_mod)
regex_classify = nlp_mod.regex_classify


def call_llm_api(text: str, agent_url: str) -> Optional[str]:
    """Gọi agent-service /drone/classify để lấy intent qua LLM."""
    if requests is None:
        return None
    try:
        r = requests.post(
            f"{agent_url}/drone/classify",
            json={"text": text},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("intent")
    except Exception as e:
        print(f"  [LLM ERROR] {e}")
    return None


def load_dataset(path: Path) -> list[dict]:
    """Load dataset từ file JSON (hỗ trợ array và dict với key 'data')."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return raw
    return raw.get("data", [])


def evaluate_mode(
    records: list[dict],
    mode: str,
    agent_url: Optional[str],
    max_samples: Optional[int] = None,
) -> dict:
    """Chạy đánh giá cho một mode, trả về dict kết quả."""
    if max_samples:
        records = records[:max_samples]

    total = correct = unknown = wrong = 0
    per_intent: dict = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})
    latencies_ms: list[float] = []

    for r in records:
        true_intent = r.get("intent_confirmed") or r.get("intent_auto")
        if not true_intent:
            continue

        text = r.get("clean_text", "")
        t0 = time.perf_counter()

        if mode == "regex":
            predicted, _ = regex_classify(text)

        elif mode == "llm":
            predicted = call_llm_api(text, agent_url)

        else:
            predicted, _ = regex_classify(text)
            if not predicted:
                predicted = call_llm_api(text, agent_url)

        latencies_ms.append((time.perf_counter() - t0) * 1000)
        total += 1

        if predicted == true_intent:
            correct += 1
            per_intent[true_intent]["TP"] += 1
        elif predicted is None or predicted == "UNKNOWN":
            unknown += 1
            per_intent[true_intent]["FN"] += 1
        else:
            wrong += 1
            per_intent[true_intent]["FN"] += 1
            per_intent[predicted]["FP"] += 1

    accuracy = correct / total if total else 0
    mean_lat = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0
    sorted_lat = sorted(latencies_ms)
    p95 = sorted_lat[int(0.95 * len(sorted_lat)) - 1] if sorted_lat else 0
    p99 = sorted_lat[int(0.99 * len(sorted_lat)) - 1] if sorted_lat else 0

    return {
        "mode": mode,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "unknown": unknown,
        "accuracy": accuracy,
        "mean_latency_ms": round(mean_lat, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "per_intent": dict(per_intent),
    }


def print_summary(results: list[dict]):
    print("\n" + "=" * 70)
    print("ABLATION STUDY — SUMMARY")
    print("=" * 70)
    header = f"{'Mode':<12} {'Accuracy':>9} {'Correct':>8} {'Unknown':>8} {'Lat_mean':>10} {'P95':>8}"
    print(header)
    print("-" * 70)
    for r in results:
        print(
            f"{r['mode']:<12} {r['accuracy']*100:>8.1f}%"
            f" {r['correct']:>8}/{r['total']:<6}"
            f" {r['unknown']:>8}"
            f" {r['mean_latency_ms']:>9.1f}ms"
            f" {r['p95_latency_ms']:>7.1f}ms"
        )
    print("=" * 70)

    regex_res = next((r for r in results if r["mode"] == "regex"), None)
    if regex_res:
        print("\nPer-intent F1 (Regex mode):")
        print(f"{'Intent':<30} {'Prec':>6} {'Rec':>6} {'F1':>6} {'N':>5}")
        print("-" * 55)
        for intent, s in sorted(regex_res["per_intent"].items(), key=lambda x: -x[1].get("TP",0)):
            tp, fp, fn = s["TP"], s["FP"], s["FN"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec  = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            n    = tp + fn
            if n > 0:
                print(f"{intent:<30} {prec*100:>5.1f}% {rec*100:>5.1f}% {f1*100:>5.1f}% {n:>5}")


def save_csv(results: list[dict], out_path: Path):
    rows = []
    for r in results:
        rows.append({
            "mode":           r["mode"],
            "accuracy_%":     round(r["accuracy"] * 100, 2),
            "correct":        r["correct"],
            "total":          r["total"],
            "unknown":        r["unknown"],
            "mean_lat_ms":    r["mean_latency_ms"],
            "p95_lat_ms":     r["p95_latency_ms"],
            "p99_lat_ms":     r["p99_latency_ms"],
        })
        for intent, s in r["per_intent"].items():
            tp, fp, fn = s["TP"], s["FP"], s["FN"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec  = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            rows.append({
                "mode":       r["mode"],
                "intent":     intent,
                "precision":  round(prec, 4),
                "recall":     round(rec, 4),
                "f1_score":   round(f1, 4),
                "support":    tp + fn,
            })

    keys = sorted({k for row in rows for k in row.keys()})
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="UAV NLP Ablation Study")
    parser.add_argument(
        "--dataset", type=str,
        default="data/aug_all_groups.json",
        help="Path to dataset JSON (array or {data: [...]})"
    )
    parser.add_argument(
        "--mode", choices=["regex", "llm", "cascade", "all"],
        default="regex",
        help="Which mode(s) to evaluate"
    )
    parser.add_argument(
        "--agent-url", type=str,
        default="http://localhost:8005",
        help="URL của agent-service (cần cho llm/cascade mode)"
    )
    parser.add_argument(
        "--max-samples", type=int, default=None,
        help="Giới hạn số mẫu để test nhanh (mặc định: tất cả)"
    )
    parser.add_argument(
        "--out-csv", type=str,
        default="ablation_results.csv",
        help="Output CSV file"
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}")
        sys.exit(1)

    records = load_dataset(dataset_path)
    print(f"Loaded {len(records)} records from {dataset_path}")

    modes_to_run = ["regex", "llm", "cascade"] if args.mode == "all" else [args.mode]

    if any(m in modes_to_run for m in ["llm", "cascade"]) and requests is None:
        print("ERROR: 'requests' not installed. Run: pip install requests")
        sys.exit(1)

    results = []
    for mode in modes_to_run:
        print(f"\n>>> Evaluating mode: {mode.upper()} ...")
        result = evaluate_mode(records, mode, args.agent_url, args.max_samples)
        results.append(result)
        print(f"    Accuracy: {result['accuracy']*100:.1f}%  |  Mean latency: {result['mean_latency_ms']:.1f}ms")

    print_summary(results)
    save_csv(results, Path(args.out_csv))


if __name__ == "__main__":
    main()
