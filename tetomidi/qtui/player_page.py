"""Trang Piano / Drums / Guitar player — giao diện kính (TetoTranscriber style)."""
from __future__ import annotations

import logging
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from ..engine.transport import PAUSED, PLAYING, Transport
from ..midi_data import MidiLoadError, Song, format_time, load_song
from ..rollmodel import build_roll
from .glassbtn import Badge, GlassButton, GlassSlider, GlassToggle
from .roll import RollView
from .widgets import (EllipsisLabel, HotkeyChip, PageTitle, ScrollArea, fit_text, make_h, make_v,
                      pick_midi_file)

log = logging.getLogger(__name__)

# (label, config key) per mode, in display order.
OPTIONS = {
    "piano": [("Preview sound", "previewSound"), ("88 key", "88Keys"), ("Sustain", "sustain"),
              ("Velocity", "velocity"), ("Note lengths", "noteLengths"), ("3D roll", "roll3D"),
              ("Loop", "loop")],
    "drums": [("Note lengths", "noteLengths"), ("3D roll", "roll3D"), ("Loop", "loop")],
    "guitar": [("Note lengths", "noteLengths"), ("3D roll", "roll3D"), ("Loop", "loop")],
}
OPTION_TIPS = {
    "previewSound": "On: Play sounds the MIDI as piano and presses no keys (no macro). Off: normal macro.",
    "88Keys": "Use the full 88-key range (extra notes use CTRL). Off: 61 keys.",
    "sustain": "Hold SPACE while the MIDI sustain pedal is down.",
    "velocity": "Send note velocity (ALT + key) and shade notes by velocity.",
    "loop": "Start again when the song ends.",
    "noteLengths": "On: notes keep their real length. Off: every note is short and the same length.",
    "roll3D": "On: 3D piano roll with the perspective floor. Off: flat 2D roll (default).",
}
HAND_CHOICES = (("all", "All"), ("left", "Left"), ("right", "Right"))
HEADINGS = {m: "select MIDI file" for m in ("piano", "drums", "guitar")}
CAPTIONS = {"piano": "Piano roll", "drums": "Drum pads", "guitar": "Guitar strings"}
MODE_TITLES = {"piano": "piano player", "drums": "drum player", "guitar": "guitar player"}
HOTKEY_ROWS = (("play", "play"), ("pause", "pause"), ("stop", "stop"),
               ("speedup", "faster"), ("slowdown", "slower"))
ROLL_KEYS = ("88Keys", "pitchOffset", "transposeOffset", "skipPercussion", "velocity", "noteLengths", "pianoMap")
ERR, WARN, MUTED, SOFT, GOOD = "#ff7b72", "#e0a13a", "#9c9ca4", "#e2e2e6", "#56bb6b"


class BpmBadge(Badge):
    """Badge tempo: lăn chuột để đổi tốc độ."""

    def __init__(self, on_step, parent=None):
        super().__init__(parent, "120")
        self.on_step = on_step
        self.setToolTip("Tempo in BPM (includes playback speed). Scroll to change speed.")

    def wheelEvent(self, e):
        self.on_step(5 if e.angleDelta().y() > 0 else -5)


class PlayerPage(QWidget):
    def __init__(self, app, mode: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.app, self.mode, self.cfg = app, mode, app.cfg
        self.transport: Transport = app.transports[mode]
        self.song: Song | None = None
        self._toggles: dict[str, GlassToggle] = {}
        self._hand_btns: dict[str, GlassButton] = {}
        self._hot_chips: dict[str, HotkeyChip] = {}
        self._build()
        self.cfg.on_change(self._on_cfg_change)
        saved = self.cfg.get(f"{mode}.currentFile", "")
        if saved and os.path.isfile(saved):
            self.load_path(saved, remember=False, quiet=True)
        self._apply_flags()
        self._refresh_status()

    # ------------------------------------------------------------ build
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 14, 24, 16)
        root.setSpacing(8)

        # --- header: title + Open ... Save MIDI / Mini player / List
        head = QHBoxLayout()
        head.setSpacing(10)
        self.heading = PageTitle(HEADINGS[self.mode])
        head.addWidget(self.heading)
        self.select_btn = GlassButton("Open")
        self.select_btn.setObjectName("primary")
        self.select_btn.setToolTip("Open a MIDI file")
        self.select_btn.clicked.connect(self.select_file)
        head.addWidget(self.select_btn)
        self.status = EllipsisLabel("", 12, MUTED)
        self.status.setObjectName("file")
        head.addWidget(self.status, 1)
        self.save_btn = GlassButton("Save MIDI")
        self.save_btn.setObjectName("ghost")
        self.save_btn.clicked.connect(self.save_midi)
        head.addWidget(self.save_btn)
        self.mini_btn = GlassButton("Mini player")
        self.mini_btn.setObjectName("ghost")
        self.mini_btn.setToolTip("Show the small always-on-top mini player")
        self.mini_btn.clicked.connect(self.app.show_mini)
        head.addWidget(self.mini_btn)
        self.list_btn = GlassButton("List")
        self.list_btn.setObjectName("ghost")
        self.list_btn.clicked.connect(self.app.show_midi_player)
        head.addWidget(self.list_btn)
        root.addLayout(head)

        # --- body: options column | roll
        body = QHBoxLayout()
        body.setSpacing(18)
        opts = QVBoxLayout()
        opts.setSpacing(12)
        for label, key in OPTIONS[self.mode]:
            row = QHBoxLayout()
            row.setSpacing(10)
            lab = QLabel(label)
            lab.setObjectName("row-label")
            tg = GlassToggle(value=bool(self.cfg.get(f"{self.mode}.{key}", False)),
                             on_change=lambda v, k=key: self._set_option(k, v))
            tg.setToolTip(OPTION_TIPS.get(key, ""))
            self._toggles[key] = tg
            row.addWidget(lab)
            row.addStretch()
            row.addWidget(tg)
            opts.addLayout(row)
        opts.addStretch()
        body.addLayout(opts, 0)

        self.roll = RollView(self.mode, self.cfg)
        self.roll.setMinimumSize(320, 240)
        body.addWidget(self.roll, 1)
        root.addLayout(body, 1)

        # --- hotkeys + hand + preview pill
        hot = QHBoxLayout()
        hot.setSpacing(6)
        hot.addStretch()
        for name, text in HOTKEY_ROWS:
            lab = QLabel(text)
            lab.setObjectName("chip-label")
            hot.addWidget(lab)
            chip = HotkeyChip(name, self.cfg.get(f"hotkeys.{name}", ""), self.app.rebind_hotkey)
            chip.setToolTip("Click, then press the key you want")
            self._hot_chips[name] = chip
            hot.addWidget(chip)
        hot.addStretch()
        root.addLayout(hot)

        if self.mode == "piano":
            hand = QHBoxLayout()
            hand.setSpacing(6)
            hand.addStretch()
            lab = QLabel("hand")
            lab.setObjectName("chip-label")
            hand.addWidget(lab)
            for value, text in HAND_CHOICES:
                pill = GlassButton(text)
                pill.setObjectName("tool")
                pill.setFixedHeight(26)
                pill.setToolTip("Play every note" if value == "all" else
                                ("Left hand only: notes below C4" if value == "left" else "Right hand only: notes from C4 up"))
                pill.clicked.connect(lambda _=False, v=value: self._set_hand(v))
                self._hand_btns[value] = pill
                hand.addWidget(pill)
            self.preview_btn = GlassButton("Preview sound: off")
            self.preview_btn.setObjectName("tool")
            self.preview_btn.setFixedHeight(26)
            self.preview_btn.setToolTip(OPTION_TIPS["previewSound"])
            self.preview_btn.clicked.connect(
                lambda: self._set_option("previewSound", not bool(self.cfg.get("piano.previewSound", False))))
            hand.addWidget(self.preview_btn)
            hand.addStretch()
            root.addLayout(hand)

        # --- playbar: PLAY STOP [slider] BPM reset
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.play_btn = GlassButton("PLAY")
        self.play_btn.setObjectName("play")
        self.play_btn.setFixedSize(96, 40)
        self.play_btn.clicked.connect(self.on_play)
        bar.addWidget(self.play_btn)
        self.stop_btn = GlassButton("STOP")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setFixedSize(96, 40)
        self.stop_btn.clicked.connect(self.on_stop)
        bar.addWidget(self.stop_btn)
        self.slider = GlassSlider(on_drag=self._on_slider_drag, on_commit=self._on_slider_commit)
        bar.addWidget(self.slider, 1)
        self.bpm = BpmBadge(lambda d: self.change_speed(d))
        self.bpm.setFixedSize(56, 28)
        bar.addWidget(self.bpm)
        reset = GlassButton("↺")
        reset.setObjectName("iconbtn")
        reset.setToolTip("Reset: stop and speed back to 100%")
        reset.clicked.connect(self.on_reset)
        bar.addWidget(reset)
        root.addLayout(bar)

        time_row = QHBoxLayout()
        time_row.addStretch()
        self.time = Badge(pill=True)
        self.time.setText("00:00:00/00:00:00")
        self.time.setFixedSize(190, 26)
        time_row.addWidget(self.time)
        time_row.addStretch()
        root.addLayout(time_row)

    # -------------------------------------------------------- options
    def _apply_flags(self):
        for key, tg in self._toggles.items():
            if key == "roll3D":
                tg.set_value(bool(self.cfg.get("roll.mode3d", False)))
            else:
                tg.set_value(bool(self.cfg.get(f"{self.mode}.{key}", False)))
        self.transport.loop = bool(self.cfg.get(f"{self.mode}.loop", False))
        if self.mode == "piano":
            on = bool(self.cfg.get("piano.previewSound", False))
            self.preview_btn.setText(f"Preview sound: {'on' if on else 'off'}")
            self.preview_btn.set_glass_kind("blue" if on else "clear")
            self._paint_hand()
        if self.mode in self.app.speed:
            self.transport.set_speed(self.app.speed[self.mode])

    def _set_option(self, key: str, value: bool):
        if key == "roll3D":
            self.cfg.set("roll.mode3d", value)
            return
        self.cfg.set(f"{self.mode}.{key}", value)
        if key == "loop":
            self.transport.loop = value

    def _set_hand(self, value: str):
        self.cfg.set(f"{self.mode}.hand", value)
        self._paint_hand()

    def _paint_hand(self):
        current = self.cfg.get(f"{self.mode}.hand", "all")
        for value, pill in self._hand_btns.items():
            pill.set_glass_kind("blue" if value == current else "clear")

    def _on_cfg_change(self, path: str):
        if path == "*":
            self._apply_flags()
            self.rebuild_roll()
            self._refresh_chips()
            return
        if path.startswith("hotkeys."):
            self._refresh_chips()
        elif path.startswith(self.mode + "."):
            rest = path[len(self.mode) + 1:]
            if rest.split(".")[0] in ROLL_KEYS:
                self.rebuild_roll()
            if rest in self._toggles or rest == "loop":
                self._apply_flags()
            if rest == "hand":
                self._paint_hand()
            if rest == "currentFile":
                pass
        elif path.startswith("roll."):
            self.roll.refresh_style()
            if path == "roll.mode3d" and "roll3D" in self._toggles:
                self._toggles["roll3D"].set_value(bool(self.cfg.get("roll.mode3d", False)))

    def _refresh_chips(self):
        for name, chip in self._hot_chips.items():
            chip.set_key(self.cfg.get(f"hotkeys.{name}", ""))

    # ------------------------------------------------------------ files
    def select_file(self):
        start = os.path.dirname(self.cfg.get(f"{self.mode}.currentFile", "") or "") or os.path.expanduser("~")
        path = pick_midi_file(self, start if os.path.isdir(start) else "")
        if path:
            self.load_path(path)

    def save_midi(self):
        source = self.cfg.get(f"{self.mode}.currentFile", "")
        if not self.song or not source or not os.path.isfile(source):
            self.set_status("Open a MIDI file first.", MUTED)
            return
        target, _f = QFileDialog.getSaveFileName(
            self, "Save MIDI as", os.path.basename(source), "MIDI files (*.mid *.midi)")
        if target:
            try:
                shutil.copyfile(source, target)
                self.set_status("MIDI saved.", SOFT)
            except OSError as exc:
                self.set_status(f"Could not save MIDI: {exc}", ERR)

    def load_path(self, path: str, remember: bool = True, quiet: bool = False):
        self.set_status("Loading…", MUTED)
        try:
            song = load_song(path)
        except MidiLoadError as exc:
            if not quiet:
                self.set_status(f"⚠ {exc}", ERR)
            else:
                self.set_status("")
            return False
        except Exception as exc:  # corrupted files can raise anything
            log.exception("loading %s", path)
            self.set_status(f"⚠ Could not read this file ({exc.__class__.__name__}).", ERR)
            return False
        self.song = song
        # drums always need the percussion channel (that IS the drum part); other modes can skip it
        skip = bool(self.cfg.get(f"{self.mode}.skipPercussion", True)) and self.mode != "drums"
        view = song.view(self.mode, skip)
        self.transport.load(view, song.length)
        self.rebuild_roll()
        if remember:
            self.cfg.set(f"{self.mode}.currentFile", path)
        self._refresh_status()
        self.update_view()
        return True

    def rebuild_roll(self):
        view = None
        if self.song:
            skip = bool(self.cfg.get(f"{self.mode}.skipPercussion", True)) and self.mode != "drums"
            view = self.song.view(self.mode, skip)
        self.roll.set_data(build_roll(self.mode, view, self.cfg.data[self.mode]))

    def _refresh_status(self):
        caption = CAPTIONS[self.mode]
        self.roll.set_caption(f"{caption}  ·  {self.song.name}" if self.song else caption)
        if self.song:
            n = len(self.transport.view.notes) if self.transport.view else 0
            self.set_status(f"{self.song.name}  ·  {format_time(self.song.length)[3:]}  ·  {n} notes", MUTED)
        elif not self.app.keys.backend.available:
            self.set_status(f"⚠ Keyboard simulation unavailable: {self.app.keys.backend.error}", WARN)
        else:
            self.set_status("")

    def set_status(self, text: str, color: str | None = None):
        self.status.set_text(text, color)

    # ---------------------------------------------------------- transport
    def on_play(self):
        if not self.song:
            self.set_status("Select a MIDI file first.", WARN)
            return
        if self.transport.state == PLAYING:
            self.transport.pause()
        else:
            self.transport.play()
        self.update_view()

    def on_pause(self):
        if self.transport.state in (PLAYING, PAUSED):
            self.transport.toggle_pause()
        self.update_view()

    def on_hotkey_play(self):
        if self.song and self.transport.state != PLAYING:
            self.transport.play()
        elif not self.song:
            self.set_status("Select a MIDI file first.", WARN)
        self.update_view()

    def on_stop(self):
        self.transport.stop()
        self.update_view()

    def on_reset(self):
        self.transport.stop()
        self.app.set_speed(self.mode, 1.0)
        self.update_view()

    def change_speed(self, delta_percent: float):
        step = float(self.cfg.get("app.speedStep", 5))
        sign = 1 if delta_percent > 0 else -1
        self.app.set_speed(self.mode, round((self.transport.speed + sign * step / 100), 4))

    def leave(self):
        """Page is hidden: stop sending keys (unless the MIDI player window is playing this instrument)."""
        if self.app.midi_owns(self.mode):
            return
        self.transport.stop()
        self.update_view()

    # slider
    def _on_slider_drag(self, v):
        if self.song:
            self.time.setText(f"{format_time(v * self.song.length)}/{format_time(self.song.length)}")

    def _on_slider_commit(self, v):
        if self.song:
            self.transport.seek(v * self.song.length)

    # -------------------------------------------------------------- tick
    def update_view(self):
        t = self.transport
        pos = t.position()
        if t.consume_finished():   # the state change already resets position and buttons
            self.app.song_finished(self.mode)
        self.roll.pos = pos
        self.roll.update()
        length = t.length if self.song else 0.0
        if not self.slider.dragging:
            self.slider.set_fraction(pos / length if length else 0.0)
            self.time.setText(f"{format_time(pos)}/{format_time(length)}")
        bpm = (self.song.bpm_at(pos) if self.song else 120.0) * t.speed
        txt = str(int(round(bpm)))
        if self.bpm.text() != txt:
            self.bpm.setText(txt)
        playing = t.state == PLAYING
        want = ("PAUSE", "amber") if playing else ("PLAY", "green")
        if self.play_btn.text() != want[0]:
            self.play_btn.setText(want[0])
            self.play_btn.set_glass_kind(want[1])
