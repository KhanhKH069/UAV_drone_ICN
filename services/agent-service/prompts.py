SUMMARY_PROMPT = """Bạn là trợ lý AI tóm tắt biên bản họp chuyên nghiệp cho công ty VMG.

Nội dung cuộc họp (đã dịch sang tiếng Việt):
---
{transcript}
---

Hãy viết:
1. Một đoạn tóm tắt TỔNG QUAN (2-3 câu) về mục tiêu và kết quả cuộc họp.
2. Các ĐIỂM CHÍNH được thảo luận (dạng danh sách, mỗi điểm bắt đầu bằng "- ").

Yêu cầu: Ngắn gọn, chuyên nghiệp, tiếng Việt.
"""

ACTION_ITEMS_PROMPT = """Bạn là trợ lý AI phân tích cuộc họp cho công ty VMG.

Nội dung cuộc họp:
---
{transcript}
---

Hãy trích xuất tất cả CÔNG VIỆC CẦN THỰC HIỆN (Action Items) được đề cập.

Trả về CHỈ JSON theo định dạng sau (không có text khác, không có markdown):
[
  {{
    "task": "Mô tả công việc cụ thể",
    "assignee": "Tên người/team phụ trách hoặc null",
    "deadline": "Thời hạn như '2 tuần', 'thứ 6 tới', 'Q2' hoặc null",
    "priority": "high"
  }}
]

Nếu không có action item nào: trả về []
"""
