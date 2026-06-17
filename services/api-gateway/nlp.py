"""
UAV NLP Pipeline
================
STT spell correction, intent classification via regex, entity extraction,
and compound command splitting.

All regex patterns are pre-compiled at module load for maximum performance.
"""
import re
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Intent classification — pre-compiled patterns
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("take_off",     re.compile(r"\b(cất cánh|bay lên|take off|takeoff|lift off|launch|take flight|depart)\b", re.IGNORECASE)),
    ("land",         re.compile(r"\b(hạ cánh|đáp xuống|land|landing|touch down|set down|descend and land)\b", re.IGNORECASE)),
    ("hover",        re.compile(r"\b(dừng lại|đứng yên|giữ vị trí|giữ nguyên|hover|hold position|hold altitude|stay in place|maintain (position|altitude)|wait here)\b", re.IGNORECASE)),
    ("stop",         re.compile(r"\b(dừng|ngừng|stop|halt|pause|freeze|cut engines)\b", re.IGNORECASE)),
    ("return_home",  re.compile(r"\b(quay về|về nhà|về điểm xuất phát|return (to )?home|go home|come back|rtl|return to base|fly back)\b", re.IGNORECASE)),
    ("move_forward", re.compile(r"\b(tiến|tới|bay tới|tiến tới trước|đi thẳng|bay thẳng|head|go|fly|move|proceed|continue|straight|forward)\b", re.IGNORECASE)),
    ("move_backward",re.compile(r"\b(lùi|bay lùi|lùi lại|backward|back)\b", re.IGNORECASE)),
    ("rotate_left",  re.compile(r"\b(xoay trái|quay trái|rotate left|turn left|spin left|yaw left)\b", re.IGNORECASE)),
    ("rotate_right", re.compile(r"\b(xoay phải|quay phải|rotate right|turn right|spin right|yaw right)\b", re.IGNORECASE)),
    ("move_left",    re.compile(r"\b(sang trái|bay sang trái|trái|left)\b", re.IGNORECASE)),
    ("move_right",   re.compile(r"\b(sang phải|bay sang phải|phải|right)\b", re.IGNORECASE)),
    ("ascend",       re.compile(r"\b(bay cao|nâng cao|lên cao|ascend|climb|rise|go up|fly up|move up|increase altitude|higher)\b", re.IGNORECASE)),
    ("descend",      re.compile(r"\b(bay thấp|hạ thấp|xuống thấp|descend|lower|go down|fly down|decrease altitude|fly lower)\b", re.IGNORECASE)),
    ("follow_target",re.compile(r"\b(bám theo|theo dõi|đuổi theo|follow|track|chase|pursue|trail|keep up with|stay with)\b", re.IGNORECASE)),
    ("get_battery",  re.compile(r"\b(hỏi pin|kiểm tra pin|xem pin|pin|battery|how much battery)\b", re.IGNORECASE)),
    ("get_altitude", re.compile(r"\b(hỏi độ cao|kiểm tra độ cao|độ cao|altitude|how high)\b", re.IGNORECASE)),
    ("ask_direction",re.compile(r"\b(which direction|what direction|where should i go|how to go|where.*go now)\b", re.IGNORECASE)),
    ("ask_destination_appearance", re.compile(r"\b(what.*destination look|how does.*destination|destination.*color|destination.*shape)\b", re.IGNORECASE)),
    ("ask_proximity",re.compile(r"\b(am i (near|close|at)|how far|am i (almost|nearly)|near the destination)\b", re.IGNORECASE)),
    ("ask_visibility",re.compile(r"\b(can i see|is.*in (my )?view|in.*field of view|is.*visible|do i see)\b", re.IGNORECASE)),
    ("ask_current_position", re.compile(r"\b(i am (on|at|in|near)|i('m| am) (on top|on the|at the)|i (move|moved|pass|passed|turn))\b", re.IGNORECASE)),
    ("orbit",        re.compile(r"\b(circle|orbit|fly around|loop around|go around|revolve)\b", re.IGNORECASE)),
    ("map_area",     re.compile(r"\b(map|scan|survey|cover the area|grid)\b", re.IGNORECASE)),
    ("spray_zone",   re.compile(r"\b(spray|sprinkle|dispense|fertiliz)\b", re.IGNORECASE)),
]

# ---------------------------------------------------------------------------
# Entity extraction — pre-compiled patterns
# ---------------------------------------------------------------------------

_RE_DIST_M   = re.compile(r"(\d+(?:\.\d+)?)\s*(mét|met|meter|metre|m)s?\b", re.IGNORECASE)
_RE_DIST_CM  = re.compile(r"(\d+)\s*(centimet|phân|centimeter|centimetre|cm)s?\b", re.IGNORECASE)
_RE_DIST_FT  = re.compile(r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)s?\b", re.IGNORECASE)
_RE_ANGLE    = re.compile(r"(\d+)\s*(độ|degree|deg|°)", re.IGNORECASE)
_RE_COMPASS  = re.compile(r"\b(north|south|east|west|northeast|northwest|southeast|southwest)\b", re.IGNORECASE)
_RE_CLOCK    = re.compile(r"\b(\d+)\s*['\u2019]?\s*o['\u2019]?\s*clock\b", re.IGNORECASE)
_RE_COLOR    = re.compile(r"\b(red|blue|green|yellow|white|black|orange|purple|brown|grey|gray|đỏ|xanh dương|xanh lá|vàng|trắng|đen)\b", re.IGNORECASE)
_RE_OBJ      = re.compile(r"\b(person|people|man|woman|car|bike|bicycle|building|road|bridge|field|area|người|xe hơi|ô tô|xe máy)\b", re.IGNORECASE)
_RE_SPEED    = re.compile(r"\b(chậm|từ từ|nhanh|slow|fast|quickly|slowly)\b", re.IGNORECASE)
_RE_COMPOUND = re.compile(r"\b(and then|then|and|sau đó|rồi|và)\b", re.IGNORECASE)

_COLOR_MAP = {
    "đỏ": "red", "xanh dương": "blue", "xanh lá": "green",
    "vàng": "yellow", "trắng": "white", "đen": "black",
}
_TARGET_MAP = {
    "người": "person", "xe hơi": "car", "ô tô": "car",
    "xe máy": "bike", "people": "person", "man": "person", "woman": "person",
}
_SPEED_MAP = {
    "chậm": "low", "từ từ": "low", "nhanh": "high",
    "slow": "low", "slowly": "low", "fast": "high", "quickly": "high",
}

# ---------------------------------------------------------------------------
# STT spell correction — pre-compiled patterns
# ---------------------------------------------------------------------------

_STT_CORRECTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btek of\b"),    "take off"),
    (re.compile(r"\btake of\b"),   "take off"),
    (re.compile(r"\btack off\b"),  "take off"),
    (re.compile(r"\blaning\b"),    "landing"),
    (re.compile(r"\blen\b"),       "land"),
    (re.compile(r"\bflay\b"),      "fly"),
    (re.compile(r"\bflye\b"),      "fly"),
    (re.compile(r"\bgo foward\b"), "go forward"),
    (re.compile(r"\bforwad\b"),    "forward"),
    (re.compile(r"\bstraigh\b"),   "straight"),
    (re.compile(r"\brighte\b"),    "right"),
    (re.compile(r"\brotat\b"),     "rotate"),
    (re.compile(r"\bterm left\b"), "turn left"),
    (re.compile(r"\bterm right\b"),"turn right"),
    (re.compile(r"\bhove\b"),      "hover"),
    (re.compile(r"\bhaver\b"),     "hover"),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def spell_correct(text: str) -> str:
    """Normalize common STT transcription errors."""
    result = text.lower()
    for pattern, replacement in _STT_CORRECTIONS:
        result = pattern.sub(replacement, result)
    return result


def regex_classify(text: str) -> Tuple[Optional[str], float]:
    """
    Classify intent using pre-compiled regex.
    Returns (intent_name, confidence) or (None, 0.0) on no match.
    Shorter commands (<= 8 words) receive slightly higher confidence (0.95 vs 0.85).
    """
    text_lower = text.lower().strip()
    for intent_name, pattern in _INTENT_PATTERNS:
        if pattern.search(text_lower):
            confidence = 0.95 if len(text_lower.split()) <= 8 else 0.85
            return intent_name, confidence
    return None, 0.0


def extract_entities(text: str, intent: Optional[str]) -> dict:
    """Extract structured entities from a command string."""
    entities: dict = {}
    t = text.lower()

    # Distance (metres → cm, cm, feet → cm)
    if m := _RE_DIST_M.search(t):
        entities["distance_cm"] = int(float(m.group(1)) * 100)
    elif m := _RE_DIST_CM.search(t):
        entities["distance_cm"] = int(m.group(1))
    elif m := _RE_DIST_FT.search(t):
        entities["distance_cm"] = int(float(m.group(1)) * 30.48)

    if m := _RE_ANGLE.search(t):
        entities["angle_deg"] = int(m.group(1))

    if m := _RE_COMPASS.search(t):
        entities["compass"] = m.group(1).lower()

    if m := _RE_CLOCK.search(t):
        entities["clock"] = int(m.group(1))

    if m := _RE_COLOR.search(t):
        c = m.group(1)
        entities["target_color"] = _COLOR_MAP.get(c, c)

    if m := _RE_OBJ.search(t):
        c = m.group(1)
        entities["target_class"] = _TARGET_MAP.get(c, c)

    if m := _RE_SPEED.search(t):
        entities["speed"] = _SPEED_MAP.get(m.group(1), "normal")

    return entities


def split_compound_commands(text: str) -> list[str]:
    """Split compound voice commands (joined by conjunctions) into a list of single commands."""
    _SEPARATORS = {"and then", "then", "and", "sau đó", "rồi", "và"}
    parts = _RE_COMPOUND.split(text)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in _SEPARATORS]
