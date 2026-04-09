"""
client/ui/components/frame_chat.py
Tab Chat — cho phép người dùng:
  1. Gõ text → dịch → đẩy lên Meet chat
  2. Ghi âm giọng nói → STT (whisperlive-wrapper service port 8001) → dịch → đẩy lên Meet chat
"""
import base64
import logging
import os
from typing import Optional

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QSizePolicy, QTextEdit, QPushButton, QLabel, QComboBox,
)

from client.ui.components.helpers import card, label

logger = logging.getLogger("paraline.chat")

SAMPLE_RATE = 16_000  # Hz — Whisper yêu cầu 16kHz

# URL của whisperlive-wrapper service (đã chạy sẵn trong Docker)
ASR_URL = os.getenv("PARALINE_ASR_URL", "http://localhost:8001/transcribe")


# ── STT Worker ───────────────────────────────────────────────────────────────

class WhisperSTTWorker(QThread):
    """
    Gọi whisperlive-wrapper service (faster-whisper hoặc qwen) qua REST.
    POST http://localhost:8001/transcribe
      body: { audio_b64: <base64 float32>, language: "auto", vad_filter: true }
    """
    transcribed = pyqtSignal(str)   # kết quả STT
    error       = pyqtSignal(str)   # thông báo lỗi

    def __init__(self, audio: np.ndarray, language: str = "auto", parent=None):
        super().__init__(parent)
        self._audio    = audio      # float32 PCM 16kHz mono
        self._language = language

    def run(self):
        try:
            import requests
            audio_b64 = base64.b64encode(self._audio.tobytes()).decode("utf-8")
            resp = requests.post(
                ASR_URL,
                json={
                    "audio_b64":  audio_b64,
                    "language":   self._language,
                    "sample_rate": SAMPLE_RATE,
                    "vad_filter": True,
                },
                timeout=30,
            )
            if not resp.ok:
                self.error.emit(f"❌ ASR service lỗi {resp.status_code}: {resp.text[:120]}")
                return
            text = resp.json().get("text", "").strip()
            if text:
                self.transcribed.emit(text)
            else:
                self.error.emit("⚠️ Không nhận được âm thanh rõ ràng.")
        except Exception as e:
            logger.exception("STT REST error")
            self.error.emit(f"❌ Không kết nối được ASR service: {e}")


# ── Frame Chat ────────────────────────────────────────────────────────────────

class FrameChat(QWidget):
    """
    Tab Chat — hiển thị tin nhắn + cho phép người dùng gửi.

    Luồng 1 (Text):
        người dùng gõ → bấm Gửi → emit send_requested(text) → main_window
        → translation REST → meet_client.send_raw()

    Luồng 2 (Voice):
        bấm 🎤 → ghi âm sounddevice → bấm ⏹ → WhisperSTTWorker
        → kết quả đổ vào ô nhập → emit send_requested(text) tự động
    """

    # Tín hiệu đẩy lên main_window
    send_requested    = pyqtSignal(str, str)  # (original_text, src_lang_code)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._stt_worker: Optional[WhisperSTTWorker] = None
        self._build()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Scroll area ──────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll = scroll

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._chat_lay = QVBoxLayout(inner)
        self._chat_lay.setContentsMargins(14, 14, 14, 14)
        self._chat_lay.setSpacing(8)
        self._chat_lay.addStretch()

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,229,160,0.2);")
        lay.addWidget(sep)

        # ── Input bar ────────────────────────────────────────────────────────
        bar = card("chat_input_bar")
        bar_lay = QVBoxLayout(bar)
        bar_lay.setContentsMargins(10, 8, 10, 8)
        bar_lay.setSpacing(6)

        # Hàng 1: src lang selector + status label
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        src_lbl = label("NGUỒN:", "chat_input_label")
        top_row.addWidget(src_lbl)

        self._combo_src = QComboBox()
        self._combo_src.setObjectName("combo_src_lang")
        self._combo_src.addItem("🇻🇳 Tiếng Việt", "vie_Latn")
        self._combo_src.addItem("🇺🇸 English",    "eng_Latn")
        self._combo_src.addItem("🇯🇵 Japanese",   "jpn_Jpan")
        self._combo_src.setFixedHeight(26)
        top_row.addWidget(self._combo_src)
        top_row.addStretch()

        self._status_lbl = label("", "chat_input_status")
        self._status_lbl.setVisible(False)
        top_row.addWidget(self._status_lbl)

        bar_lay.addLayout(top_row)

        # Hàng 2: text input
        self._text_input = QTextEdit()
        self._text_input.setObjectName("chat_input")
        self._text_input.setPlaceholderText("Nhập tin nhắn muốn dịch rồi gửi…")
        self._text_input.setFixedHeight(68)
        self._text_input.setAcceptRichText(False)
        bar_lay.addWidget(self._text_input)

        # Hàng 3: mic + send buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_mic = QPushButton("🎤  Ghi âm")
        self._btn_mic.setObjectName("btn_mic")
        self._btn_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mic.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self._btn_mic, 2)

        self._btn_send = QPushButton("Gửi →")
        self._btn_send.setObjectName("btn_send")
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._on_send_clicked)
        btn_row.addWidget(self._btn_send, 3)

        bar_lay.addLayout(btn_row)
        lay.addWidget(bar)

    # ── Public API ───────────────────────────────────────────────────────────

    def add_bubble(self, who: str, text: str, outbound: bool = False):
        """Thêm một chat bubble vào danh sách."""
        item = card("chat_bubble_out" if outbound else "chat_bubble")
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(item)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        who_lbl = label(who.upper(), "chat_who_me" if outbound else "chat_who")
        lay.addWidget(who_lbl)

        txt = label(text, "chat_text")
        txt.setWordWrap(True)
        txt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(txt)

        idx = self._chat_lay.count() - 1
        self._chat_lay.insertWidget(idx, item)

        QTimer.singleShot(50, self._scroll_to_bottom)

    def clear(self):
        lay = self._chat_lay
        for i in range(lay.count() - 1, 0, -1):
            item = lay.takeAt(i)
            if item and item.widget():
                item.widget().deleteLater()

    # ── Send logic ───────────────────────────────────────────────────────────

    def _on_send_clicked(self):
        text = self._text_input.toPlainText().strip()
        if not text:
            return
        src_lang = self._combo_src.currentData() or "vie_Latn"
        self._text_input.clear()
        self.send_requested.emit(text, src_lang)

    # ── Voice recording logic ─────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        self._audio_chunks = []
        self._recording = True

        self._btn_mic.setText("⏹  Dừng")
        self._btn_mic.setObjectName("btn_mic_active")
        self._refresh_button_style(self._btn_mic)
        self._set_status("🔴 Đang ghi âm…", visible=True)

        def _audio_cb(indata, frames, time_info, status):
            if self._recording:
                self._audio_chunks.append(indata[:, 0].copy())

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=_audio_cb,
                blocksize=1024,
            )
            self._stream.start()
        except Exception as e:
            self._recording = False
            self._reset_mic_button()
            self._set_status(f"❌ Không mở được mic: {e}", visible=True)
            QTimer.singleShot(3000, lambda: self._set_status("", visible=False))

    def _stop_recording(self):
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._reset_mic_button()
        self._set_status("⏳ Đang nhận dạng giọng nói…", visible=True)

        if not self._audio_chunks:
            self._set_status("⚠️ Không thu được âm thanh.", visible=True)
            QTimer.singleShot(3000, lambda: self._set_status("", visible=False))
            return

        audio = np.concatenate(self._audio_chunks)

        # Map NLLB code → Whisper language code
        _NLLB_TO_WHISPER = {
            "vie_Latn": "vi",
            "jpn_Jpan": "ja",
            "eng_Latn": "en",
        }
        src_nllb = self._combo_src.currentData() or "vie_Latn"
        whisper_lang = _NLLB_TO_WHISPER.get(src_nllb, "auto")

        self._stt_worker = WhisperSTTWorker(audio, language=whisper_lang, parent=self)
        self._stt_worker.transcribed.connect(self._on_stt_done)
        self._stt_worker.error.connect(self._on_stt_error)
        self._stt_worker.start()

    def _on_stt_done(self, text: str):
        self._set_status("✅ Nhận dạng xong", visible=True)
        # Điền text vào ô nhập để user xem lại trước khi gửi
        self._text_input.setPlainText(text)
        # Tự động gửi sau 0.5s để người dùng thấy kết quả
        QTimer.singleShot(500, self._on_send_clicked)
        QTimer.singleShot(2000, lambda: self._set_status("", visible=False))

    def _on_stt_error(self, msg: str):
        self._set_status(msg, visible=True)
        QTimer.singleShot(4000, lambda: self._set_status("", visible=False))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _reset_mic_button(self):
        self._btn_mic.setText("🎤  Ghi âm")
        self._btn_mic.setObjectName("btn_mic")
        self._refresh_button_style(self._btn_mic)

    def _set_status(self, text: str, visible: bool = True):
        self._status_lbl.setText(text)
        self._status_lbl.setVisible(visible and bool(text))

    @staticmethod
    def _refresh_button_style(btn: QPushButton):
        s = btn.style()
        if s:
            s.unpolish(btn)
            s.polish(btn)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())