"""Tiện ích chung cho các trang: hàng cài đặt, steppers, tìm kiếm, chip hotkey."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from .glassbtn import Badge, GlassButton, GlassLineEdit, GlassSlider, paint_glass


def fit_text(text: str, width: int, size: int, bold: bool = False) -> str:
    """Rút gọn bằng dấu … cho vừa ``width`` px (xấp xỉ 0.6 * size mỗi ký tự)."""
    if width <= 0:
        return text
    approx = max(4, int(size * 0.58)) * (1.12 if bold else 1.0)
    if len(text) * approx <= width:
        return text
    while len(text) > 1 and len(text + "…") * approx > width:
        text = text[:-1]
    return text.rstrip() + "…"


class EllipsisLabel(QLabel):
    """Nhãn một dòng tự rút gọn bằng dấu … khi hết chỗ."""

    def __init__(self, text: str = "", size: int = 13, color: str | None = None, parent=None):
        super().__init__(parent)
        self._full = text
        self._size = size
        self._color = color
        if color:
            self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setText(text)

    def set_text(self, text: str, color: str | None = None) -> None:
        self._full = text
        if color and color != self._color:
            self._color = color
            self.setStyleSheet(f"color: {color}; background: transparent;")
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        self.setText(fit_text(self._full, self.width() - 4, self._size, self.font().bold()))


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("section")


class PageTitle(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("page-title")


class Row(QWidget):
    """Một hàng cài đặt: nhãn bên trái, điều khiển bên phải (+ dòng gợi ý dưới)."""

    def __init__(self, label: str, widget: QWidget, hint: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(label)
        lab.setObjectName("row-label")
        top.addWidget(lab)
        top.addStretch()
        top.addWidget(widget)
        lay.addLayout(top)
        if hint:
            h = QLabel(hint)
            h.setObjectName("hint")
            h.setWordWrap(True)
            lay.addWidget(h)


class ValueSlider(QWidget):
    """GlassSlider + số đọc bên phải."""

    def __init__(self, vmin: float, vmax: float, value: float, command, step: float = 1.0,
                 fmt: str = "{:g}", width: int = 220, parent=None):
        super().__init__(parent)
        self.vmin, self.vmax, self.step, self.fmt, self.command = vmin, vmax, step, fmt, command
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.slider = GlassSlider(on_commit=self._changed, on_drag=self._changed)
        self.slider.setFixedWidth(width)
        lay.addWidget(self.slider)
        self.readout = QLabel("")
        self.readout.setObjectName("status")
        lay.addWidget(self.readout)
        self.set(value)

    def _value(self, frac: float) -> float:
        v = self.vmin + (self.vmax - self.vmin) * frac
        v = round(v / self.step) * self.step
        return min(max(v, self.vmin), self.vmax)

    def _changed(self, frac: float):
        v = self._value(frac)
        self.readout.setText(self.fmt.format(v))
        self.command(v)

    def set(self, value: float):
        frac = (value - self.vmin) / (self.vmax - self.vmin) if self.vmax > self.vmin else 0.0
        self.slider.set_fraction(frac)
        self.readout.setText(self.fmt.format(value))


class Stepper(QWidget):
    """Chọn giá trị từ danh sách: nút ◀ / nhãn / nút ▶."""

    def __init__(self, options: list[str], index: int, command, width: int = 130, parent=None):
        super().__init__(parent)
        self.options = options
        self.index = max(0, min(index, len(options) - 1))
        self.command = command
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        prev = GlassButton("◀")
        prev.setObjectName("iconbtn")
        prev.clicked.connect(lambda: self._step(-1))
        self.label = QLabel(self.options[self.index])
        self.label.setObjectName("badge")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedWidth(width)
        nxt = GlassButton("▶")
        nxt.setObjectName("iconbtn")
        nxt.clicked.connect(lambda: self._step(1))
        lay.addWidget(prev)
        lay.addWidget(self.label)
        lay.addWidget(nxt)

    def _step(self, d: int):
        self.set((self.index + d) % len(self.options))

    def set(self, index: int):
        self.index = index % len(self.options)
        self.label.setText(self.options[self.index])
        self.command(self.index)

    def display(self, index: int):
        """Cap nhat nhan khi cfg doi tu noi khac (khong kich hoat command)."""
        self.index = index % len(self.options)
        self.label.setText(self.options[self.index])


class SearchBox(GlassLineEdit):
    """Ô tìm kính (MIDI Hub): gõ xong 350 ms hoặc Enter mới gọi on_search."""

    HINT = "Search songs"

    def __init__(self, on_search, parent=None):
        super().__init__(parent, self.HINT)
        self.on_search = on_search
        self.setFixedHeight(40)
        self.setClearButtonEnabled(True)
        self._job = None
        self._sent = ""
        self.textChanged.connect(self._typed)
        self.returnPressed.connect(lambda: self._fire(force=True))

    def _typed(self, _text):
        if self._job is not None:
            self._job.stop()
        self._job = QTimer(self)
        self._job.setSingleShot(True)
        self._job.setInterval(350)
        self._job.timeout.connect(self._fire)
        self._job.start()

    def _fire(self, force: bool = False):
        self._job = None
        text = self.text().strip()
        if force or text != self._sent:
            self._sent = text
            self.on_search(text)


class HotkeyChip(GlassButton):
    """Chip phím tắt: bấm rồi nhấn phím mới để gán lại (app lo phần bắt phím)."""

    def __init__(self, name: str, text: str, on_pick, parent=None):
        super().__init__(text, parent)
        self.name = name
        self.setObjectName("tool")
        self.setFixedHeight(30)
        self.setMinimumWidth(52)
        self.clicked.connect(lambda: on_pick(name))

    def set_key(self, key: str):
        self.setText(key)


def pick_midi_file(parent, start_dir: str = "") -> str:
    path, _f = QFileDialog.getOpenFileName(
        parent, "Select MIDI file", start_dir,
        "MIDI files (*.mid *.midi *.MID *.MIDI);;All files (*)")
    return path


def pick_midi_files(parent, start_dir: str = "") -> list[str]:
    paths, _f = QFileDialog.getOpenFileNames(
        parent, "Add MIDI files", start_dir,
        "MIDI files (*.mid *.midi *.MID *.MIDI);;All files (*)")
    return list(paths)


def pick_folder(parent, title: str = "Choose folder") -> str:
    return QFileDialog.getExistingDirectory(parent, title, "")


class ScrollArea(QScrollArea):
    """Vùng cuộn trong suốt cho các trang dài (Settings, Hub)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def hStretch() -> "object":
    from PySide6.QtWidgets import QSpacerItem, QSizePolicy
    return QSpacerItem(1, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


def make_v(parent=None) -> QVBoxLayout:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    return lay


def make_h(parent=None) -> QHBoxLayout:
    lay = QHBoxLayout(parent)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    return lay
