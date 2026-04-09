from PyQt6.QtWidgets import QWidget, QLabel, QScrollArea
from PyQt6.QtCore import Qt


def card(obj_name: str) -> QWidget:
    w = QWidget()
    w.setObjectName(obj_name)
    return w


def label(text: str, obj_name: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName(obj_name)
    return l


def scroll_wrap(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return sa