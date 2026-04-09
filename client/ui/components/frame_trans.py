# from PyQt6.QtCore import Qt, QTimer
# from PyQt6.QtWidgets import (
#     QWidget, QVBoxLayout, QHBoxLayout, QLabel,
#     QScrollArea, QSizePolicy, QTextEdit,
# )

# from client.ui.components.helpers import card, label


# class FrameTrans(QWidget):
#     """Tab Dịch — hiển thị subtitle EN/VI + outbound log."""

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self._inbound_only = False
#         self._build()

#     # ── Build ─────────────────────────────────────────────────────────────────

#     def _build(self):
#         lay = QVBoxLayout(self)
#         lay.setContentsMargins(0, 0, 0, 0)
#         lay.setSpacing(0)

#         # ── Scroll area ──
#         self._scroll = QScrollArea()
#         self._scroll.setWidgetResizable(True)
#         self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
#         self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

#         inner = QWidget()
#         inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
#         self._trans_lay = QVBoxLayout(inner)
#         self._trans_lay.setContentsMargins(14, 14, 14, 14)
#         self._trans_lay.setSpacing(8)
#         self._trans_lay.addStretch()

#         # Live card (luôn cuối cùng)
#         self._live_card = card("trans_item_live")
#         live_lay = QVBoxLayout(self._live_card)
#         live_lay.setContentsMargins(10, 8, 10, 8)
#         live_lay.setSpacing(3)
#         self._live_label = label("● Đang nghe…", "trans_listening")
#         live_lay.addWidget(self._live_label)
#         self._trans_lay.addWidget(self._live_card)

#         self._scroll.setWidget(inner)
#         lay.addWidget(self._scroll, 1)

#         # ── Separator ──
#         sep = QWidget()
#         sep.setFixedHeight(1)
#         sep.setStyleSheet("background: rgba(0,229,160,0.2);")
#         lay.addWidget(sep)

#         # ── Outbound log ──
#         # log_wrap = QWidget()
#         # log_wrap.setStyleSheet("background: #f7fdfb;")
#         # lw_lay = QVBoxLayout(log_wrap)
#         # lw_lay.setContentsMargins(14, 8, 14, 8)
#         # lw_lay.setSpacing(4)
#         # lw_lay.addWidget(label("ĐÃ ĐẨY VÀO MEET", "section_label"))
#         self._outbound_log = QTextEdit()
#         self._outbound_log.setObjectName("outbound_log")
#         self._outbound_log.setReadOnly(True)
#         self._outbound_log.setFixedHeight(72)
#         # lw_lay.addWidget(self._outbound_log)
#         # lay.addWidget(log_wrap)

#     # ── Public API ────────────────────────────────────────────────────────────

#     def set_inbound_only(self, value: bool):
#         self._inbound_only = value
#         self._outbound_log.setVisible(not value)

#     def add_trans_item(self, src: str, dst: str, latency_ms: float = 0.0):
#         """Thêm một bubble dịch vào scroll area."""
#         item = card("trans_item")
#         item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
#         lay = QVBoxLayout(item)
#         lay.setContentsMargins(10, 8, 10, 8)
#         lay.setSpacing(3)

#         if src:
#             src_lbl = label(f"EN · \"{src}\"", "trans_src")
#             src_lbl.setWordWrap(True)
#             src_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
#             lay.addWidget(src_lbl)

#         dst_lbl = label(f"<i>{dst}</i>", "trans_dst")
#         dst_lbl.setTextFormat(Qt.TextFormat.RichText)  # 🔥 QUAN TRỌNG
#         dst_lbl.setWordWrap(True)
#         dst_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
#         lay.addWidget(dst_lbl)

#         if latency_ms:
#             badge = label(f"▶ {latency_ms:.0f}ms", "trans_badge")
#             badge.setAlignment(Qt.AlignmentFlag.AlignRight)
#             lay.addWidget(badge)

#         # Chèn trước stretch + live card (2 item cuối)
#         idx = self._trans_lay.count() - 2
#         self._trans_lay.insertWidget(idx, item)

#         QTimer.singleShot(50, self._scroll_to_bottom)

#     def append_outbound_log(self, text: str):
#         self._outbound_log.append(f"→ {text}")
#         sb = self._outbound_log.verticalScrollBar()
#         if sb:
#             sb.setValue(sb.maximum())

#     def clear(self):
#         """Xoá toàn bộ bubble (giữ lại live card)."""
#         lay = self._trans_lay
#         # Xoá tất cả ngoại trừ stretch (idx 0) và live card (idx cuối)
#         for i in range(lay.count() - 2, 0, -1):
#             item = lay.takeAt(i)
#             if item and item.widget():
#                 item.widget().deleteLater()
#         self._outbound_log.clear()

#     # ── Private ───────────────────────────────────────────────────────────────

#     def _scroll_to_bottom(self):
#         sb = self._scroll.verticalScrollBar()
#         if sb:
#             sb.setValue(sb.maximum())



from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QTextEdit,
)

from client.ui.components.helpers import card, label


class FrameTrans(QWidget):
    """Tab Dịch — hiển thị subtitle EN/VI + outbound log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inbound_only = False
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Scroll area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._trans_lay = QVBoxLayout(inner)
        self._trans_lay.setContentsMargins(14, 14, 14, 14)
        self._trans_lay.setSpacing(10)
        self._trans_lay.addStretch()

        # ── Live card (realtime listening) ──
        self._live_card = card("trans_item_live")
        live_lay = QVBoxLayout(self._live_card)
        live_lay.setContentsMargins(10, 8, 10, 8)

        self._live_label = label("● Đang nghe…", "trans_listening")
        self._live_label.setWordWrap(True)

        live_lay.addWidget(self._live_label)
        self._trans_lay.addWidget(self._live_card)

        self._scroll.setWidget(inner)
        lay.addWidget(self._scroll, 1)

        # ── Separator ──
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,229,160,0.2);")
        lay.addWidget(sep)

        # ── Outbound log ──
        self._outbound_log = QTextEdit()
        self._outbound_log.setObjectName("outbound_log")
        self._outbound_log.setReadOnly(True)
        self._outbound_log.setFixedHeight(72)
        self._outbound_log.setVisible(False)  # mặc định ẩn
        lay.addWidget(self._outbound_log)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_inbound_only(self, value: bool):
        self._inbound_only = value
        self._outbound_log.setVisible(not value)

    def add_trans_item(self, src: str, dst: str, latency_ms: float = 0.0):
        # print("SRC:", src)
        # print("DST:", dst)
        # """Hiển thị 1 subtitle item (gốc + dịch)."""

        # item = card("trans_item")
        # item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # lay = QVBoxLayout(item)
        # lay.setContentsMargins(10, 8, 10, 8)
        # lay.setSpacing(4)

        # # ── Gộp src + dst vào 1 QLabel (HTML) ──
        # html = '<div style="line-height:1.4;">'

        # if src:
        #     html += f'<span style="color:#aaa;">EN · "{src}"</span><br>'

        # html += f'<span style="font-style:italic; color:#00e5a0;">{dst}</span>'
        # html += '</div>'

        # txt = QLabel()
        # txt.setText(html)
        # txt.setTextFormat(Qt.TextFormat.RichText)
        # txt.setWordWrap(True)
        # txt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # lay.addWidget(txt)

        # # ── latency badge ──
        # if latency_ms:
        #     badge = label(f"▶ {latency_ms:.0f}ms", "trans_badge")
        #     badge.setAlignment(Qt.AlignmentFlag.AlignRight)
        #     lay.addWidget(badge)

        # # ── insert vào trước live card ──
        # idx = self._trans_lay.count() - 2
        # self._trans_lay.insertWidget(idx, item)

        # QTimer.singleShot(30, self._scroll_to_bottom)


        item = card("trans_item")
        lay = QVBoxLayout(item)
        lay.setContentsMargins(10, 8, 10, 8)

        if src:
            src_lbl = label(src, "trans_src")
            src_lbl.setWordWrap(True)
            lay.addWidget(src_lbl)

        dst_lbl = label(f"<i>{dst}</i>", "trans_dst")
        dst_lbl.setTextFormat(Qt.TextFormat.RichText)
        dst_lbl.setWordWrap(True)
        lay.addWidget(dst_lbl)

        if latency_ms:
            badge = label(f"{latency_ms:.0f}ms", "trans_badge")
            lay.addWidget(badge)

        idx = self._trans_lay.count() - 2
        self._trans_lay.insertWidget(idx, item)

        QTimer.singleShot(50, self._scroll_to_bottom)

    def update_live_text(self, text: str):
        """Update realtime text (ASR streaming)."""
        if not text.strip():
            self._live_label.setText("● Đang nghe…")
            return

        html = f'<span style="color:#888;">🎧 {text}</span>'
        self._live_label.setText(html)
        self._live_label.setTextFormat(Qt.TextFormat.RichText)

    def append_outbound_log(self, text: str):
        self._outbound_log.append(f"→ {text}")
        sb = self._outbound_log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def clear(self):
        lay = self._trans_lay

        # Xoá tất cả trừ stretch + live card
        for i in range(lay.count() - 2, 0, -1):
            item = lay.takeAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        self._outbound_log.clear()

    # ── Private ───────────────────────────────────────────────────────────────

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())