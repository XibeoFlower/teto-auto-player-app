"""3D falling-note piano roll — port sang QPainter (từ bản Tkinter RollView).

The notes lie flat on a floor that recedes in perspective and slide towards the keyboard.
Pure view: it draws whatever ``RollData`` it is given at the playback position it is asked to
render, so the animation is driven by the transport clock and never runs on its own.
"""
from __future__ import annotations

import logging
import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..config import Config
from ..mappings import DRUM_LANE_LABELS, GUITAR_STRING_LABELS, is_black
from ..rollmodel import RollData

log = logging.getLogger(__name__)

MAX_NOTES_DRAWN = 450
VEL_SHADES = 8
DEPTH = 1.3          # how far the back of the floor is, in "keyboard distances"
NOTE_THICK = 7       # height of the front face of a note
FADE_STEPS = 6

ROLL_BG = "#07080b"
TEXT = "#f2f2f5"
TEXT_SOFT = "#e2e2e6"
TEXT_FAINT = "#6b6b74"
KEY_WHITE = "#e6e6e6"
KEY_WHITE_EDGE = "#8f8f8f"
KEY_BLACK = "#2b2b2b"
KEY_LABEL_WHITE = "#2a2a2a"
KEY_LABEL_BLACK = "#f0f0f0"
KEY_LABEL_CTRL_WHITE = "#1f5f99"
KEY_LABEL_CTRL_BLACK = "#8cc3ea"
PAD = "#15181e"

NOTE_PALETTES = {
    "blue": ("#5b93c7", "#aad6f6", "#74bcf0"),
    "cyan": ("#3cb9cc", "#a2f2fb", "#54d8ec"),
    "green": ("#5ec281", "#b6f2cc", "#74d092"),
    "pink": ("#d077a7", "#f9c0dd", "#e38abc"),
    "amber": ("#d5a851", "#ffe5ad", "#ecbc63"),
}

FALLBACK = "blue"


def _mix(c1: str, c2: str, t: float) -> QColor:
    a, b = QColor(c1), QColor(c2)
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


class RollView(QWidget):
    def __init__(self, mode: str, cfg: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode, self.cfg = mode, cfg
        self.data: RollData = RollData(mode)
        self.pos = 0.0
        self._caption = ""
        self._lit: set[int] = set()
        self.setMinimumHeight(140)
        self.setMouseTracking(False)

    # ------------------------------------------------------------- colors
    def palette(self) -> tuple[str, str, str]:
        return NOTE_PALETTES.get(self.cfg.get("roll.noteColor", FALLBACK), NOTE_PALETTES[FALLBACK])

    def _lane_palette(self, lane: int):
        """(body, edge, lit) cua mot lane. rainbow: mau theo lop not (12 hue, Synthesia style)."""
        if self.cfg.get("roll.noteColor", FALLBACK) != "rainbow":
            return self.palette()
        hue = int((lane % 12) / 12.0 * 359)
        if lane in self._key_black:   # not den: dam hon de phan biet
            return (QColor.fromHsv(hue, 200, 220), QColor.fromHsv(hue, 120, 245),
                    QColor.fromHsv(hue, 80, 255))
        return (QColor.fromHsv(hue, 160, 255), QColor.fromHsv(hue, 85, 255),
                QColor.fromHsv(hue, 45, 255))

    def set_data(self, data: RollData):
        self.data = data
        self._lit = set()
        self.update()

    def refresh_style(self):
        self._lit = set()
        self.update()

    def set_caption(self, text: str):
        if text != self._caption:
            self._caption = text
            self.update()

    # ----------------------------------------------------------- geometry
    def _layout(self) -> None:
        W, H = self.width(), self.height()
        self.W, self.H = W, H
        kb = min(max(int(H * 0.17), 40), 66)
        self.kb_h = kb
        self.hit = H - kb
        self.cx = W / 2
        self._3d = bool(self.cfg.get("roll.mode3d", False))
        self.horizon = -self.hit / DEPTH if self._3d else 0.0
        self.look = max(0.5, float(self.cfg.get("roll.fallSeconds", 3.0)))
        pal = self.palette()
        self._lane_rect: dict[int, tuple[float, float]] = {}
        self._key_rect: dict[int, tuple[float, float, float, float]] = {}
        self._key_base: dict[int, str] = {}
        self._key_black: set[int] = set()
        if self.mode == "drums":
            self._layout_drums()
        elif self.mode == "guitar":
            self._layout_guitar()
        else:
            self._layout_piano()
        self._lane_w = 20.0
        if self._lane_rect:
            first = next(iter(self._lane_rect.values()))
            self._lane_w = first[1] - first[0]

    def _layout_piano(self):
        W, H, hit = self.W, self.H, self.hit
        lo, hi = self.data.key_range
        whites = [p for p in range(lo, hi + 1) if not is_black(p)]
        if not whites:
            return
        ww = W / len(whites)
        wx = {p: i * ww for i, p in enumerate(whites)}
        for p in whites:
            self._lane_rect[p] = (wx[p] + 1, wx[p] + ww - 1)
            self._key_rect[p] = (wx[p], hit, ww, self.kb_h)
            self._key_base[p] = KEY_WHITE
        bw, bh = ww * 0.6, self.kb_h * 0.62
        for p in range(lo, hi + 1):
            if is_black(p) and (p - 1) in wx:
                cx = wx[p - 1] + ww
                self._lane_rect[p] = (cx - bw / 2, cx + bw / 2)
                self._key_rect[p] = (cx - bw / 2, hit, bw, bh)
                self._key_base[p] = KEY_BLACK
                self._key_black.add(p)

    def _lane_columns(self, count: int, gap: float):
        total_gap = gap * (count + 1)
        w = (self.W - total_gap) / count
        return [(gap + i * (w + gap), gap + i * (w + gap) + w) for i in range(count)]

    def _layout_drums(self):
        pads = self._lane_columns(len(DRUM_LANE_LABELS), 5)
        for i, (x0, x1) in enumerate(pads):
            self._lane_rect[i] = (x0 + 1, x1 - 1)
            self._key_rect[i] = (x0, self.hit, x1 - x0, self.kb_h)
            self._key_base[i] = PAD

    def _layout_guitar(self):
        strings = self._lane_columns(len(GUITAR_STRING_LABELS), 10)
        for i, (x0, x1) in enumerate(strings):
            self._lane_rect[i] = (x0 + 1, x1 - 1)
            self._key_rect[i] = (x0, self.hit, x1 - x0, self.kb_h)
            self._key_base[i] = PAD

    # ----------------------------------------------------------- helpers
    def _scale(self, tau: float) -> float:
        if not self._3d:                      # 2D: roi thang, khong phoi canh
            return max(0.0, 1.0 - tau / self.look)
        return 1.0 / (1.0 + DEPTH * tau / self.look)

    def _y(self, tau: float) -> float:
        return self.horizon + (self.hit - self.horizon) * self._scale(tau)

    def _fade(self, color, q: int) -> QColor:
        return _mix(color, ROLL_BG, 0.40 * q / FADE_STEPS)   # nhe hon: note xa van sang

    def _shade(self, vel_idx: int, lane: int = 0) -> QColor:
        body, _edge, _lit = self._lane_palette(lane)
        return _mix(ROLL_BG, body, 0.50 + 0.50 * (vel_idx + 1) / VEL_SHADES)

    # ------------------------------------------------------------- paint
    def paintEvent(self, _e):
        self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H, hit, cx = self.W, self.H, self.hit, self.cx
        p.fillRect(0, 0, W, H, QColor(ROLL_BG))
        self._paint_background(p)

        # --- sàn 3D: đường mép + đường thời gian
        pen = QPen(QColor("#161b24"))
        p.setPen(pen)
        look = self.look
        for i in range(13):
            x = W * i / 12
            if self._3d:
                p.drawLine(QPointF(cx + (x - cx) / (1 + DEPTH), self._y(look)), QPointF(x, hit))
            else:
                p.drawLine(QPointF(x, 0), QPointF(x, hit))
        pos = self.pos
        first = int(pos) + 1
        p.setPen(QPen(QColor("#1a2029")))
        for k in range(int(look) + 3):
            tau = first + k - pos
            if tau > look:
                continue
            y = self._y(tau)
            half = W / 2 * self._scale(tau) if self._3d else W / 2
            p.drawLine(QPointF(cx - half, y), QPointF(cx + half, y))

        # --- hướng nhịp octave (trước mỗi C)
        if self.mode == "piano":
            p.setPen(QPen(QColor("#202733")))
            lo, hi = self.data.key_range
            whites = [q for q in range(lo, hi + 1) if not is_black(q)]
            if whites:
                ww = W / len(whites)
                for j, q in enumerate(whites):
                    if q % 12 == 0 and q != lo:
                        x = j * ww
                        if self._3d:
                            p.drawLine(QPointF(cx + (x - cx) / (1 + DEPTH), self._y(look)), QPointF(x, hit))
                        else:
                            p.drawLine(QPointF(x, 0), QPointF(x, hit))

        # --- keyboard / pads / strings
        self._paint_keys(p)

        # --- notes
        self._paint_notes(p)

        # --- caption + empty text
        if self._caption:
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QPen(QColor(TEXT_SOFT)))
            text = self._caption
            while text and p.fontMetrics().horizontalAdvance(text) > W - 28 and len(text) > 1:
                text = text[:-1]
            if text != self._caption:
                text = text.rstrip() + "…"
            p.drawText(QPointF(14, 22), text)
        if len(self.data) == 0:
            f = QFont(self.font())
            f.setPointSizeF(10.5)
            p.setFont(f)
            p.setPen(QPen(QColor(TEXT_FAINT)))
            p.drawText(QRectF(0, 0, W, hit), Qt.AlignmentFlag.AlignCenter, "Select a MIDI file to start")
        p.end()

    def _paint_background(self, p: QPainter):
        path = self.cfg.get("roll.background", "")
        if not path or not os.path.isfile(path):
            return
        try:
            img = QImage(path)
        except Exception:
            return
        if img.isNull():
            return
        dim = min(max(float(self.cfg.get("roll.backgroundDim", 50)), 0), 100) / 100
        scaled = img.scaled(int(self.W), int(self.H), Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        p.setOpacity(1.0 - dim)
        p.drawImage(0, 0, scaled)
        p.setOpacity(1.0)

    def _paint_keys(self, p: QPainter):
        for lane, (x, y, w, h) in self._key_rect.items():
            base = QColor(self._lane_palette(lane)[2] if lane in self._lit else self._key_base[lane])
            p.setPen(QPen(QColor("#000000") if lane in self._key_black or self.mode != "piano" else QColor(KEY_WHITE_EDGE)))
            p.setBrush(base)
            p.drawRect(QRectF(x, y, w, h))
        if self.mode == "piano":
            # viền phím trắng
            p.setPen(QPen(QColor(KEY_WHITE_EDGE)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for lane, (x, y, w, h) in self._key_rect.items():
                if lane not in self._key_black:
                    p.drawRect(QRectF(x, y, w, h))
        elif self.mode == "guitar":
            strings = list(self._key_rect.values())
            for i, (x, y, w, h) in enumerate(strings):
                line = QColor("#d8d8de") if i == len(strings) - 1 else QColor("#9a9aa2")
                p.setPen(QPen(line))
                p.drawLine(QPointF(x + 2, y + 7), QPointF(x + w - 2, y + 7))
        # nhãn
        f = QFont(self.font())
        labels = self._label_specs()
        for text, cx_, cy_, size, color in labels:
            f.setPointSizeF(max(6.5, min(10.5, size)))
            p.setFont(f)
            p.setPen(QPen(QColor(color)))
            p.drawText(QPointF(cx_ - p.fontMetrics().horizontalAdvance(text) / 2, cy_), text)
        # glow các phím đang bật
        if self.cfg.get("roll.glow", True):
            for lane in self._lit:
                rect = self._lane_rect.get(lane)
                if rect is None:
                    continue
                x0, x1 = rect
                gw, gh = max(44.0, (x1 - x0) * 2.6), 54.0
                lit_qc = QColor(self._lane_palette(lane)[2])
                p.setPen(Qt.PenStyle.NoPen)
                p.save()
                p.translate((x0 + x1) / 2, self.hit)
                p.scale(1.0, gh / gw)
                grad2 = QRadialGradient(QPointF(0, 0), gw / 2)
                grad2.setColorAt(0.0, QColor(lit_qc.red(), lit_qc.green(), lit_qc.blue(), 120))
                grad2.setColorAt(1.0, QColor(lit_qc.red(), lit_qc.green(), lit_qc.blue(), 0))
                p.setBrush(grad2)
                p.drawEllipse(QPointF(0, 0), gw / 2, gw / 2)
                p.restore()

    def _label_specs(self):
        """(text, cx, cy, size, color) cho nhãn phím / pad / dây."""
        out = []
        if self.mode == "piano":
            if not self.cfg.get("roll.keyLabels", True):
                return out
            pm = self.cfg.get("piano.pianoMap", {}) or {}
            letters = pm.get("61keyMap", {})
            extra = {**pm.get("88keyMap", {}).get("lowNotes", {}), **pm.get("88keyMap", {}).get("highNotes", {})}
            lo, hi = self.data.key_range
            rect = self._key_rect
            lane = self._lane_rect
            if not lane:
                return out
            first = next(iter(lane.values()))
            ww = first[1] - first[0]
            size = max(6.0, min(11.0, ww * 0.66 * 0.62))
            for p_ in range(lo, hi + 1):
                key = letters.get(str(p_))
                ctrl = key is None
                if ctrl:
                    key = extra.get(str(p_))
                if not key:
                    continue
                kr = rect.get(p_)
                if kr is None:
                    continue
                x, y, w, h = kr
                if p_ in self._key_black:
                    out.append((key, x + w / 2, y + h - size * 0.5, size, KEY_LABEL_CTRL_BLACK if ctrl else KEY_LABEL_BLACK))
                else:
                    out.append((key, x + w / 2, y + h - size * 0.35, size, KEY_LABEL_CTRL_WHITE if ctrl else KEY_LABEL_WHITE))
        elif self.mode == "drums":
            pads = self._lane_columns(len(DRUM_LANE_LABELS), 5)
            size = max(6.0, min(8.5, (self.W / len(pads)) * 0.16))
            for i, (x0, x1) in enumerate(pads):
                label = DRUM_LANE_LABELS[i]
                out.append((label, (x0 + x1) / 2, self.H - size * 0.55, size, TEXT_FAINT))
        else:
            strings = self._lane_columns(len(GUITAR_STRING_LABELS), 10)
            size = max(7.0, min(11.0, (self.W / len(strings)) * 0.2))
            for i, (x0, x1) in enumerate(strings):
                out.append((GUITAR_STRING_LABELS[i], (x0 + x1) / 2, self.H - size * 0.55, size, TEXT_FAINT))
        return out

    def _paint_notes(self, p: QPainter):
        data = self.data
        if not len(data) or not self._lane_rect:
            return
        look = self.look
        pos = self.pos
        lo, hi = data.window(pos, look)
        use_vel = bool(self.cfg.get(f"{self.mode}.velocity", False))
        thick = NOTE_THICK
        cx = self.cx
        lit: set[int] = set()
        used = 0
        starts, ends, lanes, vels = data.starts, data.ends, data.lanes, data.vels
        scale_cache: dict[float, float] = {}
        for i in range(lo, hi):
            e = ends[i]
            if e <= pos:
                continue
            rect = self._lane_rect.get(lanes[i])
            if rect is None:
                continue
            s = starts[i]
            tau_n = max(s - pos, 0.0)
            tau_f = min(e - pos, look)
            if tau_n >= look:
                continue
            sn = scale_cache.get(tau_n)
            if sn is None:
                sn = scale_cache[tau_n] = self._scale(tau_n)
            sf = scale_cache.get(tau_f)
            if sf is None:
                sf = scale_cache[tau_f] = self._scale(tau_f)
            yn, yf = self._y(tau_n), self._y(tau_f)
            if yn - yf < 3:
                yf = yn - 3
            xa, xb = rect
            if self._3d:
                pts = QPolygonF([QPointF(cx + (xa - cx) * sn, yn),
                                 QPointF(cx + (xb - cx) * sn, yn),
                                 QPointF(cx + (xb - cx) * sf, yf),
                                 QPointF(cx + (xa - cx) * sf, yf)])
            else:   # 2D: nota thuoc chu nhat, roi thang
                pts = QPolygonF([QPointF(xa, yn), QPointF(xb, yn),
                                 QPointF(xb, yf), QPointF(xa, yf)])
            active = s <= pos
            if active:
                lit.add(lanes[i])
            body, edge, lit_col = self._lane_palette(lanes[i])
            base = lit_col if active else (self._shade(min(vels[i] * VEL_SHADES // 128, VEL_SHADES - 1), lanes[i])
                                           if use_vel else body)
            q = 0 if active else min(FADE_STEPS, int((1 - sn) * FADE_STEPS / (1 - self._scale(look)) + 0.5))
            fill = self._fade(base, q) if q else QColor(base)
            p.setPen(QPen(QColor(edge)))
            p.setBrush(fill)
            p.drawPolygon(pts)
            if not active:   # mặt trước (độ dày)
                t = min(max(1.0, thick * (sn if self._3d else 1.0)), max(self.hit - yn, 1.0))
                front = QPolygonF([pts[0], pts[1],
                                   QPointF(pts[2].x(), yn + t), QPointF(pts[0].x(), yn + t)])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_mix(base, "#000000", 0.5))
                p.drawPolygon(front)
                p.setPen(QPen(QColor(edge)))
            used += 1
            if used >= MAX_NOTES_DRAWN:
                break
        if lit != self._lit:
            self._lit = lit
