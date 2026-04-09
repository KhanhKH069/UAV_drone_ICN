"""
client/meet_integration/meet_client.py
Công cụ đẩy tin nhắn từ Python sang Chrome Extension (Google Meet).
Thay thế cho TeamsClient.
"""
import logging
import os
import requests
import webbrowser

logger = logging.getLogger("paraline.meet")

# Lấy từ thư mục extension
BRIDGE_PORT = int(os.getenv("MEET_BRIDGE_PORT", "9877"))
EXTENSION_ID = os.getenv("MEET_EXTENSION_ID", "") 


class MeetClient:
    """Tương đương TeamsClient nhưng cho Google Meet qua Chrome Extension."""
    
    def __init__(self):
        self._mode = "extension"
        logger.info(f"Meet client mode: {self._mode} (Port: {BRIDGE_PORT})")

    def is_connected(self) -> bool:
        """Kiểm tra có background.js đang chạy không."""
        try:
            r = requests.get(f"http://localhost:{BRIDGE_PORT}/health", timeout=1)
            return r.status_code == 200
        except Exception:
            return False

    def set_chat_id(self, chat_id: str):
        pass # Google Meet không cần chat_id như Teams Graph API

    # ─────────────────────────────────────────────
    # Send translated text to Google Meet chat
    # ─────────────────────────────────────────────

    def send_translation(self, original: str, translated: str, tgt_lang: str = "JP") -> bool:
        """
        Gửi kết quả dịch sang Google Meet.
        Google Meet chat không hỗ trợ HTML chuẩn qua textarea,
        nên gửi dưới dạng Plain Text format.
        """
        flag = "🇯🇵" if tgt_lang.upper() in ("JP", "JA") else "🇬🇧"
        plain = f"[Paraline] {flag} {translated}  |  (VN: {original})"
        return self._send(plain)

    def send_raw(self, text: str) -> bool:
        """Gửi text thô"""
        return self._send(text)

    def send_welcome(self) -> bool:
        """Gửi tin nhắn chào mừng (tùy chọn)"""
        msg = (
            "🟠 Paraline MSAgent đã kết nối!\n"
            "- ✅ Inbound: JP/EN → 🇻🇳 (tai nghe + phụ đề)\n"
            "- ✅ Outbound: Dịch nội dung và đẩy vào Meet Chat này\n"
        )
        return self._send(msg)

    # ─────────────────────────────────────────────
    # Webhook to Chrome Extension (Native Messaging tương lai)
    # Tạm thời Chrome extension polling chưa hỗ trợ push tực tiếp từ localhost,
    # Cần Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
    # TRONG BẢN DEMO NÀY: Mình dùng workaround để Python đóng vai background app (nếu có thể),
    # nhưng Chrome background script không thể mở cổng listen TCP.
    # 
    # MONG MUỐN: Có một endpoint trên background.js nhưng extensions ko the listen port.
    # GIẢI PHÁP: Python server giữ long-polling connection đến extension.
    # Do hiện tại extension gọi đến Python theo dạng sự kiện. Tính năng send_chat đang yêu cầu
    # Extension gọi Polling tới `/poll_chat` để lấy payload.
    # ─────────────────────────────────────────────

    def _send(self, text: str) -> bool:
        """
        Đẩy text vào queue ở bridge_server (Extension Google Meet).
        Đã được bọc bằng Thread để không làm đơ giao diện chính của App khi chờ mạng.
        """
        import threading
        
        def _do_post():
            try:
                r = requests.post(
                    f"http://localhost:{BRIDGE_PORT}/enqueue",
                    json={"text": text},
                    timeout=1.5,
                )
                ok = bool(getattr(r, "ok", False))
                if not ok:
                    logger.warning(f"Meet enqueue failed: {r.status_code} {r.text[:120]}")
            except Exception as e:
                logger.warning(f"Meet enqueue error: {e}")
                
        # Ném lệnh gọi HTTP sang một luồng phụ để App hiện chữ dịch ngay lập tức
        threading.Thread(target=_do_post, daemon=True).start()
        return True

    # ─────────────────────────────────────────────
    # Meeting Join / Leave
    # ─────────────────────────────────────────────

    def join_meeting(self, join_url: str) -> bool:
        """
        Mở Google Meet URL trên browser mặc định (nên set là Chrome).
        """
        if not join_url:
            return False

        logger.info(f"Mở Google Meet link: {join_url}")
        
        try:
            # Gán thêm user=0 để mặc định chọn account auth đầu tiên của Google
            if "authuser" not in join_url:
                if "?" in join_url:
                    join_url += "&authuser=0"
                else:
                    join_url += "?authuser=0"
            
            webbrowser.open(join_url, new=2)
            logger.info("✅ Google Meet chrome tab opened")
            return True
        except Exception as e:
            logger.error(f"Browser open failed: {e}")
            return False

    def leave_meeting(self):
        """Khó có thể đóng tab Chrome từ Python. Yêu cầu user tự đóng Meet."""
        logger.info("Yêu cầu kết thúc — user cần tự tắt Meet tab")
