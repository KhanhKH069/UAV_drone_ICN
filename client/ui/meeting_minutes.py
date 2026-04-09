import requests
from PyQt6.QtCore import pyqtSignal, QThread
from client.ui.config import SERVER_REST

class MeetingMinutesWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id
        
    def run(self):
        try:
            r = requests.post(f"{SERVER_REST}/agent/summarize/{self.session_id}", timeout=90)
            if r.ok:
                self.finished.emit(r.json())
            else:
                self.error.emit(f"HTTP {r.status_code}")
        except Exception as e:
            self.error.emit(str(e))
