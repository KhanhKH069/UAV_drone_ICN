import json
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report
import os

def evaluate_predictions(json_results_path):
    """
    json_results_path: File JSON chứa mảng các dict
    [
      {"text": "bay lên", "true_intent": "take_off", "pred_intent": "take_off"},
      ...
    ]
    """
    if not os.path.exists(json_results_path):
        print(f"Không tìm thấy file {json_results_path}. Hãy chạy benchmark để tạo file này trước.")
        return

    with open(json_results_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    y_true = [item['true_intent'] for item in data]
    y_pred = [item.get('pred_intent', 'unknown') for item in data]

    labels = sorted(list(set(y_true + y_pred)))

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    
    print("=== BÁO CÁO PHÂN LOẠI (CLASSIFICATION REPORT) ===")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=labels, yticklabels=labels)
    plt.title('Confusion Matrix - Intent Classification')
    plt.ylabel('True Intent')
    plt.xlabel('Predicted Intent')
    plt.tight_layout()
    plt.savefig('confusion_matrix.png')
    print("Đã lưu hình ảnh Confusion Matrix tại confusion_matrix.png")

if __name__ == "__main__":
    evaluate_predictions("dataset_eval_results.json")
