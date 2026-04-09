import logging
import uuid
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QShortcut, QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QMenu,
    QSizeGrip, QSystemTrayIcon, QLineEdit, QStackedWidget,
    QScrollArea, QSizePolicy, QTabWidget,
)

from client.ui.config import SERVER_WS, API_KEY, STYLE
from client.ui.components.frame_trans import FrameTrans
from client.ui.components.translation_zone import TranslationZone
from client.ui.components.image_panel import ImagePanel
from client.ui.meeting_minutes import MeetingMinutesWorker
from client.audio_router.audio_manager import AudioManager
from client.websocket_client.ws_client import ParalineWSClient
from client.meet_integration.meet_client import MeetClient
from client.meet_integration.bridge_server import MeetBridgeServer
from client.image_handler.image_handler import ImageHandler

logger = logging.getLogger("paraline.ui")

# ── Stylesheet ────────────────────────────────────────────────────────────────

APP_STYLE = """
/* ── Root ── */
QMainWindow {
    background: transparent;
}
QWidget#root_widget {
    background: #ffffff;
    border-radius: 18px;
    border: 1px solid rgba(0,229,160,0.3);
}

/* ── Splash screen ── */
QWidget#splash {
    background: #ffffff;
    border-radius: 18px;
}

QLabel#brand_para {
    font-size: 32px;
    font-weight: 800;
    color: #111111;
    letter-spacing: -1px;
}
QLabel#brand_line {
    font-size: 32px;
    font-weight: 800;
    color: #00e5a0;
    letter-spacing: -1px;
}
QLabel#brand_tagline {
    font-size: 10px;
    color: #999999;
    letter-spacing: 3px;
}

/* ── Link card ── */
QWidget#link_card {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 14px;
}
QLabel#lc_label {
    font-size: 9px;
    font-weight: 700;
    color: #999999;
    letter-spacing: 2px;
}

/* ── Platform buttons ── */
QPushButton#btn_platform {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    color: #555555;
    font-size: 11px;
    font-weight: 600;
    padding: 7px 0;
}
QPushButton#btn_platform:hover {
    border-color: #00c88c;
    color: #00a875;
}
QPushButton#btn_platform_active {
    background: #111111;
    border: 1px solid #111111;
    border-radius: 8px;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 7px 0;
}

/* ── Link input ── */
QLineEdit#link_input {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    padding: 8px 12px;
    color: #111111;
    font-size: 12px;
}
QLineEdit#link_input:focus {
    border-color: #00e5a0;
}

/* ── Go button ── */
QPushButton#btn_go {
    background: #00e5a0;
    border: none;
    border-radius: 8px;
    color: #111111;
    font-size: 12px;
    font-weight: 800;
    padding: 8px 14px;
}
QPushButton#btn_go:hover {
    background: #00c88c;
}
QPushButton#btn_go:disabled {
    background: #cccccc;
    color: #888888;
}

/* ── Mini header (after join) ── */
QWidget#mini_header {
    background: #111111;
}
QLabel#mini_brand_para {
    font-size: 15px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.5px;
}
QLabel#mini_brand_line {
    font-size: 15px;
    font-weight: 800;
    color: #00e5a0;
    letter-spacing: -0.5px;
}
QLabel#mini_url {
    font-size: 10px;
    color: rgba(255,255,255,0.45);
}
QLabel#status_live {
    font-size: 9px;
    font-weight: 700;
    color: #00e5a0;
    background: rgba(0,229,160,0.15);
    border: 1px solid rgba(0,229,160,0.3);
    border-radius: 10px;
    padding: 3px 8px;
    letter-spacing: 0.8px;
}
QLabel#status_idle {
    font-size: 9px;
    font-weight: 700;
    color: #888888;
    background: rgba(128,128,128,0.12);
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 10px;
    padding: 3px 8px;
    letter-spacing: 0.8px;
}

/* ── Tab bar ── */
QWidget#tab_bar {
    background: #f7fdfb;
    border-bottom: 1px solid rgba(0,229,160,0.2);
}
QPushButton#tab_btn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #999999;
    font-size: 10px;
    font-weight: 700;
    padding: 6px 0;
    letter-spacing: 0.3px;
}
QPushButton#tab_btn:hover {
    color: #555555;
}
QPushButton#tab_btn_active {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    color: #111111;
    font-size: 10px;
    font-weight: 700;
    padding: 6px 0;
    letter-spacing: 0.3px;
}

/* ── Frame: Translation ── */
QWidget#trans_item {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px;
}
QWidget#trans_item_live {
    background: #e6fff5;
    border: 1px solid #00e5a0;
    border-radius: 9px;
}
QLabel#trans_src {
    font-size: 11px;
    color: #999999;
}
QLabel#trans_dst {
    font-size: 13px;
    font-weight: 600;
    color: #111111;
}
QLabel#trans_badge {
    font-size: 9px;
    font-weight: 700;
    color: #00a875;
}
QLabel#trans_listening {
    font-size: 11px;
    font-weight: 700;
    color: #00a875;
}

/* ── Frame: Chat ── */
QWidget#chat_bubble {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px;
}
QWidget#chat_bubble_out {
    background: #e6fff5;
    border: 1px solid rgba(0,229,160,0.5);
    border-radius: 9px;
}
QLabel#chat_who {
    font-size: 9px;
    font-weight: 700;
    color: #999999;
    letter-spacing: 0.5px;
}
QLabel#chat_who_me {
    font-size: 9px;
    font-weight: 700;
    color: #00a875;
    letter-spacing: 0.5px;
}
QLabel#chat_text {
    font-size: 12px;
    color: #111111;
}

/* ── Frame: Slide ── */
QWidget#slide_drop {
    background: #f7fdfb;
    border: 2px dashed rgba(0,229,160,0.4);
    border-radius: 9px;
}
QLabel#slide_hint {
    font-size: 11px;
    font-weight: 600;
    color: #999999;
}
QWidget#slide_result {
    background: #e6fff5;
    border: 1px solid rgba(0,229,160,0.5);
    border-radius: 9px;
}

/* ── Frame: Minutes ── */
QWidget#minutes_body {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px;
}
QWidget#action_item {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px;
}
QLabel#pri_high {
    background: #fff0f0;
    color: #c0392b;
    font-size: 9px;
    font-weight: 800;
    border-radius: 4px;
    padding: 2px 5px;
}
QLabel#pri_med {
    background: #fffbe6;
    color: #b07d00;
    font-size: 9px;
    font-weight: 800;
    border-radius: 4px;
    padding: 2px 5px;
}
QLabel#section_label {
    font-size: 9px;
    font-weight: 700;
    color: #999999;
    letter-spacing: 1.5px;
}

/* ── Scrollarea ── */
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    width: 4px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: rgba(0,229,160,0.35);
    border-radius: 2px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Control bar ── */
QWidget#ctrl_bar {
    background: #f7fdfb;
    border-top: 1px solid rgba(0,229,160,0.2);
}
QPushButton#btn_end {
    background: #fff5f5;
    border: 1px solid #fcc;
    border-radius: 8px;
    color: #c0392b;
    font-size: 11px;
    font-weight: 700;
    padding: 9px 0;
}
QPushButton#btn_end:hover {
    background: #ffe8e8;
}
QPushButton#btn_minutes {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    color: #00a875;
    font-size: 11px;
    font-weight: 700;
    padding: 9px 12px;
}
QPushButton#btn_minutes:hover {
    background: #e6fff5;
}
QPushButton#btn_quit {
    background: transparent;
    border: none;
    color: rgba(255,255,255,0.5);
    font-size: 18px;
    font-weight: 300;
    padding: 0;
}
QPushButton#btn_quit:hover {
    color: #ffffff;
}

/* ── Outbound log ── */
QTextEdit#outbound_log {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px;
    font-size: 11px;
    color: #555555;
    padding: 6px;
}
"""


# ── Pulse dot widget ──────────────────────────────────────────────────────────

class PulseDot(QWidget):
    """Animated mint-green pulsing circle for the splash screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._radius = 0.0
        self._alpha = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self._phase = 0.0

    def _tick(self):
        import math
        self._phase = (self._phase + 0.03) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2

        # 3 ripple rings
        for i in range(3):
            phase_offset = (self._phase + i * (2 * math.pi / 3)) % (2 * math.pi)
            t = (math.sin(phase_offset) + 1) / 2  # 0..1
            r = int(10 + t * 28)
            alpha = int(120 * (1 - t))
            pen = QPen(QColor(0, 229, 160, alpha))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 229, 160)))
        p.drawEllipse(cx - 7, cy - 7, 14, 14)
        p.end()


# ── Helper builders ───────────────────────────────────────────────────────────

def _card(obj_name: str) -> QWidget:
    w = QWidget()
    w.setObjectName(obj_name)
    return w


def _label(text: str, obj_name: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName(obj_name)
    return l


def _scroll_wrap(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return sa


# ── Main Window ───────────────────────────────────────────────────────────────

class ParalineMainWindow(QMainWindow):
    sig_subtitle        = pyqtSignal(str, float)
    sig_outbound_text   = pyqtSignal(str, str)
    sig_tts_audio       = pyqtSignal(str)
    sig_img_result      = pyqtSignal(object)
    sig_img_error       = pyqtSignal(str)
    sig_meeting_started = pyqtSignal(str)
    sig_meeting_ended   = pyqtSignal()
    sig_mock_result     = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.session_id: Optional[str] = None
        self.ws_client:  Optional[ParalineWSClient] = None
        self.audio_mgr     = AudioManager()
        self.meet_client   = MeetClient()
        self.image_handler: Optional[ImageHandler] = None
        self._join_delay_timer: Optional[QTimer] = None
        self._pending_join_url: Optional[str] = None
        self._active_tab = 0
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

    # ── Window setup ─────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("Paraline MSAgent")
        self.setStyleSheet(APP_STYLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Cố định kích thước — không kéo dài full màn hình
        W, H = 320, 640
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            x = g.width() - W - 16
            y = max(16, (g.height() - H) // 2)   # căn giữa dọc
            self.setGeometry(x, y, W, H)
        else:
            self.resize(W, H)
        self.setMinimumSize(280, 480)
        self.setMaximumWidth(380)

    # ── UI build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer transparent — cho shadow thở
        outer = QWidget()
        outer.setObjectName("outer_bg")
        outer.setStyleSheet("QWidget#outer_bg { background: transparent; }")
        self.setCentralWidget(outer)
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(8, 8, 8, 8)
        outer_lay.setSpacing(0)

        # Inner card bo góc
        root = QWidget()
        root.setObjectName("root_widget")
        outer_lay.addWidget(root)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Stacked: 0 = splash, 1 = main
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_splash())
        self._stack.addWidget(self._build_main())
        self._stack.setCurrentIndex(0)
        lay.addWidget(self._stack)

    # ── Splash screen ─────────────────────────────────────────────────────────

    def _build_splash(self) -> QWidget:
        splash = QWidget()
        splash.setObjectName("splash")
        lay = QVBoxLayout(splash)
        lay.setContentsMargins(24, 0, 24, 32)
        lay.setSpacing(0)

        lay.addStretch(2)

        # Pulse dot
        pulse_wrap = QWidget()
        pulse_lay = QHBoxLayout(pulse_wrap)
        pulse_lay.setContentsMargins(0, 0, 0, 0)
        pulse_lay.addStretch()
        self._pulse = PulseDot()
        pulse_lay.addWidget(self._pulse)
        pulse_lay.addStretch()
        lay.addWidget(pulse_wrap)

        lay.addSpacing(20)

        # Brand name: "Para" + "line"
        brand_row = QWidget()
        brand_row_lay = QHBoxLayout(brand_row)
        brand_row_lay.setContentsMargins(0, 0, 0, 0)
        brand_row_lay.setSpacing(0)
        brand_row_lay.addStretch()
        lbl_para = _label("Para", "brand_para")
        lbl_line = _label("line", "brand_line")
        brand_row_lay.addWidget(lbl_para)
        brand_row_lay.addWidget(lbl_line)
        brand_row_lay.addStretch()
        lay.addWidget(brand_row)

        lay.addSpacing(6)

        tagline = _label("MS AGENT \n REAL-TIME TRANSLATION", "brand_tagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tagline)

        lay.addStretch(1)

        # Link card
        card = _card("link_card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 16, 16, 16)
        card_lay.setSpacing(10)

        card_lay.addWidget(_label("CHỌN NỀN TẢNG", "lc_label"))

        # Platform toggle
        plat_row = QHBoxLayout()
        plat_row.setSpacing(6)
        self._btn_meet  = QPushButton("Google Meet")
        self._btn_teams = QPushButton("Teams")
        for btn in (self._btn_meet, self._btn_teams):
            btn.setObjectName("btn_platform")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_meet.setObjectName("btn_platform_active")
        self._btn_meet.clicked.connect(lambda: self._select_platform("meet"))
        self._btn_teams.clicked.connect(lambda: self._select_platform("teams"))
        plat_row.addWidget(self._btn_meet)
        plat_row.addWidget(self._btn_teams)
        card_lay.addLayout(plat_row)

        card_lay.addWidget(_label("LINK CUỘC HỌP", "lc_label"))

        # Input + Go
        inp_row = QHBoxLayout()
        inp_row.setSpacing(8)
        self._link_input = QLineEdit()
        self._link_input.setObjectName("link_input")
        self._link_input.setPlaceholderText("Dán link Google Meet vào đây…")
        self._link_input.returnPressed.connect(self._on_join_clicked)
        btn_go = QPushButton("Vào →")
        btn_go.setObjectName("btn_go")
        btn_go.setFixedWidth(70)
        btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go.clicked.connect(self._on_join_clicked)
        inp_row.addWidget(self._link_input)
        inp_row.addWidget(btn_go)
        card_lay.addLayout(inp_row)

        lay.addWidget(card)
        lay.addStretch(2)

        return splash

    # ── Main screen ──────────────────────────────────────────────────────────

    def _build_main(self) -> QWidget:
        main = QWidget()
        main.setObjectName("root_widget")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_mini_header())
        lay.addWidget(self._build_tab_bar())

        # Frame stack
        self._frame_stack = QStackedWidget()
        
        self.trans_frame = FrameTrans()
        self._frame_stack.addWidget(self.trans_frame)
        
        self._frame_stack.addWidget(self._build_frame_chat())
        self._frame_stack.addWidget(self._build_frame_slide())
        self._frame_stack.addWidget(self._build_frame_minutes())
        self._frame_stack.setCurrentIndex(0)
        lay.addWidget(self._frame_stack, 1)

        lay.addWidget(self._build_ctrl_bar())
        return main

    def _build_mini_header(self) -> QWidget:
        hdr = _card("mini_header")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)

        # Brand
        lbl_para = _label("Para", "mini_brand_para")
        lbl_line = _label("line", "mini_brand_line")
        lay.addWidget(lbl_para)
        lay.addWidget(lbl_line)
        lay.addSpacing(10)

        # URL
        self._mini_url = _label("—", "mini_url")
        self._mini_url.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._mini_url.setMaximumWidth(160)
        lay.addWidget(self._mini_url)

        lay.addStretch()

        self._status_pill = _label("● IDLE", "status_idle")
        lay.addWidget(self._status_pill)
        lay.addSpacing(8)

        btn_quit = QPushButton("×")
        btn_quit.setObjectName("btn_quit")
        btn_quit.setFixedSize(28, 28)
        btn_quit.clicked.connect(QApplication.instance().quit)
        lay.addWidget(btn_quit)

        return hdr

    def _build_tab_bar(self) -> QWidget:
        bar = _card("tab_bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        tabs = ["Dịch", "Chat", "Slide", "Biên bản"]
        self._tab_btns = []
        for i, name in enumerate(tabs):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("tab_btn_active" if i == 0 else "tab_btn")
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            lay.addWidget(btn)
            self._tab_btns.append(btn)

        return bar

    def _build_ctrl_bar(self) -> QWidget:
        bar = _card("ctrl_bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        self._btn_end = QPushButton("⏹  Kết thúc phiên")
        self._btn_end.setObjectName("btn_end")
        self._btn_end.clicked.connect(self._stop_session)
        self._btn_end.setEnabled(False)

        btn_mins = QPushButton("📋  Biên bản")
        btn_mins.setObjectName("btn_minutes")
        btn_mins.clicked.connect(lambda: self._switch_tab(3))

        lay.addWidget(self._btn_end, 3)
        lay.addWidget(btn_mins, 2)
        return bar

    # ── Frame: Dịch ──────────────────────────────────────────────────────────

    def _build_frame_trans(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._trans_layout = QVBoxLayout(inner)
        self._trans_layout.setContentsMargins(14, 14, 14, 14)
        self._trans_layout.setSpacing(8)
        self._trans_layout.addStretch()

        # Live indicator card (always at bottom)
        self._live_card = _card("trans_item_live")
        live_lay = QVBoxLayout(self._live_card)
        live_lay.setContentsMargins(10, 8, 10, 8)
        live_lay.setSpacing(3)
        self._live_label = _label("● Đang nghe…", "trans_listening")
        live_lay.addWidget(self._live_label)
        self._trans_layout.addWidget(self._live_card)

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        # Outbound log
        sep = QWidget(); sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,229,160,0.2);")
        lay.addWidget(sep)

        log_wrap = QWidget()
        log_wrap.setStyleSheet("background: #f7fdfb;")
        log_lay = QVBoxLayout(log_wrap)
        log_lay.setContentsMargins(14, 8, 14, 8)
        log_lay.setSpacing(4)
        log_lay.addWidget(_label("ĐÃ ĐẨY VÀO MEET", "section_label"))
        self._outbound_log = QTextEdit()
        self._outbound_log.setObjectName("outbound_log")
        self._outbound_log.setReadOnly(True)
        self._outbound_log.setFixedHeight(72)
        log_lay.addWidget(self._outbound_log)
        lay.addWidget(log_wrap)

        return outer

    def _add_trans_item(self, src: str, dst: str, latency_ms: float = 0.0):
        """Add a translation bubble above the live card."""
        item = _card("trans_item")
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(item)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        if src:
            src_lbl = _label(f"EN · \"{src}\"", "trans_src")
            src_lbl.setWordWrap(True)
            src_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            lay.addWidget(src_lbl)
        dst_lbl = _label(dst, "trans_dst")
        dst_lbl.setWordWrap(True)
        dst_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(dst_lbl)
        if latency_ms:
            badge = _label(f"▶ {latency_ms:.0f}ms", "trans_badge")
            badge.setAlignment(Qt.AlignmentFlag.AlignRight)
            lay.addWidget(badge)

        # Insert before stretch + live card (last 2 items)
        idx = self._trans_layout.count() - 2
        self._trans_layout.insertWidget(idx, item)

        # Auto-scroll
        QTimer.singleShot(50, lambda: self._scroll_trans_to_bottom())

    def _scroll_trans_to_bottom(self):
        # Find the scroll area parent
        w = self._trans_layout.parentWidget()
        if w:
            p = w.parent()
            if isinstance(p, QScrollArea):
                sb = p.verticalScrollBar()
                if sb:
                    sb.setValue(sb.maximum())

    # ── Frame: Chat ───────────────────────────────────────────────────────────

    def _build_frame_chat(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._chat_layout = QVBoxLayout(inner)
        self._chat_layout.setContentsMargins(14, 14, 14, 14)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return outer

    def _add_chat_bubble(self, who: str, text: str, outbound: bool = False):
        item = _card("chat_bubble_out" if outbound else "chat_bubble")
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(item)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)
        who_lbl = _label(who.upper(), "chat_who_me" if outbound else "chat_who")
        lay.addWidget(who_lbl)
        txt = _label(text, "chat_text")
        txt.setWordWrap(True)
        txt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(txt)

        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, item)

    # ── Frame: Slide ─────────────────────────────────────────────────────────

    def _build_frame_slide(self) -> QWidget:
        self._img_panel = ImagePanel()
        self._img_panel.translate_requested.connect(self._on_image_paste)
        return self._img_panel

    # ── Frame: Biên bản ──────────────────────────────────────────────────────

    def _build_frame_minutes(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        self._minutes_layout = QVBoxLayout(inner)
        self._minutes_layout.setContentsMargins(14, 14, 14, 14)
        self._minutes_layout.setSpacing(10)

        # Placeholder
        ph = _label("Biên bản họp sẽ hiện ở đây sau khi kết thúc phiên.", "trans_src")
        ph.setWordWrap(True)
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._minutes_layout.addStretch()
        self._minutes_layout.addWidget(ph)
        self._minutes_layout.addStretch()
        self._minutes_placeholder = ph

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return outer

    def _show_minutes(self, data: dict):
        # Clear placeholder
        if self._minutes_placeholder:
            self._minutes_placeholder.hide()

        lay = self._minutes_layout
        # Remove stretches
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Summary
        lay.addWidget(_label("TÓM TẮT NỘI DUNG", "section_label"))
        summary_card = _card("minutes_body")
        sc_lay = QVBoxLayout(summary_card)
        sc_lay.setContentsMargins(10, 8, 10, 8)
        summary_lbl = _label(data.get("summary", ""), "chat_text")
        summary_lbl.setWordWrap(True)
        sc_lay.addWidget(summary_lbl)
        lay.addWidget(summary_card)

        # Separator
        sep = QWidget(); sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,229,160,0.2);")
        lay.addWidget(sep)

        # Action items
        if data.get("action_items"):
            lay.addWidget(_label("HÀNH ĐỘNG CẦN LÀM", "section_label"))
            for item in data["action_items"]:
                ai = _card("action_item")
                ai_lay = QHBoxLayout(ai)
                ai_lay.setContentsMargins(10, 8, 10, 8)
                ai_lay.setSpacing(8)

                pri = item.get("priority", "med").lower()
                pri_lbl = _label("CAO" if pri == "high" else "VỪA",
                                 "pri_high" if pri == "high" else "pri_med")
                ai_lay.addWidget(pri_lbl, 0, Qt.AlignmentFlag.AlignTop)

                txt_col = QVBoxLayout()
                txt_col.setSpacing(2)
                task_lbl = _label(item.get("task", ""), "chat_text")
                task_lbl.setWordWrap(True)
                who_lbl  = _label(f"→ {item.get('assignee', '?')}", "trans_src")
                txt_col.addWidget(task_lbl)
                txt_col.addWidget(who_lbl)
                ai_lay.addLayout(txt_col)

                lay.addWidget(ai)

        lay.addStretch()

        # Send to Meet
        msg = f"📋 Biên bản họp\n\n{data.get('summary','')}\n"
        for item in data.get("action_items", []):
            msg += f"• [{item.get('priority','').upper()}] {item.get('task','')} — {item.get('assignee','?')}\n"
        self.meet_client.send_raw(msg)

        # Switch to minutes tab
        self._switch_tab(3)

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        self._active_tab = idx
        self._frame_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setObjectName("tab_btn_active" if i == idx else "tab_btn")
            s = btn.style()
            if s:
                s.unpolish(btn); s.polish(btn)

    # ── Platform selection ────────────────────────────────────────────────────

    def _select_platform(self, plat: str):
        self._btn_meet.setObjectName("btn_platform_active" if plat == "meet" else "btn_platform")
        self._btn_teams.setObjectName("btn_platform_active" if plat == "teams" else "btn_platform")
        for btn in (self._btn_meet, self._btn_teams):
            s = btn.style()
            if s: s.unpolish(btn); s.polish(btn)
        placeholder = "Dán link Google Meet vào đây…" if plat == "meet" else "Dán link Microsoft Teams vào đây…"
        self._link_input.setPlaceholderText(placeholder)

    # ── Join ─────────────────────────────────────────────────────────────────

    def _on_join_clicked(self):
        url = self._link_input.text().strip()
        if not url:
            self._link_input.setPlaceholderText("⚠ Hãy dán link trước!")
            return
        self._pending_join_url = url
        self.meet_client.join_meeting(url)
        self._switch_to_main(url)
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._delayed_start_session)
        t.start(2000)
        self._join_delay_timer = t

    def _switch_to_main(self, url: str):
        display = url.replace("https://", "").replace("http://", "")
        self._mini_url.setText(display[:38] + ("…" if len(display) > 38 else ""))
        self._stack.setCurrentIndex(1)

    def _switch_to_splash(self):
        self._stack.setCurrentIndex(0)

    # ── Session ───────────────────────────────────────────────────────────────

    def _start_session(self):
        self.session_id = str(uuid.uuid4())
        self.image_handler = ImageHandler(self.session_id, API_KEY)
        self.ws_client = ParalineWSClient(
            server_ws_url=SERVER_WS, session_id=self.session_id, api_key=API_KEY,
            on_subtitle=     lambda t, ms: self.sig_subtitle.emit(t, ms),
            on_inbound_audio=lambda b64:   self.sig_tts_audio.emit(b64),
            on_outbound_text=lambda o, t:  self.sig_outbound_text.emit(o, t),
        )
        if self.ws_client.inbound_only:
            self.trans_frame.set_inbound_only(True)
            logger.info("UI: Chế độ Inbound Only được kích hoạt")

        self.ws_client.start()
        self.audio_mgr.start(
            inbound_cb=self.ws_client.send_inbound_chunk,
            outbound_cb=self.ws_client.send_outbound_chunk,
        )
        self._set_status("live", "● LIVE")
        self._btn_end.setEnabled(True)
        self.meet_client.send_welcome()
        self._add_trans_item("", "✅ Phiên dịch đã bắt đầu", 0)
        self._add_chat_bubble("Paraline", "✅ Phiên dịch đã bắt đầu", outbound=True)
        logger.info(f"Session started: {self.session_id[:8]}")

    def _stop_session(self):
        if self.ws_client:
            self.ws_client.stop()
        self.audio_mgr.stop()
        self._set_status("idle", "● IDLE")
        self._btn_end.setEnabled(False)
        self._get_meeting_minutes()

    def _delayed_start_session(self):
        if not self.session_id:
            self._start_session()

    def _get_meeting_minutes(self):
        if not self.session_id:
            return
        self.trans_frame.add_trans_item("", "⏳ Đang tạo biên bản cuộc họp…", 0)
        self._minutes_worker = MeetingMinutesWorker(self.session_id)
        self._minutes_worker.finished.connect(self._on_minutes_success)
        self._minutes_worker.error.connect(self._on_minutes_error)
        self._minutes_worker.start()

    def _on_minutes_success(self, data: dict):
        self._show_minutes(data)
        QTimer.singleShot(3000, self._switch_to_splash)

    def _on_minutes_error(self, err: str):
        logger.error(f"Meeting minutes error: {err}")
        self.trans_frame.add_trans_item("", f"❌ Lỗi tạo biên bản: {err}", 0)
        QTimer.singleShot(3000, self._switch_to_splash)

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_subtitle(self, text: str, latency_ms: float):
        self._add_trans_item("", text, latency_ms)

    def _on_outbound_text(self, original: str, translated: str):
        self._add_trans_item(original[:60], translated, 0)
        self._add_chat_bubble("Paraline → Meet", translated, outbound=True)
        self._outbound_log.append(f"→ {translated}")
        sb = self._outbound_log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())
        self.meet_client.send_translation(original, translated)

    def _on_tts_audio(self, audio_b64: str):
        self.audio_mgr.play_tts(audio_b64)

    def _on_image_paste(self, pil_img, src_lang="eng_Latn"):
        if not self.session_id:
            self.trans_frame.add_trans_item("", "⚠️ Cần bắt đầu phiên trước khi dịch ảnh", 0)
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
        self._switch_to_main(join_url or "—")
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
            self.trans_frame.add_trans_item("", "❌ Mock test thất bại — kiểm tra kết nối server.", 0)
            return
        self.trans_frame.add_trans_item("", "✅ Mock test hoàn tất", 0)
        for item in results:
            self.sig_outbound_text.emit(
                item.get("original", "")[:50],
                item.get("translated", "")[:60],
            )

    # ── Signals wiring ────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.sig_subtitle.connect(self._on_subtitle)
        self.sig_outbound_text.connect(self._on_outbound_text)
        self.sig_tts_audio.connect(self._on_tts_audio)
        self.sig_img_result.connect(self._img_panel.show_result)
        self.sig_img_error.connect(self._img_panel.show_error)
        self.sig_meeting_started.connect(self._on_meeting_started)
        self.sig_meeting_ended.connect(self._on_meeting_ended)
        self.sig_mock_result.connect(self._on_mock_result)

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
        if s:
            s.unpolish(self._status_pill)
            s.polish(self._status_pill)

    # ── Drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, a0):
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = a0.globalPosition().toPoint()

    def mouseMoveEvent(self, a0):
        if a0 and a0.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(self.pos() + a0.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = a0.globalPosition().toPoint()

    # ── Clipboard paste ───────────────────────────────────────────────────────

    def _handle_paste(self):
        from PyQt6.QtWidgets import QApplication as _App
        from PIL import Image as PILImage
        import io
        from PyQt6.QtCore import QByteArray, QBuffer
        cb = _App.clipboard()
        if not cb:
            return
        m = cb.mimeData()
        if not m:
            return
        if m.hasImage():
            q = cb.image()
            if q and not q.isNull():
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QBuffer.OpenModeFlag.WriteOnly)
                q.save(buf, "PNG")
                pil = PILImage.open(io.BytesIO(ba.data())).convert("RGB")
                self._switch_tab(2)  # Switch to Slide tab
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
        if self.ws_client:
            self.ws_client.stop()
        self.audio_mgr.stop()
        super().closeEvent(a0)


import sys
from PyQt6.QtWidgets import QApplication
# from client.ui.ui_test import ParalineMainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Paraline MSAgent")
    window = ParalineMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()