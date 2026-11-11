"""Nút và khung kính tự vẽ (xấp xỉ "liquid glass") — lấy từ TetoTranscriber.

Qt không đọc được điểm ảnh phía sau cửa sổ nên không làm được khúc xạ thật như vật liệu của Apple.
Ở đây vẽ lại các lớp tạo cảm giác kính dày: nền trong mờ, vệt bóng phía trên, ánh sáng hắt lên từ
đáy, viền sáng chéo và viền trong. Hover và nhấn có hiệu ứng chuyển mượt.

Kiểu nút lấy theo objectName (khớp với QSS trong glass.py):
  primary -> kính trắng sáng, discord / nút bật -> kính xanh, còn lại (ghost, tool, iconbtn) -> kính trong.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QLabel, QLineEdit, QPushButton, QSlider


def _c(r: float, g: float, b: float, a: float) -> QColor:
    return QColor(int(max(0, min(255, r))), int(max(0, min(255, g))),
                  int(max(0, min(255, b))), int(max(0, min(255, a))))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _rounded(r: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    radius = max(0.0, min(radius, r.height() / 2, r.width() / 2))
    path.addRoundedRect(r, radius, radius)
    return path


def paint_glass(
    p: QPainter,
    r: QRectF,
    radius: float,
    kind: str = "clear",
    glow: float = 0.0,
    pressed: bool = False,
    enabled: bool = True,
) -> None:
    """Vẽ một tấm kính bo tròn vào hình chữ nhật r.

    kind: "clear" (kính trong), "bright" (trắng sáng), "blue" (xanh), "panel" (khung lớn),
    "green" / "red" / "amber" (kính màu cho PLAY / STOP / PAUSE).
    glow: 0..1, mức sáng lên khi di chuột.
    """
    if r.width() < 6 or r.height() < 6:
        return
    if not enabled and kind in ("bright", "blue", "green", "red", "amber"):
        kind = "clear"
    dim = 1.0 if enabled else 0.4
    g = glow if enabled else 0.0
    h = r.height()
    path = _rounded(r, radius)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)

    # 1) nền kính
    fill = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
    if kind == "bright":
        fill.setColorAt(0.00, _c(255, 255, 255, 247))
        fill.setColorAt(0.50, _c(_lerp(232, 244, g), _lerp(235, 246, g), _lerp(244, 252, g), 240))
        fill.setColorAt(0.52, _c(_lerp(206, 220, g), _lerp(211, 224, g), _lerp(226, 236, g), 236))
        fill.setColorAt(1.00, _c(246, 248, 253, 248))
    elif kind == "blue":
        fill.setColorAt(0.0, _c(_lerp(120, 142, g), _lerp(132, 152, g), 255, 238))
        fill.setColorAt(1.0, _c(_lerp(70, 88, g), _lerp(82, 100, g), _lerp(216, 238, g), 230))
    elif kind == "green":
        fill.setColorAt(0.0, _c(_lerp(96, 116, g), _lerp(200, 218, g), _lerp(120, 138, g), 236))
        fill.setColorAt(1.0, _c(_lerp(58, 76, g), _lerp(150, 168, g), _lerp(80, 98, g), 228))
    elif kind == "red":
        fill.setColorAt(0.0, _c(_lerp(238, 252, g), _lerp(96, 116, g), _lerp(90, 110, g), 236))
        fill.setColorAt(1.0, _c(_lerp(196, 214, g), _lerp(58, 76, g), _lerp(54, 72, g), 228))
    elif kind == "amber":
        fill.setColorAt(0.0, _c(_lerp(236, 250, g), _lerp(178, 196, g), _lerp(74, 92, g), 238))
        fill.setColorAt(1.0, _c(_lerp(200, 218, g), _lerp(132, 150, g), _lerp(44, 62, g), 230))
    elif kind == "panel":
        fill.setColorAt(0.0, _c(255, 255, 255, (38 + 26 * g) * dim))
        fill.setColorAt(0.5, _c(255, 255, 255, (8 + 10 * g) * dim))
        fill.setColorAt(1.0, _c(255, 255, 255, (22 + 16 * g) * dim))
    else:
        fill.setColorAt(0.0, _c(255, 255, 255, (52 + 34 * g) * dim))
        fill.setColorAt(1.0, _c(255, 255, 255, (14 + 22 * g) * dim))
    p.fillPath(path, QBrush(fill))

    p.setClipPath(path)

    # 2) ánh sáng hắt lên từ đáy (hiệu ứng "kính dày" tụ sáng ở cạnh dưới)
    if kind != "bright":
        base = 14 if kind == "panel" else 36
        glow_a = (base + 18 * g) * dim * (0.6 if pressed else 1.0)
        band = QLinearGradient(r.left(), r.bottom(), r.left(), r.top() + h * 0.55)
        band.setColorAt(0.0, _c(255, 255, 255, glow_a))
        band.setColorAt(1.0, _c(255, 255, 255, 0))
        p.fillPath(path, QBrush(band))

    # 3) vệt bóng (specular) ở nửa trên
    if kind == "panel":
        gh = min(h * 0.24, 60.0)
        inset = radius * 0.6
        top_a = 46 + 18 * g
    else:
        gh = h * 0.46
        inset = radius * 0.55
        top_a = {"bright": 175, "blue": 112, "green": 118, "red": 118, "amber": 120}.get(kind, 98 + 44 * g)
    top_a *= dim * (0.5 if pressed else 1.0)
    gloss_rect = QRectF(r.left() + inset, r.top() + 1.5, r.width() - 2 * inset, gh)
    if gloss_rect.width() > 4 and gloss_rect.height() > 2:
        gloss = QLinearGradient(0, gloss_rect.top(), 0, gloss_rect.bottom())
        gloss.setColorAt(0.0, _c(255, 255, 255, top_a))
        gloss.setColorAt(1.0, _c(255, 255, 255, 4))
        p.fillPath(_rounded(gloss_rect, gloss_rect.height() / 2 if kind != "panel" else 22),
                   QBrush(gloss))

    p.setClipping(False)

    # 4) viền sáng chéo: sáng ở góc trên trái, mờ ở giữa, sáng lại ở góc dưới phải
    if kind == "bright":
        p.setPen(QPen(_c(0, 0, 0, 46), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_rounded(r.adjusted(-0.6, -0.6, 0.6, 0.6), radius + 0.6))
    rim = QLinearGradient(r.topLeft(), r.bottomRight())
    k = (1.0 + 0.35 * g) * dim
    rim.setColorAt(0.00, _c(255, 255, 255, 215 * k))
    rim.setColorAt(0.35, _c(255, 255, 255, 64 * k))
    rim.setColorAt(0.62, _c(255, 255, 255, 34 * k))
    rim.setColorAt(1.00, _c(255, 255, 255, 150 * k))
    p.setPen(QPen(QBrush(rim), 1.25))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    # 5) viền trong mảnh tạo cảm giác có độ dày
    if kind != "bright":
        inner = r.adjusted(1.7, 1.7, -1.7, -1.7)
        p.setPen(QPen(_c(255, 255, 255, 20 * dim), 1.0))
        p.drawPath(_rounded(inner, radius - 1.7))

    p.restore()


KIND_BY_NAME = {"primary": "bright", "discord": "blue", "play": "green", "stop": "red", "pause": "amber"}
KIND_ON = "blue"      # pill / chip / toggle ở trạng thái bật
KIND_OFF = "clear"    # ... và tắt


class GlassButton(QPushButton):
    """QPushButton vẽ nền kính; chữ và icon vẫn do Qt vẽ (QSS đặt nền trong suốt)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._glow = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_glow)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kind_override: str | None = None

    def set_glass_kind(self, kind: str) -> None:
        """Đổi loại kính lúc chạy (ví dụ pill bật/tắt)."""
        if kind != self._kind_override:
            self._kind_override = kind
            self.update()

    def glass_kind(self) -> str:
        if self._kind_override is not None:
            return self._kind_override
        name = self.objectName()
        return KIND_BY_NAME.get(name, "clear")

    def minimumSizeHint(self):
        # Không cho layout ép nút hẹp hơn chữ của nó (nếu không chữ như "Editor MIDI" bị cụt)
        return self.sizeHint()

    def _set_glow(self, v) -> None:
        self._glow = float(v)
        self.update()

    def _go(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._go(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(0.0)
        super().leaveEvent(e)

    def paintEvent(self, e):
        name = self.objectName()
        kind = self.glass_kind()
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radius = min(r.height() / 2, 14.0) if name == "tool" else r.height() / 2
        down = self.isDown() and self.isEnabled()

        p = QPainter(self)
        if down:  # nhấn xuống: thu nhỏ nhẹ quanh tâm
            c = r.center()
            p.translate(c)
            p.scale(0.985, 0.985)
            p.translate(-c.x(), -c.y())
        paint_glass(p, r, radius, kind, self._glow, down, self.isEnabled())
        p.end()

        super().paintEvent(e)  # chữ và icon


class GlassPanel(QFrame):
    """Khung kính lớn (kiểu DropZone của Transcriber). ``glow`` sáng lên khi hover."""

    def __init__(self, parent=None, radius: float = 26.0):
        super().__init__(parent)
        self._glow = 0.0
        self._radius = radius
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_glow)

    def set_glow(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _set_glow(self, v) -> None:
        self._glow = float(v)
        self.update()

    def enterEvent(self, e):
        self.set_glow(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.set_glow(False)
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        paint_glass(p, r, self._radius, "panel", self._glow, False, self.isEnabled())
        p.end()


class _GlowWidget:
    """Chung: hover glow 0..1 với animation mượt."""

    def __init__(self):
        self._glow = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_glow)

    def _set_glow(self, v) -> None:
        self._glow = float(v)
        self.update()

    def _go(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._go(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(0.0)
        super().leaveEvent(e)


class GlassToggle(_GlowWidget, QAbstractButton):
    """Công tắc kính: rãnh kính trong, bật = kính xanh, núm tròn sáng."""

    def __init__(self, value: bool = False, on_change=None, parent=None):
        QAbstractButton.__init__(self, parent)
        _GlowWidget.__init__(self)
        self.setCheckable(True)
        self.setChecked(bool(value))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if value else 0.0
        self._on_change = on_change
        self.toggled.connect(self._on_toggled)
        self.setFixedSize(52, 26)

    def _on_toggled(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        if self._on_change:
            self._on_change(bool(on))

    def set_value(self, value: bool) -> None:
        """Đặt trạng thái từ code (khi config đổi chỗ khác) mà không phát tín hiệu."""
        if value != self.isChecked():
            self.blockSignals(True)
            self.setChecked(value)
            self.blockSignals(False)
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(1.0 if value else 0.0)
            self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        kind = KIND_ON if self.isChecked() else "clear"
        paint_glass(p, r, r.height() / 2, kind, self._glow * 0.6, self.isDown(), self.isEnabled())
        # núm tròn
        pad = 3.0
        d = r.height() - 2 * pad
        x = r.left() + pad + self._pos * (r.width() - d - 2 * pad)
        knob = QRectF(x, r.top() + pad, d, d)
        p.setPen(QPen(_c(255, 255, 255, 200), 1.0))
        p.setBrush(_c(255, 255, 255, 244 if self.isEnabled() else 120))
        p.drawEllipse(knob)
        p.end()


class GlassSlider(_GlowWidget, QSlider):
    """Thanh trượt kính: rãnh mảnh, phần đã chạy trắng, núm tròn kính."""

    draggingChanged = Signal(bool)

    def __init__(self, parent=None, on_commit=None, on_drag=None):
        QSlider.__init__(self, Qt.Orientation.Horizontal, parent)
        _GlowWidget.__init__(self)
        self.setRange(0, 1000)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False
        self._on_commit = on_commit
        self._on_drag = on_drag
        self.sliderPressed.connect(self._press)
        self.sliderMoved.connect(self._move)
        self.sliderReleased.connect(self._release)

    @property
    def dragging(self) -> bool:
        return self._dragging

    def _press(self):
        self._dragging = True
        self.draggingChanged.emit(True)
        if self._on_drag:
            self._on_drag(self.value() / 1000)

    def _move(self, _v):
        if self._on_drag:
            self._on_drag(self.value() / 1000)

    def _release(self):
        self._dragging = False
        self.draggingChanged.emit(False)
        if self._on_commit:
            self._on_commit(self.value() / 1000)

    def set_fraction(self, v: float) -> None:
        """Đặt vị trí từ code (0..1), bỏ qua khi người dùng đang kéo."""
        if self._dragging:
            return
        self.blockSignals(True)
        self.setValue(int(round(min(max(v, 0.0), 1.0) * 1000)))
        self.blockSignals(False)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            frac = e.position().x() / max(self.width() - 1, 1)
            self.setValue(int(frac * 1000))
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cy = h / 2
        track = QRectF(6, cy - 2, w - 12, 4)
        path = _rounded(track, 2)
        p.fillPath(path, _c(255, 255, 255, 36))
        frac = (self.value() - self.minimum()) / max(self.maximum() - self.minimum(), 1)
        if frac > 0.003:
            fill = QRectF(6, cy - 2, (w - 12) * frac, 4)
            grad = QLinearGradient(fill.left(), 0, fill.right(), 0)
            grad.setColorAt(0.0, _c(255, 255, 255, 120))
            grad.setColorAt(0.5, _c(255, 255, 255, 235))
            grad.setColorAt(1.0, _c(255, 255, 255, 120))
            p.fillPath(_rounded(fill, 2), QBrush(grad))
        d = 14 + 2 * self._glow
        knob = QRectF(6 + (w - 12) * frac - d / 2, cy - d / 2, d, d)
        paint_glass(p, knob, d / 2, "clear", 0.4 + 0.6 * self._glow, self.isSliderDown(), self.isEnabled())
        p.end()


class RoundButton(_GlowWidget, QAbstractButton):
    """Nút tròn kính (mini player): vẽ glyph tam giác / vạch bằng tay."""

    def __init__(self, parent, glyph: str, size: int, on_click=None, kind: str = "clear"):
        QAbstractButton.__init__(self, parent)
        _GlowWidget.__init__(self)
        self._glyph = glyph
        self._kind = kind
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        if on_click:
            self.clicked.connect(on_click)

    def set_glyph(self, glyph: str) -> None:
        if glyph != self._glyph:
            self._glyph = glyph
            self.update()

    def set_glass_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        down = self.isDown() and self.isEnabled()
        if down:
            c = r.center()
            p.translate(c)
            p.scale(0.97, 0.97)
            p.translate(-c.x(), -c.y())
        paint_glass(p, r, r.height() / 2, self._kind, self._glow, down, self.isEnabled())
        # glyph
        p.setPen(Qt.PenStyle.NoPen)
        color = _c(20, 20, 22, 255) if self._kind == "bright" else _c(242, 242, 245, 235)
        p.setBrush(color)
        cx, cy = r.center().x(), r.center().y()
        s = r.width()
        if self._glyph == "play":
            path = QPainterPath()
            path.moveTo(cx - s * 0.14, cy - s * 0.20)
            path.lineTo(cx + s * 0.22, cy)
            path.lineTo(cx - s * 0.14, cy + s * 0.20)
            path.closeSubpath()
            p.drawPath(path)
        elif self._glyph == "pause":
            p.drawRoundedRect(QRectF(cx - s * 0.18, cy - s * 0.20, s * 0.11, s * 0.40), 2, 2)
            p.drawRoundedRect(QRectF(cx + s * 0.07, cy - s * 0.20, s * 0.11, s * 0.40), 2, 2)
        elif self._glyph == "stop":
            p.drawRoundedRect(QRectF(cx - s * 0.16, cy - s * 0.16, s * 0.32, s * 0.32), 3, 3)
        elif self._glyph == "prev":
            path = QPainterPath()
            path.moveTo(cx + s * 0.14, cy - s * 0.20)
            path.lineTo(cx - s * 0.18, cy)
            path.lineTo(cx + s * 0.14, cy + s * 0.20)
            path.closeSubpath()
            p.drawPath(path)
            p.drawRoundedRect(QRectF(cx - s * 0.30, cy - s * 0.20, s * 0.08, s * 0.40), 2, 2)
        elif self._glyph == "next":
            path = QPainterPath()
            path.moveTo(cx - s * 0.14, cy - s * 0.20)
            path.lineTo(cx + s * 0.18, cy)
            path.lineTo(cx - s * 0.14, cy + s * 0.20)
            path.closeSubpath()
            p.drawPath(path)
            p.drawRoundedRect(QRectF(cx + s * 0.22, cy - s * 0.20, s * 0.08, s * 0.40), 2, 2)
        p.end()


class Badge(_GlowWidget, QLabel):
    """Nhãn kính nhỏ dạng viên thuốc (thời gian, BPM, tốc độ)."""

    def __init__(self, parent=None, text: str = "", pill: bool = True):
        QLabel.__init__(self, parent)
        _GlowWidget.__init__(self)
        self._pill = pill
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("badge")
        self.setText(text)

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        paint_glass(p, r, r.height() / 2 if self._pill else 9.0, "clear", 0.5 + 0.5 * self._glow,
                    False, self.isEnabled())
        p.end()
        super().paintEvent(e)


class GlassLineEdit(QLineEdit):
    """Ô nhập kính; viền sáng hơn khi focus."""

    def __init__(self, parent=None, placeholder: str = ""):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)


class MiniSeek(_GlowWidget, QSlider):
    """Thanh tỉnh mảnh kiểu Lua (mini player): click / kéo để tua, fill trắng."""

    def __init__(self, parent=None, on_seek=None):
        QSlider.__init__(self, Qt.Orientation.Horizontal, parent)
        _GlowWidget.__init__(self)
        self.setRange(0, 1000)
        self.setFixedHeight(14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False
        self._on_seek = on_seek
        self.sliderPressed.connect(self._press)
        self.sliderMoved.connect(self._move)
        self.sliderReleased.connect(self._release)

    @property
    def dragging(self) -> bool:
        return self._dragging

    def _frac(self, x: float) -> float:
        return min(max(x / max(self.width(), 1), 0.0), 1.0)

    def _press(self):
        self._dragging = True
        self._emit()

    def _move(self, _v):
        if self._dragging:
            self._emit()

    def _release(self):
        self._dragging = False
        self._emit()

    def _emit(self):
        if self._on_seek:
            self._on_seek(self.value() / 1000)

    def set_fraction(self, v: float) -> None:
        if self._dragging:
            return
        self.blockSignals(True)
        self.setValue(int(round(min(max(v, 0.0), 1.0) * 1000)))
        self.blockSignals(False)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setValue(int(self._frac(e.position().x()) * 1000))
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        t = 4.0
        y0 = (h - t) / 2
        track = QRectF(0, y0, w, t)
        p.fillPath(_rounded(track, t / 2), _c(255, 255, 255, 46))
        frac = (self.value() - self.minimum()) / max(self.maximum() - self.minimum(), 1)
        if frac > 0.003:
            fill = QRectF(0, y0, max(2.0, w * frac), t)
            p.fillPath(_rounded(fill, t / 2), _c(242, 242, 245, 245))
        p.end()
