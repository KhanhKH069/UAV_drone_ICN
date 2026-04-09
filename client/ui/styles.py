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
QPushButton#btn_go:hover { background: #00c88c; }
QPushButton#btn_go:disabled { background: #cccccc; color: #888888; }

/* ── Mini header ── */
QWidget#mini_header { background: #111111; }
QLabel#mini_brand_para {
    font-size: 15px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;
}
QLabel#mini_brand_line {
    font-size: 15px; font-weight: 800; color: #00e5a0; letter-spacing: -0.5px;
}
QLabel#mini_url { font-size: 10px; color: rgba(255,255,255,0.45); }
QLabel#status_live {
    font-size: 9px; font-weight: 700; color: #00e5a0;
    background: rgba(0,229,160,0.15); border: 1px solid rgba(0,229,160,0.3);
    border-radius: 10px; padding: 3px 8px; letter-spacing: 0.8px;
}
QLabel#status_idle {
    font-size: 9px; font-weight: 700; color: #888888;
    background: rgba(128,128,128,0.12); border: 1px solid rgba(128,128,128,0.25);
    border-radius: 10px; padding: 3px 8px; letter-spacing: 0.8px;
}

/* ── Tab bar ── */
QWidget#tab_bar {
    background: #f7fdfb;
    border-bottom: 1px solid rgba(0,229,160,0.2);
}
QPushButton#tab_btn {
    background: transparent; border: 1px solid transparent;
    border-radius: 8px; color: #999999;
    font-size: 10px; font-weight: 700; padding: 6px 0; letter-spacing: 0.3px;
}
QPushButton#tab_btn:hover { color: #555555; }
QPushButton#tab_btn_active {
    background: #ffffff; border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px; color: #111111;
    font-size: 10px; font-weight: 700; padding: 6px 0; letter-spacing: 0.3px;
}

/* ── Frame: Translation ── */
QWidget#trans_item {
    background: #f7fdfb; border: 1px solid rgba(0,229,160,0.2); border-radius: 9px;
}
QWidget#trans_item_live {
    background: #e6fff5; border: 1px solid #00e5a0; border-radius: 9px;
}
QLabel#trans_src  { font-size: 11px; color: #999999; }
QLabel#trans_dst  { font-size: 13px; font-weight: 600; color: #111111; }
QLabel#trans_badge { font-size: 9px; font-weight: 700; color: #00a875; }
QLabel#trans_listening { font-size: 11px; font-weight: 700; color: #00a875; }

/* ── Frame: Chat ── */
QWidget#chat_bubble {
    background: #f7fdfb; border: 1px solid rgba(0,229,160,0.2); border-radius: 9px;
}
QWidget#chat_bubble_out {
    background: #e6fff5; border: 1px solid rgba(0,229,160,0.5); border-radius: 9px;
}
QLabel#chat_who    { font-size: 9px; font-weight: 700; color: #999999; letter-spacing: 0.5px; }
QLabel#chat_who_me { font-size: 9px; font-weight: 700; color: #00a875; letter-spacing: 0.5px; }
QLabel#chat_text   { font-size: 12px; color: #111111; }

/* ── Frame: Slide ── */
QWidget#slide_drop {
    background: #f7fdfb; border: 2px dashed rgba(0,229,160,0.4); border-radius: 9px;
}
QLabel#slide_hint  { font-size: 11px; font-weight: 600; color: #999999; }
QWidget#slide_result {
    background: #e6fff5; border: 1px solid rgba(0,229,160,0.5); border-radius: 9px;
}

/* ── Frame: Minutes ── */
QWidget#minutes_body {
    background: #f7fdfb; border: 1px solid rgba(0,229,160,0.2); border-radius: 9px;
}
QWidget#action_item {
    background: #f7fdfb; border: 1px solid rgba(0,229,160,0.2); border-radius: 9px;
}
QLabel#pri_high {
    background: #fff0f0; color: #c0392b;
    font-size: 9px; font-weight: 800; border-radius: 4px; padding: 2px 5px;
}
QLabel#pri_med {
    background: #fffbe6; color: #b07d00;
    font-size: 9px; font-weight: 800; border-radius: 4px; padding: 2px 5px;
}
QLabel#section_label {
    font-size: 9px; font-weight: 700; color: #999999; letter-spacing: 1.5px;
}

/* ── Scrollarea ── */
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { width: 4px; background: transparent; }
QScrollBar::handle:vertical {
    background: rgba(0,229,160,0.35); border-radius: 2px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Control bar ── */
QWidget#ctrl_bar {
    background: #f7fdfb; border-top: 1px solid rgba(0,229,160,0.2);
}
QPushButton#btn_end {
    background: #fff5f5; border: 1px solid #fcc; border-radius: 8px;
    color: #c0392b; font-size: 11px; font-weight: 700; padding: 9px 0;
}
QPushButton#btn_end:hover { background: #ffe8e8; }
QPushButton#btn_minutes {
    background: #ffffff; border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px; color: #00a875;
    font-size: 11px; font-weight: 700; padding: 9px 12px;
}
QPushButton#btn_minutes:hover { background: #e6fff5; }
QPushButton#btn_quit {
    background: transparent; border: none;
    color: rgba(255,255,255,0.5); font-size: 18px; font-weight: 300; padding: 0;
}
QPushButton#btn_quit:hover { color: #ffffff; }

/* ── Outbound log ── */
QTextEdit#outbound_log {
    background: #f7fdfb; border: 1px solid rgba(0,229,160,0.2);
    border-radius: 9px; font-size: 11px; color: #555555; padding: 6px;
}

/* ── ComboBox ── */
QComboBox {
    background: #f7fdfb;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    padding: 6px 12px;
    color: #111111;
    font-size: 11px;
    font-weight: 600;
}
QComboBox:hover, QComboBox:focus {
    border-color: #00e5a0;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: none;
}
/* Use standard triangle or default for down arrow */
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    color: #111111;
    selection-background-color: #e6fff5;
    selection-color: #00a875;
    outline: none; /* Hide default dotted focus outline */
}
QComboBox QAbstractItemView::item {
    font-size: 11px;
    font-weight: 600;
    min-height: 28px;
    padding: 4px 8px;
    color: #333333;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #e6fff5;
    color: #00a875;
    border-radius: 4px;
}

/* ── Chat Input Bar ── */
QWidget#chat_input_bar {
    background: #f7fdfb;
    border-top: 1px solid rgba(0,229,160,0.2);
}
QLabel#chat_input_label {
    font-size: 9px;
    font-weight: 700;
    color: #999999;
    letter-spacing: 1.5px;
}
QLabel#chat_input_status {
    font-size: 9px;
    font-weight: 600;
    color: #00a875;
}
QComboBox#combo_src_lang {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 6px;
    padding: 2px 8px;
    color: #333333;
    font-size: 10px;
    font-weight: 600;
    min-width: 100px;
}
QComboBox#combo_src_lang:hover {
    border-color: #00c88c;
}
QTextEdit#chat_input {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.35);
    border-radius: 8px;
    padding: 6px 10px;
    color: #111111;
    font-size: 12px;
}
QTextEdit#chat_input:focus {
    border-color: #00e5a0;
}
QPushButton#btn_mic {
    background: #ffffff;
    border: 1px solid rgba(0,229,160,0.4);
    border-radius: 8px;
    color: #333333;
    font-size: 11px;
    font-weight: 700;
    padding: 7px 0;
}
QPushButton#btn_mic:hover {
    border-color: #00c88c;
    color: #00a875;
}
QPushButton#btn_mic_active {
    background: #fff0f0;
    border: 1px solid #f5a0a0;
    border-radius: 8px;
    color: #c0392b;
    font-size: 11px;
    font-weight: 700;
    padding: 7px 0;
}
QPushButton#btn_mic_active:hover {
    background: #ffe4e4;
}
QPushButton#btn_send {
    background: #00e5a0;
    border: none;
    border-radius: 8px;
    color: #111111;
    font-size: 11px;
    font-weight: 800;
    padding: 7px 0;
}
QPushButton#btn_send:hover { background: #00c88c; }
QPushButton#btn_send:disabled { background: #cccccc; color: #888888; }
"""