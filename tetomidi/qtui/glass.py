"""Giao diện kính tối giản (theo TetoTranscriber): QSS + hiệu ứng acrylic trên Windows."""
from __future__ import annotations

import ctypes
import os

STYLE = """
QWidget { color: #f2f2f5; font-family: "Segoe UI", sans-serif; font-size: 13px; }

QLabel#title { font-size: 24px; font-weight: bold; background: transparent; }
QLabel#page-title { font-size: 22px; font-weight: bold; background: transparent; }
QLabel#sub { color: rgba(255,255,255,120); font-size: 12px; background: transparent; }
QLabel#file { color: rgba(255,255,255,210); font-size: 14px; background: transparent; }
QLabel#status { color: rgba(255,255,255,150); font-size: 12px; background: transparent; }
QLabel#row-label { font-size: 15px; background: transparent; }
QLabel#hint { color: rgba(255,255,255,105); font-size: 11px; background: transparent; }
QLabel#section { font-size: 19px; font-weight: bold; background: transparent; }
QLabel#badge { font-weight: bold; background: transparent; }
QLabel#chip-label { color: rgba(255,255,255,150); font-size: 12px; background: transparent; }

QPushButton { border-radius: 16px; padding: 8px 18px; }
/* Nền các nút do GlassButton (glassbtn.py) tự vẽ nên QSS để trong suốt. */
QPushButton#primary {
    color: #050505; font-weight: bold; padding: 10px 26px;
    border: none; background: transparent;
}
QPushButton#primary:disabled { color: rgba(255,255,255,90); }
QPushButton#ghost { color: #f2f2f5; border: none; background: transparent; }
QPushButton#ghost:disabled { color: rgba(255,255,255,70); }
QPushButton#tool {
    padding: 7px 16px; border-radius: 12px; color: #f2f2f5;
    border: none; background: transparent;
}
QPushButton#tool:disabled { color: rgba(255,255,255,70); }
QPushButton#iconbtn {
    border: none; background: transparent;
    min-width: 34px; max-width: 34px;
    min-height: 34px; max-height: 34px;
    padding: 0; font-size: 15px;
}
QPushButton#mini {
    border: none; background: transparent; font-size: 11px; padding: 0;
}

QFrame#sidebar {
    background: rgba(18,18,21,238);
    border: 1px solid rgba(255,255,255,45);
    border-radius: 22px;
}
QLabel#sbTitle {
    font-size: 17px; font-weight: bold;
    background: transparent; border: none; padding: 0 6px;
}
QPushButton#menu {
    text-align: left;
    padding: 11px 14px;
    border-radius: 14px;
    font-size: 14px;
    color: #f2f2f5;
    background: transparent;
    border: 1px solid transparent;
}
QPushButton#menu:hover { background: rgba(255,255,255,30); }
QPushButton#menu:pressed { background: rgba(255,255,255,46); }

QPlainTextEdit#console {
    background: rgba(6,6,8,215);
    border: 1px solid rgba(255,255,255,30);
    border-radius: 12px;
    color: #cfd2da;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    padding: 8px;
}

QMainWindow, QWidget#editor, QWidget#glassRoot { background: transparent; }
QScrollArea { background: transparent; border: none; }
QAbstractScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,50); border-radius: 5px; min-height: 32px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,50); border-radius: 5px; min-width: 32px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent; border: none;
}

QProgressBar { background: rgba(255,255,255,25); border: none; border-radius: 4px; }
QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(255,255,255,40), stop:0.5 #ffffff, stop:1 rgba(255,255,255,40));
}

QDialog { background: #0b0b0d; }
QLineEdit, QComboBox, QSpinBox {
    background: rgba(255,255,255,18);
    border: 1px solid rgba(255,255,255,45);
    border-radius: 12px;
    padding: 8px 12px;
    color: #f2f2f5;
    selection-background-color: rgba(255,255,255,70);
}
QLineEdit { border-radius: 14px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid rgba(255,255,255,150);
    background: rgba(255,255,255,28);
}
QComboBox QAbstractItemView {
    background: #141416;
    selection-background-color: rgba(255,255,255,40);
    border: 1px solid rgba(255,255,255,40);
    color: #f2f2f5;
}
QComboBox::drop-down { border: none; width: 22px; }
QListWidget {
    background: rgba(255,255,255,14);
    border: 1px solid rgba(255,255,255,32);
    border-radius: 14px;
    color: #e2e2e6;
    padding: 4px;
}
QListWidget::item { padding: 6px 8px; border-radius: 8px; }
QListWidget::item:selected { background: rgba(255,255,255,40); color: #ffffff; }
QListWidget::item:hover { background: rgba(255,255,255,24); }
QCheckBox { spacing: 8px; background: transparent; }
QMessageBox { background: #0b0b0d; }
QToolTip {
    background: #141416; color: #f2f2f5;
    border: 1px solid rgba(255,255,255,60); border-radius: 8px; padding: 5px 8px;
}
"""


class _Accent(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_Accent)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def enable_acrylic(hwnd: int, tint_abgr: int = 0x99080808) -> bool:
    """Bật acrylic blur phía sau cửa sổ (Windows 10/11). Trả về False nếu không hỗ trợ."""
    if os.name != "nt":
        return False
    accent = _Accent(4, 2, tint_abgr, 0)  # 4 = ACRYLIC_BLURBEHIND
    data = _WinCompAttrData(19, ctypes.pointer(accent), ctypes.sizeof(accent))  # 19 = WCA_ACCENT_POLICY
    try:
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))
    except Exception:
        return False
