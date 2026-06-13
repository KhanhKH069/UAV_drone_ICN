# Baseline Comparison cho UAV Voice Control

Tài liệu này hướng dẫn cách chạy benchmark và so sánh 3 baseline cho quá trình trích xuất Intent điều khiển bay từ văn bản (Audio -> Text -> Intent).

## 3 Baselines cần so sánh

1. **Regex-only (Baseline 1)**: Nhanh nhất (< 5ms), chạy offline trên CPU nhẹ, độ chính xác cao đối với các lệnh rập khuôn.
2. **LLM-only (Baseline 2)**: Chậm nhất (~1000-2000ms), linh hoạt với các lệnh không theo khuôn mẫu nhưng tốn GPU và overhead lớn.
3. **Cascade Regex → LLM (Hệ thống v2.0 hiện tại)**: Mô hình lai. Cố gắng match bằng Regex trước, nếu không được mới fallback qua LLM. Tối ưu thời gian và hiệu suất.

## Cách thực hiện đánh giá (Ablation Study)

### Bước 1: Chuẩn bị Dataset
1. Chạy file `scripts/research/collect_dataset.py` để thu âm các lệnh đa dạng (có thể từ nhiều phi công khác nhau).
2. Chuẩn bị 1 file JSON chứa Text chuẩn và True Intent (ground truth) (vd: `dataset_text_only.json`).

### Bước 2: Chạy Benchmark cho Regex-only
Viết 1 script nhỏ sử dụng module `regex_parser` của dự án (nếu đã bóc tách từ LLM prompt). Đo Latency và Accuracy trên toàn tập test.

### Bước 3: Chạy Benchmark cho LLM-only
Chạy tập test thẳng vào API `/drone/classify` nhưng **tắt bộ nhớ cache** và **tắt Regex check**. Ghi nhận Response Time trung bình.

### Bước 4: Chạy Benchmark cho Cascade (Default)
Chạy tập test qua `/drone/classify` với kiến trúc hiện tại.

## Báo cáo (Dự kiến)

Sau khi có kết quả từ `eval_confusion_matrix.py`, lập bảng so sánh vào báo cáo cuối cùng:

| Phương pháp | Accuracy (F1) | Mean Latency (ms) | Tài nguyên |
|---|---|---|---|
| Regex-only | ~ 60-70% (kém linh hoạt) | < 5 | CPU |
| LLM-only | ~ 90-95% | 1500 | GPU |
| **Cascade** | **~ 90-95%** | **~ 100-300** | GPU/CPU kết hợp |

Kết quả sẽ chứng minh kiến trúc Cascade của v2.0 là thiết kế tối ưu nhất cho bài toán UAV Edge AI, khi phần lớn các lệnh bay cơ bản đều có cấu trúc tương đối cố định (lợi dụng tốc độ siêu nhanh của Regex).
