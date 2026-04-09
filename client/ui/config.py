import os

SERVER_WS   = os.getenv("PARALINE_SERVER_WS",   "ws://127.0.0.1:8056")
SERVER_REST = os.getenv("PARALINE_SERVER_REST",  "http://127.0.0.1:8056")
API_KEY     = os.getenv("CLIENT_API_KEY", "paraline_client_secret_key_local")

STYLE = """
* { font-family: 'Segoe UI Variable', 'Segoe UI', Arial, sans-serif; }

#panel {
    background: #f0f2ff;
    border-left: 1px solid rgba(99,102,241,0.18);
}

QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(99,102,241,0.3); border-radius: 2px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: rgba(99,102,241,0.55); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* ── Header gradient strip ───────────────────── */
#header_strip {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #818cf8);
    border-radius: 0px;
}

#title_label { color: #ffffff; font-size: 12px; font-weight: 800; letter-spacing: 1.5px; }

#status_dot { font-size: 9px; padding: 2px 9px; border-radius: 10px; font-weight: 700; letter-spacing: 0.4px; }
#status_idle      { background: rgba(255,255,255,0.2);  color: #fff; border: 1px solid rgba(255,255,255,0.3); }
#status_active    { background: rgba(255,255,255,0.25); color: #fff; border: 1px solid rgba(255,255,255,0.4); }
#status_warning   { background: rgba(251,191,36,0.3);   color: #fef3c7; border: 1px solid rgba(251,191,36,0.5); }
#status_finishing { background: rgba(251,191,36,0.3);   color: #fef3c7; border: 1px solid rgba(251,191,36,0.5); }

/* ── Monitor badge (below header) ────────────── */
#monitor_badge { color: #a5b4fc; font-size: 9.5px; }

/* ── Start button ────────────────────────────── */
QPushButton#btn_start {
    background: #6366f1; color: #fff; border: none; border-bottom: 2px solid #4338ca;
    padding: 9px 0; border-radius: 7px; font-weight: 700; font-size: 11px; letter-spacing: 0.3px;
}
QPushButton#btn_start:hover   { background: #818cf8; }
QPushButton#btn_start:pressed { background: #4f46e5; border-bottom: 1px solid #4338ca; padding-top: 10px; }
QPushButton#btn_start:disabled { background: #e0e7ff; color: #a5b4fc; border: 1px solid #c7d2fe; border-bottom: 2px solid #c7d2fe; }

/* ── Stop button ─────────────────────────────── */
QPushButton#btn_stop {
    background: #fff; color: #ef4444; border: 1.5px solid #fca5a5; border-bottom: 2px solid #f87171;
    padding: 9px 0; border-radius: 7px; font-weight: 700; font-size: 11px;
}
QPushButton#btn_stop:hover   { background: #fff1f2; border-color: #f87171; }
QPushButton#btn_stop:pressed { background: #fee2e2; border-bottom: 1px solid #f87171; padding-top: 10px; }
QPushButton#btn_stop:disabled { background: #f9fafb; color: #d1d5db; border: 1.5px solid #e5e7eb; border-bottom: 2px solid #e5e7eb; }

/* ── Secondary button ───────────────────────── */
QPushButton#btn_secondary {
    background: #f5f3ff; color: #6d28d9; border: 1.5px solid #ddd6fe; padding: 9px 0; border-radius: 10px; font-size: 12px; font-weight: 600;
}
QPushButton#btn_secondary:hover   { background: #ede9fe; border-color: #c4b5fd; }
QPushButton#btn_secondary:pressed { background: #ddd6fe; }
QPushButton#btn_secondary:disabled { background: #f9fafb; color: #d1d5db; border-color: #e5e7eb; }

/* ── Meet card ──────────────────────────────── */
#meet_card { background: #f8f9ff; border: 1.5px solid #e0e7ff; border-radius: 10px; }
#meet_card_label { color: #818cf8; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }

/* ── Join button ────────────────────────────── */
QPushButton#btn_join { background: #4f46e5; color: #fff; border: none; border-radius: 7px; padding: 6px 14px; font-size: 11px; font-weight: 700; }
QPushButton#btn_join:hover   { background: #6366f1; }
QPushButton#btn_join:pressed { background: #4338ca; }

/* ── URL input ──────────────────────────────── */
QLineEdit { background: transparent; color: #374151; border: none; font-size: 12px; selection-background-color: #c7d2fe; }
QLineEdit:focus { color: #111827; }

/* ── ComboBox ───────────────────────────────── */
QComboBox { background: #f5f3ff; color: #6d28d9; border: 1.5px solid #ddd6fe; border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: 600; min-width: 110px; }
QComboBox:hover { border-color: #c4b5fd; }
QComboBox::drop-down { border: none; width: 16px; }
QComboBox QAbstractItemView { background: #fff; color: #374151; border: 1.5px solid #ddd6fe; selection-background-color: #ede9fe; selection-color: #6d28d9; outline: none; }

/* ── Image drop ─────────────────────────────── */
#image_drop { background: #faf5ff; color: #7c3aed; border: 2px dashed #c4b5fd; border-radius: 10px; font-size: 12px; font-weight: 600; }
#image_drop:hover { background: #f3e8ff; border-color: #a78bfa; }

/* ── Outbound log ───────────────────────────── */
#outbound_log { background: #eff6ff; color: #2563eb; font-size: 12px; border: 1.5px solid #bfdbfe; border-radius: 10px; padding: 6px 10px; }

/* ── Section labels ─────────────────────────── */
#section_label { color: #9ca3af; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }

/* ── Progress bar ───────────────────────────── */
QProgressBar { background: #e0e7ff; border: none; border-radius: 3px; height: 4px; }
QProgressBar::chunk { background: #6366f1; border-radius: 3px; }
"""
