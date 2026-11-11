"""Icon vẽ bằng code (không cần file ảnh ngoài) + icon PNG của app."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ..paths import resource_path


def _pm(size: int) -> tuple[QPixmap, QPainter, float]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pm, p, float(size)


def discord_icon(size: int = 18, color: QColor | None = None) -> QIcon:
    """Biểu tượng chat kiểu Discord (bong bóng có hai mắt) — hình vẽ đơn giản."""
    color = color or QColor("#ffffff")
    pm, p, s = _pm(size)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)

    body = QPainterPath()
    body.addRoundedRect(QRectF(0.12 * s, 0.20 * s, 0.76 * s, 0.56 * s), 0.28 * s, 0.28 * s)
    tail = QPainterPath()
    tail.moveTo(0.26 * s, 0.66 * s)
    tail.lineTo(0.22 * s, 0.90 * s)
    tail.lineTo(0.46 * s, 0.72 * s)
    tail.closeSubpath()
    p.drawPath(body.united(tail))

    # khoét hai mắt cho trong suốt
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.drawEllipse(QRectF(0.31 * s, 0.37 * s, 0.13 * s, 0.19 * s))
    p.drawEllipse(QRectF(0.56 * s, 0.37 * s, 0.13 * s, 0.19 * s))
    p.end()
    return QIcon(pm)


def sidebar_icon(size: int = 18, color: QColor | None = None) -> QIcon:
    """Nút mở danh mục: khung bo tròn với một vạch dọc ở bên trái."""
    color = color or QColor("#ffffff")
    pm, p, s = _pm(size)
    pen = QPen(color)
    pen.setWidthF(max(1.5, s * 0.09))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.14 * s, 0.20 * s, 0.72 * s, 0.60 * s), 0.10 * s, 0.10 * s)
    p.drawLine(QPointF(0.36 * s, 0.20 * s), QPointF(0.36 * s, 0.80 * s))
    p.end()
    return QIcon(pm)


def mini_icon(size: int = 18, color: QColor | None = None) -> QIcon:
    """Nút mini player: hai khung chữ nhật (một to một nhỏ) như biểu tượngPicture-in-picture."""
    color = color or QColor("#ffffff")
    pm, p, s = _pm(size)
    pen = QPen(color)
    pen.setWidthF(max(1.5, s * 0.085))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.12 * s, 0.18 * s, 0.76 * s, 0.64 * s), 0.12 * s, 0.12 * s)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(0.42 * s, 0.46 * s, 0.34 * s, 0.26 * s), 0.06 * s, 0.06 * s)
    p.end()
    return QIcon(pm)


def list_icon(size: int = 18, color: QColor | None = None) -> QIcon:
    """Nút danh sách phát: ba dòng, mỗi dòng một chấm."""
    color = color or QColor("#ffffff")
    pm, p, s = _pm(size)
    pen = QPen(color)
    pen.setWidthF(max(1.5, s * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i, fy in enumerate((0.28, 0.50, 0.72)):
        p.drawPoint(QPointF(0.18 * s, fy * s))
        p.drawLine(QPointF(0.34 * s, fy * s), QPointF(0.82 * s, fy * s))
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    """Logo tetoMIDI (assets/icons/app.png)."""
    try:
        return QIcon(str(resource_path("assets/icons/app.png")))
    except Exception:
        return QIcon()


def page_icon(name: str) -> QIcon | None:
    """Icon PNG cho các mục sidebar: piano / drum / guitar / hub / gear / discord."""
    mapping = {"piano": "piano", "drums": "drum", "guitar": "guitar", "hub": "hub",
               "settings": "gear", "discord": "discord"}
    file = mapping.get(name)
    if not file:
        return None
    path = resource_path(f"assets/icons/{file}.png")
    if not Path(path).is_file():
        return None
    return QIcon(str(path))
