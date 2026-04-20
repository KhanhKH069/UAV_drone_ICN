import logging
import uuid
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QVBoxLayout, QWidget, QMenu,
    QSystemTrayIcon, QLineEdit, QStackedWidget, QSizePolicy,
)

from client.ui.config import SERVER_WS, API_KEY
from client.ui.styles import APP_STYLE
from client.ui.components.helpers import card, label
from client.ui.components.splash_screen import SplashScreen
from client.ui.components.frame_trans import FrameTrans
from client.ui.components.frame_chat import FrameChat
from client.ui.components.frame_minutes import FrameMinutes
from client.ui.components.image_panel import ImagePanel
from client.ui.meeting_minutes import MeetingMinutesWorker
from client.audio_router.audio_manager import AudioManager
from client.websocket_client.ws_client import ParalineWSClient
from client.meet_integration.meet_client import MeetClient
from client.meet_integration.bridge_server import MeetBridgeServer
from client.image_handler.image_handler import ImageHandler
from PyQt6.QtWidgets import QComboBox

logger = logging.getLogger("paraline.ui")


class ParalineMainWindow(QMainWindow):
    sig_subtitle        = pyqtSignal(str , str, float)
    sig_outbound_text   = pyqtSignal(str, str)
    sig_tts_audio       = pyqtSignal(str)
    sig_img_result      = pyqtSignal(object)
    sig_img_error       = pyqtSignal(str)
    sig_meeting_started = pyqtSignal(str)
    sig_meeting_ended   = pyqtSignal()
    sig_mock_result     = pyqtSignal(list)
    sig_listening       = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.session_id: Optional[str] = None
        self.ws_client:  Optional[ParalineWSClient] = None
        self.audio_mgr   = AudioManager()
        self.meet_client = MeetClient()
        self.image_handler: Optional[ImageHandler] = None
        self._join_delay_timer: Optional[QTimer] = None
        self._active_tab = 0
        self._selected_device: Optional[str] = None   # device chọn từ splash screen

        self.meeting_monitor = MeetBridgeServer(
            on_meeting_started=lambda url: self.sig_meeting_started.emit(url),
            on_meeting_ended=lambda: self.sig_meeting_ended.emit(),
        )
        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._setup_hotkeys()
        self._setup_tray()
        self.meeting_monitor.start()

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("Paraline MSAgent")
        self.setStyleSheet(APP_STYLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        W, H = 380, 640
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.setGeometry(g.width() - W - 16, max(16, (g.height() - H) // 2), W, H)
        else:
            self.resize(W, H)
        self.setMinimumSize(340, 480)
        self.setMaximumWidth(440)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QWidget()
        outer.setObjectName("outer_bg")
        outer.setStyleSheet("QWidget#outer_bg { background: transparent; }")
        self.setCentralWidget(outer)
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(8, 8, 8, 8)
        outer_lay.setSpacing(0)

        root = QWidget()
        root.setObjectName("root_widget")
        outer_lay.addWidget(root)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_splash())   # 0
        self._stack.addWidget(self._build_main())     # 1
        self._stack.setCurrentIndex(0)
        lay.addWidget(self._stack)

    # ── Splash ────────────────────────────────────────────────────────────────

    def _build_splash(self) -> QWidget:
        self._splash = SplashScreen()
        self._splash.join_requested.connect(self._on_join_requested)
        return self._splash

    # ── Main screen ──────────────────────────────────────────────────────────

    def _build_main(self) -> QWidget:
        main = QWidget()
        main.setObjectName("root_widget")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_mini_header())
        lay.addWidget(self._build_tab_bar())

        self._frame_stack = QStackedWidget()
        self._frame_trans   = FrameTrans()
        self._frame_chat    = FrameChat()
        self._img_panel     = ImagePanel()
        self._frame_minutes = FrameMinutes()

        self._img_panel.translate_requested.connect(self._on_image_paste)

        self._frame_stack.addWidget(self._frame_trans)    # 0
        self._frame_stack.addWidget(self._frame_chat)     # 1
        self._frame_stack.addWidget(self._img_panel)      # 2
        self._frame_stack.addWidget(self._frame_minutes)  # 3
        self._frame_stack.setCurrentIndex(0)
        lay.addWidget(self._frame_stack, 1)

        lay.addWidget(self._build_ctrl_bar())
        return main

    def _build_mini_header(self) -> QWidget:
        hdr = card("mini_header")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)

        lay.addWidget(label("Para", "mini_brand_para"))
        lay.addWidget(label("line", "mini_brand_line"))
        lay.addSpacing(10)

        self._mini_url = label("—", "mini_url")
        self._mini_url.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._mini_url.setMaximumWidth(180)
        lay.addWidget(self._mini_url)
        lay.addStretch()

        self._status_pill = label("● IDLE", "status_idle")
        lay.addWidget(self._status_pill)
        lay.addSpacing(8)

        btn_quit = QPushButton("×")
        btn_quit.setObjectName("btn_quit")
        btn_quit.setFixedSize(28, 28)
        btn_quit.clicked.connect(QApplication.instance().quit)
        lay.addWidget(btn_quit)
        return hdr

    def _build_tab_bar(self) -> QWidget:
        bar = card("tab_bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        self._tab_btns = []
        for i, name in enumerate(["Dịch", "Chat", "Slide", "Biên bản"]):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("tab_btn_active" if i == 0 else "tab_btn")
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            lay.addWidget(btn)
            self._tab_btns.append(btn)
        return bar

    def _build_ctrl_bar(self) -> QWidget:
        bar = card("ctrl_bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        self._btn_end = QPushButton("⏹  Kết thúc phiên")
        self._btn_end.setObjectName("btn_end")
        self._btn_end.clicked.connect(self._stop_session)
        self._btn_end.setEnabled(False)

        
        # btn_mins = QPushButton("📋  Biên bản")
        # btn_mins.setObjectName("btn_minutes")
        # btn_mins.clicked.connect(lambda: self._switch_tab(3))
        # lay.addWidget(btn_mins, 2)


        self._combo_tgt_lang = QComboBox()
        self._combo_tgt_lang.setObjectName("combo_lang")

        # label hiển thị — value là NLLB code
        # self._combo_tgt_lang.addItem("🆻🇳 Vietnamese", "vie_Latn")
        self._combo_tgt_lang.addItem("🇺🇸 English", "eng_Latn")
        self._combo_tgt_lang.addItem("🇯🇵 Japanese", "jpn_Jpan")

        # Khởi tạo ngôn ngữ đích mặc định cho chat
        self._chat_tgt_lang: str = self._combo_tgt_lang.currentData() or "jpn_Jpan"

        self._combo_tgt_lang.currentIndexChanged.connect(self._on_change_language)

        lay.addWidget(self._combo_tgt_lang, 2)
        lay.addWidget(self._btn_end, 3)
        
        return bar

    # ── Tab ───────────────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        self._active_tab = idx
        self._frame_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setObjectName("tab_btn_active" if i == idx else "tab_btn")
            s = btn.style()
            if s: s.unpolish(btn); s.polish(btn)

    # ── Join / Session ────────────────────────────────────────────────────────


    def _on_change_language(self, idx: int):
        tgt_lang = self._combo_tgt_lang.currentData()
        if not tgt_lang:
            return

        # Cập nhật ngôn ngữ đích cho chat outbound
        self._chat_tgt_lang = tgt_lang

        if self.ws_client:
            # inbound: người kia → bạn
            self.ws_client.inbound_src_lang = tgt_lang
            print(f'[🌐] Switched language inbound → {self.ws_client.inbound_src_lang}')


    def _on_join_requested(self, url: str, platform: str, device_name: str = ""):
        self._selected_device = device_name or None
        if device_name:
            logger.info(f"[UI] Thiết bị đầu vào được chọn: {device_name}")
        self.meet_client.join_meeting(url)
        display = url.replace("https://", "").replace("http://", "")
        self._mini_url.setText(display[:42] + ("…" if len(display) > 42 else ""))
        self._stack.setCurrentIndex(1)

        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._delayed_start_session)
        t.start(2000)
        self._join_delay_timer = t

    def _delayed_start_session(self):
        if not self.session_id:
            self._start_session()

    def _start_session(self):
        self.session_id = str(uuid.uuid4())
        self.image_handler = ImageHandler(self.session_id, API_KEY)
        # self.ws_client = ParalineWSClient(
        #     server_ws_url=SERVER_WS, session_id=self.session_id, api_key=API_KEY,
        #     on_subtitle=     lambda t, ms: self.sig_subtitle.emit(t, ms),
        #     on_inbound_audio=lambda b64:   self.sig_tts_audio.emit(b64),
        #     on_outbound_text=lambda o, t:  self.sig_outbound_text.emit(o, t),
        # )

        self.ws_client = ParalineWSClient(
            server_ws_url=SERVER_WS,
            session_id=self.session_id,
            api_key=API_KEY,
            on_subtitle=lambda src, dst, ms: self.sig_subtitle.emit(src, dst, ms),
            on_inbound_audio=lambda b64: self.sig_tts_audio.emit(b64),
            on_outbound_text=lambda o, t: self.sig_outbound_text.emit(o, t),
            on_listening=lambda text: self.sig_listening.emit(text),
        )

        if getattr(self.ws_client, "inbound_only", False):
            self._frame_trans.set_inbound_only(True)

        self.ws_client.start()
        self.audio_mgr.start(
            inbound_cb=self.ws_client.send_inbound_chunk,
            inbound_device=self._selected_device,
        )
        self._set_status("live", "● LIVE")
        self._btn_end.setEnabled(True)
        self.meet_client.send_welcome()
        self._frame_trans.add_trans_item("", "✅ Phiên dịch đã bắt đầu", 0)
        self._frame_chat.add_bubble("Paraline", "✅ Phiên dịch đã bắt đầu", outbound=True)
        logger.info(f"Session started: {self.session_id[:8]}")

    def _stop_session(self):
        if self.ws_client:
            self.ws_client.stop()
        self.audio_mgr.stop()
        self._set_status("idle", "● IDLE")
        self._btn_end.setEnabled(False)
        self.session_id = None
        self._get_meeting_minutes()

    def _get_meeting_minutes(self):
        if not self.session_id:
            return
        self._frame_trans.add_trans_item("", "⏳ Đang tạo biên bản cuộc họp…", 0)
        self._minutes_worker = MeetingMinutesWorker(self.session_id)
        self._minutes_worker.finished.connect(self._on_minutes_success)
        self._minutes_worker.error.connect(self._on_minutes_error)
        self._minutes_worker.start()

    def _on_minutes_success(self, data: dict):
        self._frame_minutes.populate(data)
        self._switch_tab(3)
        msg = f"📋 Biên bản họp\n\n{data.get('summary', '')}\n"
        for item in data.get("action_items", []):
            msg += f"• [{item.get('priority','').upper()}] {item.get('task','')} — {item.get('assignee','?')}\n"
        self.meet_client.send_raw(msg)
        QTimer.singleShot(4000, lambda: self._stack.setCurrentIndex(0))

    def _on_minutes_error(self, err: str):
        logger.error(f"Meeting minutes error: {err}")
        self._frame_trans.add_trans_item("", f"❌ Lỗi tạo biên bản: {err}", 0)
        QTimer.singleShot(3000, lambda: self._stack.setCurrentIndex(0))

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_subtitle(self, src, dst, latency: float):
        self._frame_trans.update_live_text("")  # Clear live area on final result
        self._frame_trans.add_trans_item(src, dst, latency)

    def _on_listening(self, text: str):
        self._frame_trans.update_live_text(text)

    def _on_outbound_text(self, original: str, translated: str):
        if self.ws_client and getattr(self.ws_client, "inbound_only", False):
            return
        self._frame_trans.add_trans_item(original, translated, 0)
        self._frame_trans.append_outbound_log(translated)
        self.meet_client.send_translation(original, translated)

    # ── Chat send (text input + voice) ────────────────────────────────

    def _on_chat_send(self, original: str, src_lang: str):
        """
        Nhận text từ FrameChat (gõ tay hoặc giọng nói đã qua STT).
        1. Hiển thị bubble ngay lập tức (UX).
        2. Trong thread phụ: gọi REST /translate rồi gửi lên Meet.
        """
        self._frame_chat.add_bubble("Bạn", original, outbound=True)

        tgt_lang = getattr(self, "_chat_tgt_lang", "jpn_Jpan")

        import threading
        threading.Thread(
            target=self._call_translation_and_send,
            args=(original, src_lang, tgt_lang),
            daemon=True,
        ).start()

    def _call_translation_and_send(self, original: str, src_lang: str, tgt_lang: str):
        """Chạy trong thread phụ — gọi REST, rồi emit kết quả về main thread."""
        translated = original  # fallback nếu translation service không chạy
        try:
            import requests
            # Translation service REST endpoint (port 8002)
            trans_url = "http://localhost:8002/translate"
            resp = requests.post(
                trans_url,
                json={"text": original, "src_lang": src_lang, "tgt_lang": tgt_lang},
                timeout=60,   # NLLB model cần thời gian load + inference lần đầu
            )
            if resp.ok:
                translated = resp.json().get("translated_text", original)
                logger.info(f"[Chat] Dịch OK: '{original[:30]}' → '{translated[:30]}'")
        except Exception as e:
            logger.warning(f"[Chat] Translation REST failed: {e} — dùng text gốc")

        # Gửi lên Meet chat
        self.meet_client.send_raw(f"[Paraline Chat] {translated}")

        # Cập nhật bubble với kết quả dịch — dùng QTimer để emit về GUI thread
        QTimer.singleShot(
            0,
            lambda: self._frame_chat.add_bubble(
                f"↳ Dịch ({tgt_lang})", translated, outbound=False
            ),
        )


    def _on_tts_audio(self, audio_b64: str):
        self.audio_mgr.play_tts(audio_b64)

    def _on_image_paste(self, pil_img, src_lang="eng_Latn"):
        if not self.session_id:
            self._frame_trans.add_trans_item("", "⚠️ Cần bắt đầu phiên trước khi dịch ảnh", 0)
            return
        if self.image_handler:
            self.image_handler.translate_image(
                pil_img, src_lang=src_lang,
                on_success=lambda img, _: self.sig_img_result.emit(img),
                on_error=lambda msg: self.sig_img_error.emit(msg),
            )

    def _on_meeting_started(self, join_url: str):
        if self.session_id:
            return
        if join_url:
            self.meet_client.join_meeting(join_url)
        display = (join_url or "—").replace("https://", "").replace("http://", "")
        self._mini_url.setText(display[:42])
        self._stack.setCurrentIndex(1)
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._delayed_start_session)
        t.start(1200)
        self._join_delay_timer = t

    def _on_meeting_ended(self):
        t = self._join_delay_timer
        if t and t.isActive():
            t.stop()
        if self.session_id:
            self._stop_session()

    def _on_mock_result(self, results: list):
        if not results:
            self._frame_trans.add_trans_item("", "❌ Mock test thất bại — kiểm tra kết nối server.", 0)
            return
        self._frame_trans.add_trans_item("", "✅ Mock test hoàn tất", 0)
        for item in results:
            self.sig_outbound_text.emit(
                item.get("original", "")[:50],
                item.get("translated", "")[:60],
            )

    # ── Wiring ────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.sig_subtitle.connect(self._on_subtitle)
        self.sig_outbound_text.connect(self._on_outbound_text)
        self.sig_tts_audio.connect(self._on_tts_audio)
        self.sig_img_result.connect(self._img_panel.show_result)
        self.sig_img_error.connect(self._img_panel.show_error)
        self.sig_meeting_started.connect(self._on_meeting_started)
        self.sig_meeting_ended.connect(self._on_meeting_ended)
        self.sig_mock_result.connect(self._on_mock_result)
        self.sig_listening.connect(self._on_listening)
        # Chat frame: người dùng gửi text (từ gõ phím hoặc giọng nói)
        self._frame_chat.send_requested.connect(self._on_chat_send)

    def _setup_hotkeys(self):
        QShortcut(QKeySequence("Ctrl+V"),       self, self._handle_paste)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, self._toggle_visibility)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        menu = QMenu()
        menu.addAction("Mở Paraline", self.show)
        menu.addSeparator()
        app = QApplication.instance()
        if app:
            menu.addAction("Thoát", app.quit)
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("Paraline MSAgent")
        self._tray.show()

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, state: str, text: str):
        obj = "status_live" if state == "live" else "status_idle"
        self._status_pill.setText(text)
        self._status_pill.setObjectName(obj)
        s = self._status_pill.style()
        if s: s.unpolish(self._status_pill); s.polish(self._status_pill)

    # ── Drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, a0):
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = a0.globalPosition().toPoint()

    def mouseMoveEvent(self, a0):
        if a0 and a0.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(self.pos() + a0.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = a0.globalPosition().toPoint()

    # ── Paste ─────────────────────────────────────────────────────────────────

    def _handle_paste(self):
        from PyQt6.QtWidgets import QApplication as _App
        from PyQt6.QtCore import QByteArray, QBuffer
        from PIL import Image as PILImage
        import io

        cb = _App.clipboard()
        if not cb: return
        m = cb.mimeData()
        if not m: return

        if m.hasImage():
            q = cb.image()
            if q and not q.isNull():
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QBuffer.OpenModeFlag.WriteOnly)
                q.save(buf, "PNG")
                pil = PILImage.open(io.BytesIO(ba.data())).convert("RGB")
                self._switch_tab(2)
                self._on_image_paste(pil, self._img_panel._combo_lang.currentData())
        elif m.hasUrls():
            for url in m.urls():
                if url.isLocalFile():
                    try:
                        pil = PILImage.open(url.toLocalFile()).convert("RGB")
                        self._switch_tab(2)
                        self._on_image_paste(pil, self._img_panel._combo_lang.currentData())
                        break
                    except Exception:
                        pass

    def _toggle_visibility(self):
        self.hide() if self.isVisible() else self.show()

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, a0):
        self.meeting_monitor.stop()
        if self.ws_client: self.ws_client.stop()
        self.audio_mgr.stop()
        super().closeEvent(a0)