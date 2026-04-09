from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
)

from client.ui.components.helpers import card, label


class FrameMinutes(QWidget):
    """Tab Biên bản — hiển thị tóm tắt và action items sau cuộc họp."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(14, 14, 14, 14)
        self._inner_lay.setSpacing(10)

        # Placeholder
        ph = label("Biên bản họp sẽ hiện ở đây sau khi kết thúc phiên.", "trans_src")
        ph.setWordWrap(True)
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inner_lay.addStretch()
        self._inner_lay.addWidget(ph)
        self._inner_lay.addStretch()
        self._placeholder = ph

        scroll.setWidget(self._inner)
        lay.addWidget(scroll, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def populate(self, data: dict):
        """Điền nội dung biên bản từ dict trả về server."""
        # Ẩn placeholder
        if self._placeholder:
            self._placeholder.hide()

        lay = self._inner_lay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Tóm tắt
        lay.addWidget(label("TÓM TẮT NỘI DUNG", "section_label"))
        summary_card = card("minutes_body")
        sc_lay = QVBoxLayout(summary_card)
        sc_lay.setContentsMargins(10, 8, 10, 8)
        summary_lbl = label(data.get("summary", ""), "chat_text")
        summary_lbl.setWordWrap(True)
        sc_lay.addWidget(summary_lbl)
        lay.addWidget(summary_card)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,229,160,0.2);")
        lay.addWidget(sep)

        # Action items
        if data.get("action_items"):
            lay.addWidget(label("HÀNH ĐỘNG CẦN LÀM", "section_label"))
            for item in data["action_items"]:
                self._add_action_item(lay, item)

        lay.addStretch()

    def clear(self):
        lay = self._inner_lay
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self._placeholder:
            self._placeholder.show()
            lay.addStretch()
            lay.addWidget(self._placeholder)
            lay.addStretch()

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_action_item(self, parent_lay, item: dict):
        ai = card("action_item")
        ai_lay = QHBoxLayout(ai)
        ai_lay.setContentsMargins(10, 8, 10, 8)
        ai_lay.setSpacing(8)

        pri = item.get("priority", "med").lower()
        pri_lbl = label(
            "CAO" if pri == "high" else "VỪA",
            "pri_high" if pri == "high" else "pri_med",
        )
        ai_lay.addWidget(pri_lbl, 0, Qt.AlignmentFlag.AlignTop)

        txt_col = QVBoxLayout()
        txt_col.setSpacing(2)
        task_lbl = label(item.get("task", ""), "chat_text")
        task_lbl.setWordWrap(True)
        who_lbl = label(f"→ {item.get('assignee', '?')}", "trans_src")
        txt_col.addWidget(task_lbl)
        txt_col.addWidget(who_lbl)
        ai_lay.addLayout(txt_col)

        parent_lay.addWidget(ai)