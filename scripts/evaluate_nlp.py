import sys
import os
import json
from collections import defaultdict

import importlib.util


def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


drone_module_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "services",
        "api-gateway",
        "routers",
        "drone.py",
    )
)
drone = load_module_from_path("drone", drone_module_path)
_regex_classify = drone._regex_classify


def evaluate_regex(dataset_path: str):
    print(f"Loading dataset from: {dataset_path}")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)["data"]

    total = len(data)
    correct = 0
    unknown = 0
    wrong = 0

    intent_metrics = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0})

    for item in data:
        text = item["clean_text"]
        true_intent = item.get("intent_auto") or item.get("intent_confirmed")

        # Regex Tầng 1
        predicted_intent, conf = _regex_classify(text)

        if not true_intent:
            continue

        if predicted_intent == true_intent:
            correct += 1
            intent_metrics[true_intent]["TP"] += 1
        elif predicted_intent is None:
            unknown += 1
            intent_metrics[true_intent]["FN"] += 1
        else:
            wrong += 1
            intent_metrics[true_intent]["FN"] += 1
            intent_metrics[predicted_intent]["FP"] += 1

    accuracy = correct / total
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS (Tier 1 Regex)")
    print("=" * 50)
    print(f"Total samples: {total}")
    print(f"Correct: {correct}")
    print(f"Wrong: {wrong}")
    print(f"Unknown (Fallback needed): {unknown}")
    print(f"Accuracy: {accuracy * 100:.2f}%")
    print("\nDetailed Metrics by Intent:")
    print(
        f"{'Intent':<30} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Support'}"
    )
    print("-" * 80)

    for intent, counts in sorted(intent_metrics.items()):
        tp = counts["TP"]
        fp = counts["FP"]
        fn = counts["FN"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )
        support = tp + fn

        if support > 0:
            print(
                f"{intent:<30} | {precision * 100:>6.2f}%    | {recall * 100:>6.2f}%    | {f1 * 100:>6.2f}%    | {support:>5}"
            )


if __name__ == "__main__":
    dataset_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "dataaaa",
        "nlp_intent_corpus_v21_train_ready.json",
    )
    evaluate_regex(dataset_file)
