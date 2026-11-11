"""Trang SETTING — bản Qt kính: hotkeys, playback, âm bàn phím giả, piano roll, cửa sổ, dữ liệu."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget)

from .. import VERSION_LABEL
from ..fakesound import DEFAULT_DEVICE_LABEL, list_output_devices
from ..paths import config_dir, resource_path
from .glassbtn import GlassButton, GlassToggle
from .widgets import (EllipsisLabel, HotkeyChip, Row, ScrollArea, SectionLabel, Stepper,
                      ValueSlider, make_h, make_v)

MODE_KEYS = ["piano"]
PITCH_NAMES = ["Lowest", "Low", "Middle", "High", "Highest"]
PITCH_VALUES = [-24, -12, 0, 12, 24]
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif")
BACKGROUND_NAME = "roll_background"
HOTKEY_ROWS = [("play", "Play"), ("pause", "Pause"), ("stop", "Stop"),
               ("speedup", "Speed up"), ("slowdown", "Slow down")]
FAINT = "#6b6b74"


class SettingsPage(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app, self.cfg = app, app.cfg
        self._speed_sliders: dict[str, ValueSlider] = {}
        self.hot_chips: dict[str, HotkeyChip] = {}
        self._device_names: list[str] = []
        self._build()
        self.cfg.on_change(self._cfg_changed)

    # --------------------------------------------------------- helpers
    def _section(self, lay: QVBoxLayout, title: str):
        lay.addWidget(SectionLabel(title))

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 14, 14, 14)
        scroll = ScrollArea()
        inner = QWidget()
        lay = make_v(inner)
        lay.setSpacing(4)
        title = QLabel("Settings")
        title.setObjectName("page-title")
        lay.addWidget(title)
        lay.addSpacing(6)

        # -- hotkeys
        self._section(lay, "Hotkeys")
        for name, text in HOTKEY_ROWS:
            chip = HotkeyChip(name, self.cfg.get(f"hotkeys.{name}", ""), self.app.rebind_hotkey)
            chip.setToolTip("Click, then press the key you want")
            self.hot_chips[name] = chip
            lay.addWidget(Row(text, chip))
        hint = QLabel("Hotkeys work while another window (your game) has focus. Linux: needs an X11 session.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # -- playback
        self._section(lay, "Playback")
        lay.addWidget(Row("Speed step", ValueSlider(1, 25, float(self.cfg.get("app.speedStep", 5)),
                                                    lambda v: self.cfg.set("app.speedStep", v), 1, "{:g}%")))
        lay.addWidget(Row("Preview sound", GlassToggle(bool(self.cfg.get("piano.previewSound", False)),
                                                       lambda v: self.cfg.set("piano.previewSound", v)),
                          hint="On: Play sounds the MIDI as piano and presses no keys (no macro). Off: normal macro."))
        for m in MODE_KEYS:
            self._build_mode(lay, m)

        # -- fake keyboard sound
        self._section(lay, "Fake keyboard sound")
        lay.addWidget(Row("Fake keyboard sound", GlassToggle(bool(self.cfg.get("fakeSound.enabled", False)),
                                                             lambda v: self.cfg.set("fakeSound.enabled", v)),
                          hint="Plays a real typing click for every key the app presses, so it sounds like you type "
                               "the notes by hand."))
        lay.addWidget(Row("Volume", ValueSlider(0, 100, float(self.cfg.get("fakeSound.volume", 50)),
                                                lambda v: self.cfg.set("fakeSound.volume", v), 5, "{:g}%")))
        lay.addWidget(Row("Send sound to", self._device_picker(),
                          hint='Voice chat: pick your virtual cable here (e.g. VB-Audio "CABLE Input"), then choose '
                               'the cable\'s other end ("CABLE Output") as the microphone in Roblox.'))
        lay.addWidget(Row("Also play on my speakers", GlassToggle(bool(self.cfg.get("fakeSound.alsoSpeakers", False)),
                                                                  lambda v: self.cfg.set("fakeSound.alsoSpeakers", v)),
                          hint="Plays the same clicks on the default output, so you hear what the others hear."))
        test_row = make_h()
        test_btn = GlassButton("Test sound")
        test_btn.setObjectName("tool")
        test_btn.clicked.connect(self._test_fake_sound)
        test_row.addWidget(test_btn)
        test_row.addStretch()
        host = QWidget()
        host.setLayout(test_row)
        lay.addWidget(Row("Test", host))
        self.fake_status = EllipsisLabel("", 11, FAINT)
        lay.addWidget(self.fake_status)
        self._update_fake_status()

        # -- MIDI Hub preview
        self._section(lay, "MIDI Hub preview")
        lay.addWidget(Row("Piano SoundFont", GlassToggle(bool(self.cfg.get("hub.useSoundfont", False)),
                                                         lambda v: self.cfg.set("hub.useSoundfont", v)),
                          hint="The Hub preview plays the song with the bundled Piano.sf2 SoundFont. "
                               "Off = the built-in synthesised piano. Applies the next time a preview starts."))

        # -- piano roll
        self._section(lay, "Piano roll")
        self._mode3d_toggle = GlassToggle(bool(self.cfg.get("roll.mode3d", False)),
                                          lambda v: self.cfg.set("roll.mode3d", v))
        lay.addWidget(Row("3D roll", self._mode3d_toggle,
                          hint="On: 3D roll with the perspective floor. Off: flat 2D roll (default)."))
        lay.addWidget(Row("Fall time", ValueSlider(1.0, 8.0, float(self.cfg.get("roll.fallSeconds", 3.0)),
                                                   lambda v: self.cfg.set("roll.fallSeconds", v), 0.5, "{:g} s")))
        lay.addWidget(Row("Key glow", GlassToggle(bool(self.cfg.get("roll.glow", True)),
                                                  lambda v: self.cfg.set("roll.glow", v))))
        lay.addWidget(Row("Key letters (piano)", GlassToggle(bool(self.cfg.get("roll.keyLabels", True)),
                                                             lambda v: self.cfg.set("roll.keyLabels", v))))
        colors = list(("blue", "cyan", "green", "pink", "amber", "rainbow"))
        cur = self.cfg.get("roll.noteColor", "blue")
        self._color_names = colors
        self._color_stepper = Stepper([c.title() for c in colors],
                                      colors.index(cur) if cur in colors else 0,
                                      lambda i: self.cfg.set("roll.noteColor", colors[i]), 110)
        lay.addWidget(Row("Note color", self._color_stepper))
        self._background_row(lay)
        lay.addWidget(Row("Background darkness", ValueSlider(0, 90, float(self.cfg.get("roll.backgroundDim", 50)),
                                                             lambda v: self.cfg.set("roll.backgroundDim", v), 5, "{:g}%"),
                          hint="Background picture for the piano roll: JPG, PNG or GIF (first frame)."))

        # -- window
        self._section(lay, "Window")
        lay.addWidget(Row("Window opacity", ValueSlider(
            40, 100, round(self.app.opacity() * 100), lambda v: self.app.set_opacity(v / 100), 5, "{:g}%"),
            hint="Makes the whole app see-through (the mini player too)."))
        lay.addWidget(Row("Always on top", GlassToggle(bool(self.cfg.get("app.topmost", False)),
                                                       self.app.set_topmost)))

        # -- data
        self._section(lay, "Data")
        btns = QWidget()
        brow = make_h(btns)
        brow.setContentsMargins(0, 0, 0, 0)
        open_btn = GlassButton("Open config folder")
        open_btn.setObjectName("ghost")
        open_btn.clicked.connect(self._open_folder)
        brow.addWidget(open_btn)
        reset_btn = GlassButton("Reset all")
        reset_btn.setObjectName("stop")
        reset_btn.clicked.connect(self._reset)
        brow.addWidget(reset_btn)
        brow.addStretch()
        lay.addWidget(Row("Config", btns,
                          hint="The 61/88-key piano map is stored in config.json (pianoMap) if you need to edit it."))

        # -- about
        self._section(lay, "About")
        try:
            img = QImage(resource_path("assets/icons/app.png"))
            if not img.isNull():
                logo = QLabel()
                logo.setPixmap(QPixmap.fromImage(img.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                                            Qt.TransformationMode.SmoothTransformation)))
                lay.addWidget(logo)
        except Exception:
            pass
        ver = QLabel(f"tetoMIDI {VERSION_LABEL}")
        ver.setObjectName("row-label")
        lay.addWidget(ver)
        lic = QLabel("GNU GPL v3")
        lic.setObjectName("hint")
        lay.addWidget(lic)
        lay.addSpacing(20)
        lay.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ------------------------------------------------ playback per mode
    def _build_mode(self, lay: QVBoxLayout, mode: str):
        c = mode
        self._speed_sliders[mode] = None  # sẽ gán ngay dưới đây
        speed_holder = {}

        def make_speed():
            s = ValueSlider(10, 500, round(self.app.speed.get(mode, 1.0) * 100),
                            lambda v: self.app.set_speed(mode, v / 100), 5, "{:g}%")
            self._speed_sliders[mode] = s
            return s
        lay.addWidget(Row("Playback speed", make_speed()))
        lay.addWidget(Row("Custom hold length", GlassToggle(bool(self.cfg.get(f"{c}.customHoldLength.enabled", False)),
                                                            lambda v: self.cfg.set(f"{c}.customHoldLength.enabled", v))))
        lay.addWidget(Row("Hold time", ValueSlider(0.02, 1.0, float(self.cfg.get(f"{c}.customHoldLength.noteLength", 0.2)),
                                                   lambda v: self.cfg.set(f"{c}.customHoldLength.noteLength", v), 0.02, "{:.2f} s")))
        lay.addWidget(Row("Finger limit", ValueSlider(1, 11, float(self.cfg.get(f"{c}.fingerLimit", 11)),
                                                      lambda v: self.cfg.set(f"{c}.fingerLimit", int(v)), 1, "{:g}"),
                          hint="Max keys held at once (11 = unlimited)."))
        lay.addWidget(Row("Release keys on pause", GlassToggle(bool(self.cfg.get(f"{c}.releaseOnPause", False)),
                                                               lambda v: self.cfg.set(f"{c}.releaseOnPause", v))))
        lay.addWidget(Row("Human error", GlassToggle(bool(self.cfg.get(f"{c}.randomFail.enabled", False)),
                                                     lambda v: self.cfg.set(f"{c}.randomFail.enabled", v))))
        lay.addWidget(Row("Timing error chance", ValueSlider(0, 50, float(self.cfg.get(f"{c}.randomFail.speed", 0)),
                                                             lambda v: self.cfg.set(f"{c}.randomFail.speed", v), 1, "{:g}%")))
        if mode == "piano":
            lay.addWidget(Row("Wrong-note chance", ValueSlider(0, 50, float(self.cfg.get("piano.randomFail.transpose", 0)),
                                                               lambda v: self.cfg.set("piano.randomFail.transpose", v), 1, "{:g}%")))
            pitch = self.cfg.get("piano.pitchOffset", 0)
            lay.addWidget(Row("Pitch", Stepper(PITCH_NAMES,
                                               PITCH_VALUES.index(pitch) if pitch in PITCH_VALUES else 2,
                                               lambda i: self.cfg.set("piano.pitchOffset", PITCH_VALUES[i]), 110)))
            lay.addWidget(Row("Key", Stepper(KEY_NAMES, int(self.cfg.get("piano.transposeOffset", 0)) % 12,
                                             lambda i: self.cfg.set("piano.transposeOffset", i), 70)))
            lay.addWidget(Row("No doubles", GlassToggle(bool(self.cfg.get("piano.noDoubles", False)),
                                                        lambda v: self.cfg.set("piano.noDoubles", v)),
                          hint="Re-press a key that is still held."))
            lay.addWidget(Row("Sustain cut-off", ValueSlider(0, 127, float(self.cfg.get("piano.sustainCutoff", 0)),
                                                             lambda v: self.cfg.set("piano.sustainCutoff", v), 1, "{:g}")))
            lay.addWidget(Row("Skip percussion channel", GlassToggle(bool(self.cfg.get("piano.skipPercussion", True)),
                                                                     lambda v: self.cfg.set("piano.skipPercussion", v)),
                          hint="Don't type MIDI channel 10 (percussion) as piano keys."))

    # ------------------------------------------------ fake keyboard sound
    def _short(self, name, limit=28):
        return name if len(name) <= limit else name[:limit - 1] + "…"

    def _device_options(self) -> list[str]:
        names = [n for _, n in list_output_devices()]
        self._device_count = len(names)
        saved = str(self.cfg.get("fakeSound.device", "") or "")
        self._device_missing = saved if saved and saved not in names else ""
        if self._device_missing:
            names.append(saved)
        self._device_names = [""] + names   # "" = system default
        return [DEFAULT_DEVICE_LABEL] + names

    def _device_index(self, options) -> int:
        saved = str(self.cfg.get("fakeSound.device", "") or "")
        return self._device_names.index(saved) if saved in self._device_names else 0

    def _device_picker(self) -> QWidget:
        box = QWidget()
        lay = make_h(box)
        lay.setContentsMargins(0, 0, 0, 0)
        options = self._device_options()
        self.device_stepper = Stepper([self._short(n) for n in options], self._device_index(options),
                                      self._device_chosen, 210)
        lay.addWidget(self.device_stepper)
        rescan = GlassButton("Rescan")
        rescan.setObjectName("tool")
        rescan.clicked.connect(self._rescan_devices)
        lay.addWidget(rescan)
        return box

    def _device_chosen(self, index):
        if 0 <= index < len(self._device_names):
            self.cfg.set("fakeSound.device", self._device_names[index])

    def _rescan_devices(self):
        options = self._device_options()
        self.device_stepper.options = [self._short(n) for n in options]
        self.device_stepper.set(self._device_index(options))
        self.app.fake_sound.apply()
        self._update_fake_status()

    def _test_fake_sound(self):
        self.app.fake_sound.test()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, self._update_fake_status)

    def _update_fake_status(self):
        err = self.app.fake_sound.error
        if err:
            text, color = f"Audio problem: {err}", "#e5736b"
        elif not getattr(self, "_device_count", 0):
            text, color = "No audio output device found (PortAudio missing?).", "#e5736b"
        elif getattr(self, "_device_missing", ""):
            text, color = f"Saved device not found: {self._device_missing}", "#e5736b"
        elif self.cfg.get("fakeSound.enabled", False):
            text, color = "Fake keyboard sound is on.", FAINT
        else:
            text, color = "Fake keyboard sound is off.", FAINT
        self.fake_status.set_text(text, color)

    # ------------------------------------------------ roll background picture
    def _background_row(self, lay: QVBoxLayout):
        box = QWidget()
        row = make_h(box)
        row.setContentsMargins(0, 0, 0, 0)
        choose = GlassButton("Choose image")
        choose.setObjectName("ghost")
        choose.clicked.connect(self._choose_background)
        row.addWidget(choose)
        remove = GlassButton("Remove")
        remove.setObjectName("ghost")
        remove.clicked.connect(self._remove_background)
        row.addWidget(remove)
        row.addStretch()
        lay.addWidget(Row("Background image", box))
        self.bg_name = EllipsisLabel(self._background_text(), 11, FAINT)
        lay.addWidget(self.bg_name)

    def _background_text(self) -> str:
        path = self.cfg.get("roll.background", "")
        if not path or not os.path.isfile(path):
            return "No picture: plain background"
        return f"Current picture: {os.path.basename(path)}"

    def _clear_background_files(self, keep=None):
        for old in glob.glob(str(config_dir() / "backgrounds" / (BACKGROUND_NAME + ".*"))):
            if old != keep:
                try:
                    os.remove(old)
                except OSError:
                    pass

    def _choose_background(self):
        from PySide6.QtWidgets import QFileDialog
        path, _f = QFileDialog.getOpenFileName(self, "Choose a background picture", "",
                                               "Pictures (*.jpg *.jpeg *.png *.gif);;All files (*)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext not in IMAGE_EXTS:
                raise ValueError("unsupported file type")
            img = QImage(path)
            if img.isNull():
                raise ValueError("not a picture")
            folder = config_dir() / "backgrounds"
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / (BACKGROUND_NAME + ext)
            if os.path.abspath(path) != os.path.abspath(dest):
                shutil.copyfile(path, dest)
            self._clear_background_files(keep=str(dest))
        except (OSError, ValueError):
            QMessageBox.information(self, "Background picture",
                                    "This file cannot be used. Please choose a JPG, PNG or GIF picture.")
            return
        self.cfg.set("roll.background", str(dest))

    def _remove_background(self):
        self.cfg.set("roll.background", "")
        self._clear_background_files()

    # ------------------------------------------------------- events
    def _cfg_changed(self, path):
        if path.startswith("hotkeys.") or path == "*":
            for n, chip in self.hot_chips.items():
                chip.set_key(self.cfg.get(f"hotkeys.{n}", ""))
        if path.startswith("fakeSound.") or path == "*":
            from PySide6.QtCore import QTimer
            QTimer.singleShot(250, self._update_fake_status)   # app (re)opens the audio streams after this
        if path in ("roll.background", "*"):
            self.bg_name.set_text(self._background_text())
        if path == "roll.mode3d" and getattr(self, "_mode3d_toggle", None) is not None:
            self._mode3d_toggle.set_value(bool(self.cfg.get("roll.mode3d", False)))
        if path == "roll.noteColor" and getattr(self, "_color_stepper", None) is not None:
            cur = self.cfg.get("roll.noteColor", "blue")
            if cur in self._color_names:
                self._color_stepper.display(self._color_names.index(cur))

    def show_chip_capturing(self, name):
        if name in self.hot_chips:
            self.hot_chips[name].set_key("…")

    def refresh(self):
        for mode, s in self._speed_sliders.items():
            if s is not None:
                s.set(round(self.app.speed.get(mode, 1.0) * 100))

    def _open_folder(self):
        path = str(config_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606 - opening the user's own config folder
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            QMessageBox.information(self, "Config folder", path)

    def _reset(self):
        if QMessageBox.question(self, "Reset all settings",
                                "Restore every setting (hotkeys, key maps, options) to its default?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.app.reset_settings()
