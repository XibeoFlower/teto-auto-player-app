"""Danh mục trượt từ bên trái, phủ lên nội dung chính (theo TetoTranscriber)."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

SIDEBAR_W = 230
MARGIN = 8
DURATION_MS = 280
ICON_PX = 18


class Sidebar(QFrame):
    """Panel con của cửa sổ chính; chỉ animate thuộc tính `pos` nên trượt rất mượt."""

    itemChosen = Signal(str)

    def __init__(self, parent: QWidget, items: list[tuple[str, str, QIcon | None]],
                 title: str = "tetoMIDI"):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._open = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 20, 14, 20)
        lay.setSpacing(6)

        label = QLabel(title)
        label.setObjectName("sbTitle")
        lay.addWidget(label)
        lay.addSpacing(12)

        for key, text, icon in items:
            btn = QPushButton(text)
            btn.setObjectName("menu")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon is not None:
                btn.setIcon(icon)
                btn.setIconSize(QSize(ICON_PX, ICON_PX))
            btn.clicked.connect(lambda *_, k=key: self._choose(k))
            lay.addWidget(btn)
        lay.addStretch()

        # kích thước cố định, tính một lần theo chiều cao cửa sổ
        self.resize(SIDEBAR_W, parent.height() - 2 * MARGIN)

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._after_anim)
        self.hide()

    def fit(self) -> None:
        """Cập nhật chiều cao khi cửa sổ chính đổi kích thước."""
        self.resize(SIDEBAR_W, self.parentWidget().height() - 2 * MARGIN)

    def _closed_pos(self) -> QPoint:
        return QPoint(-SIDEBAR_W - MARGIN, MARGIN)

    def _opened_pos(self) -> QPoint:
        return QPoint(MARGIN, MARGIN)

    def _run(self, target: QPoint) -> None:
        # bắt đầu từ vị trí hiện tại nên đổi chiều giữa chừng vẫn mượt
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.start()

    def is_open(self) -> bool:
        return self._open

    def show_panel(self) -> None:
        if self._open:
            return
        self._open = True
        if not self.isVisible():
            self.move(self._closed_pos())
        self.show()
        self.raise_()
        self._run(self._opened_pos())

    def hide_panel(self) -> None:
        if not self._open:
            return
        self._open = False
        self._run(self._closed_pos())

    def toggle_panel(self) -> None:
        if self._open:
            self.hide_panel()
        else:
            self.show_panel()

    def _after_anim(self) -> None:
        # chỉ ẩn khi animation đóng đã chạy xong (không bị hủy vì mở lại)
        if not self._open:
            self.hide()

    def _choose(self, key: str) -> None:
        self.hide_panel()
        self.itemChosen.emit(key)

    def mousePressEvent(self, e):
        e.accept()  # bấm vào nền danh mục không kéo cửa sổ chính
