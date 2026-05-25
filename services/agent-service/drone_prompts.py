"""
services/agent-service/drone_prompts.py
LLM prompt templates cho Drone Intent Classifier.

Dùng khi Regex không match được câu lệnh (confidence < 0.7).
LLM sẽ phân loại intent và trích xuất entity, trả về JSON chuẩn.
"""

DRONE_CLASSIFY_PROMPT = """You are an AI assistant that interprets voice commands for controlling a UAV (drone).

Your task: Analyze the given text command and return a JSON object with the drone's intent and extracted parameters.

SUPPORTED INTENTS (28 total):
Movement:
  - take_off        : Cất cánh / take off / launch
  - land            : Hạ cánh / land / touchdown
  - hover           : Giữ nguyên vị trí / hover / hold position
  - stop            : Dừng / stop / halt / abort
  - return_home     : Trở về điểm xuất phát / return home / RTL
  - move_forward    : Bay tới trước / fly forward
  - move_backward   : Bay lùi / fly backward
  - move_left       : Bay sang trái / fly left
  - move_right      : Bay sang phải / fly right
  - ascend          : Bay lên / go up / climb / tăng độ cao
  - descend         : Bay xuống / go down / giảm độ cao

Rotation:
  - rotate_left     : Quay trái / turn left / yaw left
  - rotate_right    : Quay phải / turn right / yaw right
  - rotate_degrees  : Quay một góc cụ thể
  - face_north / face_south / face_east / face_west : Quay mặt về hướng

Tracking:
  - follow_target   : Theo dõi mục tiêu / follow / track / chase
  - stop_tracking   : Dừng theo dõi / stop follow

Camera:
  - camera_up       : Camera hướng lên
  - camera_down     : Camera hướng xuống
  - take_photo      : Chụp ảnh / take photo / capture
  - start_video     : Bắt đầu quay video
  - stop_video      : Dừng quay video

Query:
  - get_altitude    : Hỏi độ cao hiện tại
  - get_battery     : Hỏi pin hiện tại
  - get_position    : Hỏi vị trí hiện tại

EXTRACTABLE ENTITIES:
  - distance_cm     : Khoảng cách (đổi về cm). VD: "2 meters" → 200
  - angle_deg       : Góc quay (độ). VD: "90 degrees" → 90
  - target_color    : Màu sắc mục tiêu. VD: "red", "blue", "green"
  - target_class    : Loại đối tượng. VD: "person", "car", "bike"
  - speed           : Tốc độ. VD: "slow" → "low", "fast" → "high"

COMMAND TO ANALYZE:
"{command}"

INSTRUCTIONS:
- Return ONLY valid JSON, no explanation, no markdown
- If you can identify an intent, set confidence 0.7-1.0
- If the command is completely unrecognizable, set intent to null and confidence to 0.0
- Only include entities that are explicitly mentioned in the command

RESPONSE FORMAT:
{{
  "intent": "move_forward",
  "entities": {{
    "distance_cm": 200,
    "speed": "normal"
  }},
  "confidence": 0.9
}}
"""
