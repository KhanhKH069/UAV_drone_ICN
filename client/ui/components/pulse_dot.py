import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class PulseDot(QWidget):
    """Animated mint-green pulsing circle dùng cho splash screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._phase = (self._phase + 0.03) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2

        for i in range(3):
            phase_offset = (self._phase + i * (2 * math.pi / 3)) % (2 * math.pi)
            t = (math.sin(phase_offset) + 1) / 2
            r = int(10 + t * 28)
            alpha = int(120 * (1 - t))
            pen = QPen(QColor(0, 229, 160, alpha))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 229, 160)))
        p.drawEllipse(cx - 7, cy - 7, 14, 14)
        p.end()