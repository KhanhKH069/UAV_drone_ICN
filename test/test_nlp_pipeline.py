import os
import sys
import pytest

# Cấu hình sys.path để import đúng các hàm từ api-gateway
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../services/api-gateway"))
)
from routers.drone import (
    _spell_correct_stt,
    _split_compound_commands,
    _regex_classify,
    _extract_entities,
)


# ---------------------------------------------------------
# 1. Test Khử Nhiễu STT (_spell_correct_stt)
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("tek of right now", "take off right now"),
        ("laning on the pad", "landing on the pad"),
        ("term left and go foward", "turn left and go forward"),
        ("flay straigh", "fly straight"),
        ("hove here", "hover here"),
        ("normal command", "normal command"),  # Không có lỗi
    ],
)
def test_spell_correct_stt(input_text, expected):
    assert _spell_correct_stt(input_text) == expected


# ---------------------------------------------------------
# 2. Test Cắt Câu Ghép (_split_compound_commands)
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "input_text, expected",
    [
        (
            "fly forward 2 meters and then turn left",
            ["fly forward 2 meters", "turn left"],
        ),
        ("take off and land", ["take off", "land"]),
        ("go straight sau đó turn right", ["go straight", "turn right"]),
        ("hover", ["hover"]),  # Câu đơn
    ],
)
def test_split_compound_commands(input_text, expected):
    assert _split_compound_commands(input_text) == expected


# ---------------------------------------------------------
# 3. Test Regex Intent (_regex_classify)
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "input_text, expected_intent, expected_min_conf",
    [
        ("take off", "take_off", 0.95),
        ("land right now", "land", 0.95),
        ("hover", "hover", 0.95),
        ("stop the engines", "stop", 0.95),
        ("return to home", "return_home", 0.95),
        ("turn 90 degrees", None, 0.0),
        ("fly forward 5 meters", "move_forward", 0.95),  # move_forward matches "fly"
        ("head north", "move_forward", 0.85),
        ("turn left", "rotate_left", 0.95),
        ("turn right", "rotate_right", 0.95),
        (
            "this is a random long sentence that does not match any regex intent",
            None,
            0.0,
        ),
    ],
)
def test_regex_classify(input_text, expected_intent, expected_min_conf):
    intent, conf = _regex_classify(input_text)
    assert intent == expected_intent
    if intent is not None:
        assert conf >= expected_min_conf


# ---------------------------------------------------------
# 4. Test Trích Xuất Thực Thể (_extract_entities)
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "input_text, intent, expected_entities",
    [
        ("fly forward 2 meters", "move_forward", {"distance_cm": 200}),
        ("fly 50 cm", "move_forward", {"distance_cm": 50}),
        ("go 10 feet", "move_forward", {"distance_cm": 304}),  # 10 * 30.48 = 304
        ("turn 90 degrees", "rotate_left", {"angle_deg": 90}),
        ("head north", "move_forward", {"compass": "north"}),
        ("go 2 o'clock", "move_forward", {"clock": 2}),
        (
            "look for a red car",
            "follow_target",
            {"target_color": "red", "target_class": "car"},
        ),
        ("fly fast", "move_forward", {"speed": "high"}),
        ("move slowly", "move_forward", {"speed": "low"}),
        ("take off", "take_off", {}),  # Không có entity
    ],
)
def test_extract_entities(input_text, intent, expected_entities):
    entities = _extract_entities(input_text, intent)
    assert entities == expected_entities
