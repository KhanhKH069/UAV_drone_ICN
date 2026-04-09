from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QImage

from client.ui.components.helpers import card, label


class ImagePanel(QWidget):
    """Tab Slide — paste ảnh, chọn ngôn ngữ nguồn, dịch OCR."""

    translate_requested = pyqtSignal(object, str)   # (PIL.Image, src_lang)

    _LANGUAGES = [
        ("Tiếng Anh",   "eng_Latn"),
        ("Tiếng Nhật",  "jpn_Jpan")
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pil_img = None
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # ── Toolbar: ngôn ngữ + nút dịch ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        lang_lbl = label("Ngôn ngữ nguồn:", "section_label")
        toolbar.addWidget(lang_lbl)

        self._combo_lang = QComboBox()
        self._combo_lang.setStyleSheet("""
            QComboBox {
                background: #f7fdfb;
                border: 1px solid rgba(0,229,160,0.4);
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 11px;
                color: #111;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #fff;
                border: 1px solid rgba(0,229,160,0.4);
                selection-background-color: #e6fff5;
                font-size: 11px;
            }
        """)
        for name, code in self._LANGUAGES:
            self._combo_lang.addItem(name, code)
        toolbar.addWidget(self._combo_lang)
        toolbar.addStretch()

        self._btn_translate = QPushButton("Dịch →")
        self._btn_translate.setStyleSheet("""
            QPushButton {
                background: #00e5a0; border: none; border-radius: 7px;
                color: #111; font-size: 11px; font-weight: 800;
                padding: 5px 14px;
            }
            QPushButton:hover { background: #00c88c; }
            QPushButton:disabled { background: #ccc; color: #888; }
        """)
        self._btn_translate.setEnabled(False)
        self._btn_translate.clicked.connect(self._on_translate_clicked)
        toolbar.addWidget(self._btn_translate)
        lay.addLayout(toolbar)

        # ── Drop zone ──
        self._drop_zone = card("slide_drop")
        self._drop_zone.setMinimumHeight(140)
        self._drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dz_lay = QVBoxLayout(self._drop_zone)
        dz_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_lay.setSpacing(8)

        ico = QLabel("🖼")
        ico.setStyleSheet("font-size: 28px; background: transparent; border: none;")
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_lay.addWidget(ico)

        hint = label("Ctrl+V để paste ảnh slide", "slide_hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_lay.addWidget(hint)

        sub = label("PNG, JPG · OCR đa ngôn ngữ", "trans_src")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_lay.addWidget(sub)

        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet("background: transparent; border: none;")
        self._preview_lbl.hide()
        dz_lay.addWidget(self._preview_lbl)

        lay.addWidget(self._drop_zone, 1)

        # ── Result area ──
        self._result_card = card("slide_result")
        self._result_card.hide()
        rc_lay = QVBoxLayout(self._result_card)
        rc_lay.setContentsMargins(12, 10, 12, 10)
        rc_lay.setSpacing(6)

        rc_lay.addWidget(label("KẾT QUẢ DỊCH", "section_label"))

        self._result_lbl = QLabel()
        self._result_lbl.setObjectName("chat_text")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        rc_lay.addWidget(self._result_lbl)

        btn_clear = QPushButton("✕  Xoá")
        btn_clear.setStyleSheet("""
            QPushButton {
                background: transparent; border: 1px solid rgba(0,229,160,0.3);
                border-radius: 6px; color: #999; font-size: 10px; padding: 4px 10px;
            }
            QPushButton:hover { border-color: #00e5a0; color: #00a875; }
        """)
        btn_clear.setFixedWidth(70)
        btn_clear.clicked.connect(self._clear)
        rc_lay.addWidget(btn_clear, 0, Qt.AlignmentFlag.AlignRight)

        lay.addWidget(self._result_card)

        # ── Status ──
        self._status_lbl = label("", "trans_src")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.hide()
        lay.addWidget(self._status_lbl)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_input(self, pil_img):
        """Hiển thị ảnh preview trong drop zone."""
        self._pil_img = pil_img
        self._result_card.hide()

        # Convert PIL → QPixmap để preview
        try:
            import io
            from PyQt6.QtCore import QByteArray
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            ba = QByteArray(buf.getvalue())
            qimg = QImage.fromData(ba)
            px = QPixmap.fromImage(qimg).scaled(
                260, 120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_lbl.setPixmap(px)
            self._preview_lbl.show()
        except Exception:
            self._preview_lbl.hide()

        self._btn_translate.setEnabled(True)
        self._set_status("🖼  Ảnh đã tải — bấm Dịch →")

    def show_result(self, pil_img):
        """Gọi khi dịch thành công — hiển thị ảnh kết quả."""
        self._set_status("")
        self._result_card.show()
        try:
            import io
            from PyQt6.QtCore import QByteArray
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            ba = QByteArray(buf.getvalue())
            qimg = QImage.fromData(ba)
            px = QPixmap.fromImage(qimg).scaled(
                300, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._result_lbl.setPixmap(px)
        except Exception as e:
            self._result_lbl.setText(f"[Lỗi hiển thị: {e}]")

    def show_error(self, msg: str):
        """Gọi khi dịch thất bại."""
        self._set_status(f"❌ {msg}")
        self._btn_translate.setEnabled(True)

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_translate_clicked(self):
        if self._pil_img is None:
            return
        self._btn_translate.setEnabled(False)
        self._set_status("⏳ Đang nhận diện & dịch…")
        src_lang = self._combo_lang.currentData()
        self.translate_requested.emit(self._pil_img, src_lang)

    def _clear(self):
        self._pil_img = None
        self._preview_lbl.hide()
        self._result_card.hide()
        self._btn_translate.setEnabled(False)
        self._set_status("")

    def _set_status(self, msg: str):
        if msg:
            self._status_lbl.setText(msg)
            self._status_lbl.show()
        else:
            self._status_lbl.hide()