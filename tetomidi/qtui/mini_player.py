"""Mini player kính (theo TetoMIDI Lua script): thanh nhỏ luôn trên cùng.

Rows, top to bottom (like the script's mini player):
  1. app icon + song name + instrument sub-label + a "full" pill that returns to the main window
  2. elapsed time | thin seek track with a white fill | total time
  3. stop (reset) + big play / pause buttons, centred
  4. All / Left / Right (piano only)   5. the instrument's option chips

It owns no playback state: it drives the transport of whichever instrument page is active (or the
last one shown) and mirrors that page's song, position and play state.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QBrush, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import platform_tweaks
from ..engine.transport import PLAYING
from ..midi_data import format_time
from ..paths import resource_path
from .glassbtn import MiniSeek, RoundButton, paint_glass
from .player_page import MODE_TITLES, OPTIONS
from .widgets import EllipsisLabel

CHIP_LABELS = {"previewSound": "Preview", "88Keys": "88 key", "sustain": "Sustain", "velocity": "Velocity",
               "noteLengths": "Lengths", "loop": "Loop"}
HAND_CHOICES = (("all", "All"), ("left", "Left"), ("right", "Right"))
WIDTH = 470
CORNER = 16.0


class MiniPlayer(QWidget):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle("tetoMIDI mini")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(self.app.cfg.get("app.topmost", False)))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag = None
        self._mode: str | None = None
        self._build()
        page = self.app.player_page()
        if page is not None:
            self._rebuild_mode(page.mode)
        self.setFixedWidth(WIDTH)
        self.adjustSize()

    # ------------------------------------------------------------ glass paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, CORNER, CORNER)
        p.fillPath(path, QColor(10, 10, 13, 238))
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(255, 255, 255, 40))
        g.setColorAt(0.10, QColor(255, 255, 255, 8))
        g.setColorAt(1.0, QColor(0, 0, 0, 140))
        p.fillPath(path, QBrush(g))
        w = float(self.width())
        sheen = QRadialGradient(QPointF(w * 0.18, 0.0), w * 0.85)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 36))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sheen))
        rim = QLinearGradient(0, 0, w, float(self.height()))
        rim.setColorAt(0.00, QColor(255, 255, 255, 140))
        rim.setColorAt(0.35, QColor(255, 255, 255, 46))
        rim.setColorAt(0.70, QColor(255, 255, 255, 26))
        rim.setColorAt(1.00, QColor(255, 255, 255, 96))
        p.setPen(QPen(QBrush(rim), 1.2))
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------ build
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(4)

        # row 1: icon + song + sub | full
        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel()
        try:
            img = QPixmap(resource_path("assets/icons/app.png")).scaled(
                22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(img)
        except Exception:
            icon_lbl.setText("♪")
        top.addWidget(icon_lbl)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.song = EllipsisLabel("No MIDI file loaded – open one in the main window", 13)
        self.song.setObjectName("file")
        col.addWidget(self.song)
        self.sub = QLabel("piano player")
        self.sub.setObjectName("sub")
        col.addWidget(self.sub)
        top.addLayout(col, 1)
        full = _MiniPill("full", self.app.hide_mini, tip="Back to the main window")
        top.addWidget(full)
        root.addLayout(top)

        # row 2: time | seek | total
        mid = QHBoxLayout()
        mid.setSpacing(8)
        self.time = QLabel("0:00")
        self.time.setObjectName("sub")
        self.total = QLabel("0:00")
        self.total.setObjectName("sub")
        self.seek = MiniSeek(on_seek=self._on_seek)
        mid.addWidget(self.time)
        mid.addWidget(self.seek, 1)
        mid.addWidget(self.total)
        root.addLayout(mid)

        # row 3: stop | play (centred)
        row = QHBoxLayout()
        row.addStretch(1)
        self.stop_btn = RoundButton(self, "stop", 42, self._stop)
        self.stop_btn.setToolTip("Stop")
        self.play_btn = RoundButton(self, "play", 54, self._play)
        self.play_btn.setToolTip("Play / pause")
        row.addWidget(self.stop_btn)
        row.addSpacing(10)
        row.addWidget(self.play_btn)
        row.addStretch(1)
        root.addLayout(row)

        # row 4: hand (piano only)
        self.hand_row = QWidget()
        hl = QHBoxLayout(self.hand_row)
        hl.setContentsMargins(0, 2, 0, 0)
        hl.setSpacing(4)
        self.hand_btns: dict[str, _MiniPill] = {}
        for value, text in HAND_CHOICES:
            pill = _MiniPill(text, lambda _b=False, v=value: self._set_hand(v),
                             tip="Play every note" if value == "all" else
                                 ("Left hand only: notes below C4" if value == "left" else "Right hand only: notes from C4 up"))
            self.hand_btns[value] = pill
            hl.addWidget(pill, 1)
        root.addWidget(self.hand_row)

        # row 5: option chips
        self.chip_row = QWidget()
        self.chip_lay = QHBoxLayout(self.chip_row)
        self.chip_lay.setContentsMargins(0, 2, 0, 0)
        self.chip_lay.setSpacing(4)
        self.chips: dict[str, _MiniPill] = {}
        root.addWidget(self.chip_row)

        self._bind_drag(self)

    def _bind_drag(self, widget):
        """Kéo cửa sổ bằng mọi vùng trống (label/ Khung); nút và thanh tua giữ nguyên click."""
        from PySide6.QtWidgets import QLabel as _L, QWidget as _W
        if isinstance(widget, (_MiniPill, RoundButton, MiniSeek)):
            return
        if isinstance(widget, (_W, _L)):
            widget.mousePressEvent = self._drag_press    # type: ignore[method-assign]
            widget.mouseMoveEvent = self._drag_move      # type: ignore[method-assign]
            widget.mouseReleaseEvent = self._drag_release  # type: ignore[method-assign]
        for child in widget.findChildren(QWidget):
            self._bind_drag(child)

    def _drag_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        e.accept()

    def _drag_move(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        e.accept()

    def _drag_release(self, e):
        self._drag = None
        e.accept()

    # ------------------------------------------------------------ rows 4/5
    def _rebuild_mode(self, mode: str):
        self._mode = mode
        while self.chip_lay.count():
            item = self.chip_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.chips.clear()
        for label, key in OPTIONS.get(mode, []):
            chip = _MiniPill(CHIP_LABELS.get(key, label), lambda _b=False, k=key: self._toggle_chip(k))
            self.chips[key] = chip
            self.chip_lay.addWidget(chip, 1)
        self.hand_row.setVisible(mode == "piano")
        self.adjustSize()
        self.setFixedWidth(WIDTH)

    # ------------------------------------------------------------ actions
    @property
    def page(self):
        return self.app.player_page()

    def place_near_root(self):
        r = self.app.window
        self.move(max(r.x() + 60, 0), max(r.y() + 60, 0))

    def _play(self):
        page = self.page
        if page is None:
            return
        if page.song is None:   # nothing loaded: start the MIDI player's list on this instrument
            midi = self.app.midi_window()
            if midi.playlist.items:
                midi.use_mode(page.mode)
                midi.start()
                return
        page.on_play()

    def _stop(self):
        if self.page:
            self.page.on_stop()

    def _set_hand(self, value: str):
        p = self.page
        if p:
            p.cfg.set("piano.hand", value)

    def _toggle_chip(self, key: str):
        p = self.page
        if p:
            p._set_option(key, not bool(p.cfg.get(f"{p.mode}.{key}", False)))

    def _on_seek(self, v: float):
        p = self.page
        if p and p.song:
            self.time.setText(format_time(v * p.song.length)[3:])
            p.transport.seek(v * p.song.length)

    # ------------------------------------------------------------ tick
    def update_view(self):
        p = self.page
        if p is None:
            return
        if p.mode != self._mode:
            self._rebuild_mode(p.mode)
        self.sub.setText(MODE_TITLES.get(p.mode, p.mode))
        name = p.song.name if p.song else "No MIDI file loaded – open one in the main window"
        if self.song._full != name:
            self.song.set_text(name)
        t = p.transport
        length = t.length if p.song else 0.0
        pos = t.position()
        if not self.seek.dragging:
            self.seek.set_fraction(pos / length if length else 0.0)
            self.time.setText(format_time(pos)[3:])
            self.total.setText(format_time(length)[3:] if length else "0:00")
        want = "pause" if t.state == PLAYING else "play"
        if self.play_btn._glyph != want:
            self.play_btn.set_glyph(want)
        if p.mode == "piano":
            hand = p.cfg.get("piano.hand", "all")
            for value, pill in self.hand_btns.items():
                pill.set_kind("blue" if value == hand else "clear")
        for key, chip in self.chips.items():
            on = bool(p.cfg.get(f"{p.mode}.{key}", False))
            chip.set_kind("blue" if on else "clear")


class _MiniPill(QLabel):
    """Viên thuốc kính nhỏ (chữ trắng, bật = kính xanh) cho mini player."""

    def __init__(self, text: str, on_click=None, tip: str = ""):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(64, 24)
        self._kind = "clear"
        self._glow = 0.0
        self._pressed = False
        if on_click:
            self._on_click = on_click
        if tip:
            self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_kind(self, kind: str):
        if kind != self._kind:
            self._kind = kind
            self.update()

    def set_glow(self, on: bool):
        self._glow = 1.0 if on else 0.0
        self.update()

    def enterEvent(self, e):
        self.set_glow(True)

    def leaveEvent(self, e):
        self.set_glow(False)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            cb = getattr(self, "_on_click", None)
            if cb:
                cb()
            e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.2, 1.2, -1.2, -1.2)
        paint_glass(p, r, r.height() / 2, self._kind, 0.55 + 0.45 * self._glow, self._pressed, True)
        p.end()
        super().paintEvent(_)
