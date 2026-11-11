"""Intro khi mở app: logo hiện ở giữa màn hình rồi phóng to dần và tan đi, để lộ cửa sổ chính."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPauseAnimation, QRectF, QSequentialAnimationGroup, Qt, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

LOGO_SIZE = 190.0   # px logo ở trạng thái nghỉ
ZOOM_TO = 7.0       # logo phóng lên bấy nhiêu lần ở cuối


class IntroSplash(QWidget):
    reveal = Signal()    # bắt đầu giai đoạn phóng to: lúc này hiện cửa sổ chính
    finished = Signal()  # xong hoàn toàn

    def __init__(self, logo: QPixmap):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._logo = logo
        self._scale = 0.6
        self._alpha = 0.0
        self._bg = 0.0
        self._revealed = False
        self.setGeometry(QGuiApplication.primaryScreen().geometry())

        def anim(ms: int, curve: QEasingCurve.Type, slot) -> QVariantAnimation:
            a = QVariantAnimation(self)
            a.setDuration(ms)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.setEasingCurve(curve)
            a.valueChanged.connect(slot)
            return a

        self._grow = anim(550, QEasingCurve.Type.OutCubic, self._on_grow)
        self._zoom = anim(650, QEasingCurve.Type.InCubic, self._on_zoom)
        self._seq = QSequentialAnimationGroup(self)
        self._seq.addAnimation(self._grow)
        self._seq.addAnimation(QPauseAnimation(350, self))
        self._seq.addAnimation(self._zoom)
        self._seq.currentAnimationChanged.connect(self._on_step)
        self._seq.finished.connect(self._done)

    def start(self) -> None:
        self.show()
        self._seq.start()

    def _on_grow(self, v) -> None:
        v = float(v)
        self._scale, self._alpha, self._bg = 0.6 + 0.4 * v, v, v
        self.update()

    def _on_zoom(self, v) -> None:
        v = float(v)
        self._scale, self._alpha, self._bg = 1.0 + (ZOOM_TO - 1.0) * v, 1.0 - v, 1.0 - v
        self.update()

    def _on_step(self, current) -> None:
        if current is self._zoom:
            self._emit_reveal()

    def _emit_reveal(self) -> None:
        if not self._revealed:
            self._revealed = True
            self.reveal.emit()

    def _done(self) -> None:
        self._emit_reveal()
        self.close()
        self.finished.emit()

    def mousePressEvent(self, _e) -> None:  # bấm để bỏ qua intro
        self._seq.stop()
        self._done()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(8, 8, 10, int(245 * self._bg)))
        if not self._logo.isNull():
            p.setOpacity(max(0.0, min(1.0, self._alpha)))
            p.translate(self.width() / 2, self.height() / 2)
            p.scale(self._scale, self._scale)
            half = LOGO_SIZE / 2
            p.drawPixmap(QRectF(-half, -half, LOGO_SIZE, LOGO_SIZE), self._logo, QRectF(self._logo.rect()))
        p.end()
