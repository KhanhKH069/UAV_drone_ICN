import sys
import os
import json
import argparse
import requests
import pandas as pd
from collections import defaultdict
import importlib.util

nlp_module_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "services", "api-gateway", "nlp.py")
)
try:
    spec = importlib.util.spec_from_file_location("nlp", nlp_module_path)
    nlp = importlib.util.module_from_spec(spec)
    sys.modules["nlp"] = nlp
    spec.loader.exec_module(nlp)
    _regex_classify = nlp.regex_classify
except Exception as e:
    print(f"Warning: Could not load local NLP regex module: {e}")
    _regex_classify = lambda x: (None, 0.0)

EDGE_SERVER_URL = "http://localhost:8000/api/v1/intent"

def call_llm_api(text):
    """Gọi API Edge Server để lấy intent bằng LLM"""
    try:
        response = requests.post(EDGE_SERVER_URL, json={"text": text, "use_llm_only": True}, timeout=5)
        if response.status_code == 200:
            return response.json().get('intent', 'UNKNOWN')
        return 'UNKNOWN'
    except:
        return 'UNKNOWN'

def evaluate(dataset_path: str, mode: str, out_csv: str):
    print(f"Loading dataset from: {dataset_path}")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f).get("data", [])

    total = len(data)
    if total == 0:
        print("Dataset is empty.")
        return

    correct = 0
    unknown = 0
    wrong = 0
    intent_metrics = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})

    print(f"Evaluating in {mode.upper()} mode...")

    for i, item in enumerate(data):
        text = item["clean_text"]
        true_intent = item.get("intent_auto") or item.get("intent_confirmed")

        if not true_intent:
            continue

        if mode == 'regex':
            predicted_intent, _ = _regex_classify(text)
        elif mode == 'llm':
            predicted_intent = call_llm_api(text)
        else:
            predicted_intent, _ = _regex_classify(text)
            if not predicted_intent:
                predicted_intent = call_llm_api(text)

        if predicted_intent == true_intent:
            correct += 1
            intent_metrics[true_intent]["TP"] += 1
        elif predicted_intent is None or predicted_intent == 'UNKNOWN':
            unknown += 1
            intent_metrics[true_intent]["FN"] += 1
        else:
            wrong += 1
            intent_metrics[true_intent]["FN"] += 1
            intent_metrics[predicted_intent]["FP"] += 1

    accuracy = correct / total
    print("\n" + "=" * 50)
    print(f"EVALUATION RESULTS ({mode.upper()})")
    print("=" * 50)
    print(f"Total samples: {total}")
    print(f"Correct: {correct}")
    print(f"Wrong: {wrong}")
    print(f"Unknown (Fallback needed): {unknown}")
    print(f"Accuracy: {accuracy * 100:.2f}%")
    print("\nDetailed Metrics by Intent:")
    
    results = []
    
    for intent, counts in sorted(intent_metrics.items()):
        tp = counts["TP"]
        fp = counts["FP"]
        fn = counts["FN"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        support = tp + fn

        if support > 0:
            print(f"{intent:<30} | {precision * 100:>6.2f}%    | {recall * 100:>6.2f}%    | {f1 * 100:>6.2f}%    | {support:>5}")
            results.append({
                "Mode": mode,
                "Intent": intent,
                "Precision": round(precision, 4),
                "Recall": round(recall, 4),
                "F1_Score": round(f1, 4),
                "Support": support
            })

    if out_csv and results:
        df = pd.DataFrame(results)
        df.to_csv(out_csv, index=False)
        print(f"\nSaved metrics to {out_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="../data/splits/val_unseen.json", help="Path to dataset JSON")
    parser.add_argument("--mode", type=str, choices=['regex', 'llm', 'cascade'], default='regex', help="Evaluation backend")
    parser.add_argument("--out_csv", type=str, default="nlp_eval_results.csv", help="Output CSV path")
    
    args = parser.parse_args()
    evaluate(args.dataset, args.mode, args.out_csv)
