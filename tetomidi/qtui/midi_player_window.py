"""MIDI Player window (glass style): a playlist that drives the key-press player of the chosen instrument.

Like the mini player it owns no playback state: songs are loaded into the instrument page and played
by that page's transport, so options, speed and the piano roll behave exactly as in the main window.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

from ..engine.playlist import REPEAT_MODES, Playlist
from ..engine.transport import PLAYING
from ..midi_data import format_time
from .glassbtn import Badge, GlassButton, GlassSlider
from .player_page import PlayerPage
from .widgets import EllipsisLabel, PageTitle

MODES = (("piano", "Piano"), ("drums", "Drums"), ("guitar", "Guitar"))
MIDI_EXTS = (".mid", ".midi")
RESTART_AFTER = 3.0   # "Prev" restarts the song when more than this many seconds were played
ACTIVE = QColor(47, 111, 166)          # pill xanh khi bật (như chip của mini player)
LIST_QSS = """
QListWidget {
    background: rgba(6,6,8,215);
    border: 1px solid rgba(255,255,255,30);
    border-radius: 12px;
    color: #cfd2da;
    font-size: 12px;
    padding: 6px;
    outline: none;
}
QListWidget::item { padding: 7px 10px; border-radius: 8px; }
QListWidget::item:hover { background: rgba(255,255,255,22); }
QListWidget::item:selected { background: rgba(255,255,255,36); color: #f2f2f5; }
"""


def find_midi_files(folder: str) -> list[str]:
    found: list[str] = []
    for root, _dirs, files in os.walk(folder):
        found += [os.path.join(root, f) for f in files if f.lower().endswith(MIDI_EXTS)]
    return sorted(found, key=str.lower)


class MidiPlayerWindow(QWidget):
    def __init__(self, app):
        super().__init__(None)
        self.app, self.cfg = app, app.cfg
        self.setObjectName("editor")   # same dark background as the transcriber editor
        self.setWindowTitle("tetoMIDI – MIDI Player")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(self.cfg.get("app.topmost", False)))
        self.resize(640, 780)
        self.setMinimumSize(560, 640)
        self._last: dict = {}

        mode = self.cfg.get("player.mode", "piano")
        self.mode = mode if mode in dict(MODES) else "piano"
        saved = [p for p in self.cfg.get("player.playlist", []) if isinstance(p, str) and os.path.isfile(p)]
        index = self.cfg.get("player.index", -1)
        self.playlist = Playlist(saved, index if isinstance(index, int) else -1, self.cfg.get("player.repeat", "off"),
                                 bool(self.cfg.get("player.shuffle", False)))
        self._build()
        self._refresh_list()
        self._refresh_mode_buttons()
        self._apply_opacity()

    @property
    def page(self) -> PlayerPage:
        return self.app.pages[self.mode]

    # ---------------------------------------------------------------- build
    def paintEvent(self, _):
        """Nền tối kiểu Transcriber editor (QSS #editor để trong suốt nên tự vẽ ở đây)."""
        from PySide6.QtGui import QBrush, QLinearGradient, QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 10, 13))
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(255, 255, 255, 26))
        g.setColorAt(0.10, QColor(255, 255, 255, 6))
        g.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.fillRect(self.rect(), QBrush(g))
        p.end()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(PageTitle("MIDI Player"))
        head.addStretch()
        self.mode_btns: dict[str, GlassButton] = {}
        for key, text in MODES:
            btn = GlassButton(text)
            btn.setObjectName("tool")
            btn.setFixedHeight(30)
            btn.setToolTip(f"Play the list on the {key} player")
            btn.clicked.connect(lambda _=False, k=key: self.set_mode(k))
            self.mode_btns[key] = btn
            head.addWidget(btn)
        root.addLayout(head)

        self.now = EllipsisLabel("Nothing loaded. Add files, then double-click a song.", 13, "#9c9ca4")
        self.now.setObjectName("file")
        root.addWidget(self.now)

        self.list = QListWidget()
        self.list.setStyleSheet(LIST_QSS)
        self.list.setUniformItemSizes(False)
        self.list.itemDoubleClicked.connect(lambda _i: self._play_selected())
        self.list.itemActivated.connect(lambda _i: self._play_selected())
        root.addWidget(self.list, 1)

        edit = QHBoxLayout()
        edit.setSpacing(8)
        for text, cmd in (("Add files", self.add_files), ("Add folder", self.add_folder),
                          ("Remove", self.remove_selected), ("Clear", self.clear)):
            btn = GlassButton(text)
            btn.setObjectName("ghost")
            btn.clicked.connect(cmd)
            edit.addWidget(btn)
        edit.addStretch()
        self.count = QLabel("")
        self.count.setObjectName("sub")
        edit.addWidget(self.count)
        root.addLayout(edit)

        seek = QHBoxLayout()
        seek.setSpacing(12)
        self.slider = GlassSlider(on_drag=self._on_drag, on_commit=self._on_commit)
        seek.addWidget(self.slider, 1)
        self.time = Badge(text="00:00:00/00:00:00")
        self.time.setFixedSize(190, 26)
        seek.addWidget(self.time)
        root.addLayout(seek)

        ctl = QHBoxLayout()
        ctl.setSpacing(10)
        ctl.addStretch()
        prev = GlassButton("PREV")
        prev.setObjectName("ghost")
        prev.setFixedSize(86, 40)
        prev.clicked.connect(self.prev)
        ctl.addWidget(prev)
        self.play_btn = GlassButton("PLAY")
        self.play_btn.setObjectName("play")
        self.play_btn.setFixedSize(96, 40)
        self.play_btn.clicked.connect(self.toggle_play)
        ctl.addWidget(self.play_btn)
        stop = GlassButton("STOP")
        stop.setObjectName("stop")
        stop.setFixedSize(96, 40)
        stop.clicked.connect(self.stop)
        ctl.addWidget(stop)
        nxt = GlassButton("NEXT")
        nxt.setObjectName("ghost")
        nxt.setFixedSize(86, 40)
        nxt.clicked.connect(self.next)
        ctl.addWidget(nxt)
        ctl.addStretch()
        root.addLayout(ctl)

        opt = QHBoxLayout()
        opt.setSpacing(8)
        self.repeat_btn = GlassButton("Repeat: off")
        self.repeat_btn.setObjectName("tool")
        self.repeat_btn.setFixedHeight(32)
        self.repeat_btn.clicked.connect(self.cycle_repeat)
        opt.addWidget(self.repeat_btn)
        self.shuffle_btn = GlassButton("Shuffle: off")
        self.shuffle_btn.setObjectName("tool")
        self.shuffle_btn.setFixedHeight(32)
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        opt.addWidget(self.shuffle_btn)
        opt.addStretch()
        minus = GlassButton("–")
        minus.setObjectName("iconbtn")
        minus.setToolTip("Slower")
        minus.clicked.connect(lambda: self.change_speed(-1))
        opt.addWidget(minus)
        self.speed = Badge(text="100%")
        self.speed.setFixedSize(64, 28)
        opt.addWidget(self.speed)
        plus = GlassButton("+")
        plus.setObjectName("iconbtn")
        plus.setToolTip("Faster")
        plus.clicked.connect(lambda: self.change_speed(1))
        opt.addWidget(plus)
        opt.addStretch()
        self.preview_btn = GlassButton("Preview sound: off")
        self.preview_btn.setObjectName("tool")
        self.preview_btn.setFixedHeight(32)
        self.preview_btn.setToolTip("On = plays the song, no macro")
        self.preview_btn.clicked.connect(self.toggle_preview)
        opt.addWidget(self.preview_btn)
        root.addLayout(opt)

    # ------------------------------------------------------------- helpers
    def _set(self, key, text, widget_set):
        if self._last.get(key) != text:
            self._last[key] = text
            widget_set(text)

    _set_text = _set

    def _apply_opacity(self):
        self.setWindowOpacity(self.app.opacity())

    # ------------------------------------------------------------ playlist
    def _save_list(self):
        self.cfg.set("player.playlist", list(self.playlist.items))
        self.cfg.set("player.index", self.playlist.index)

    def _refresh_list(self):
        top = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        for i, path in enumerate(self.playlist.items):
            QListWidgetItem(f"{i + 1:>3}.  {os.path.basename(path)}", self.list)
        self._mark_current()
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(top)
        n = len(self.playlist.items)
        self.count.setText(f"{n} song{'s' if n != 1 else ''}")

    def _mark_current(self):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if i == self.playlist.index:
                item.setBackground(ACTIVE)
                item.setForeground(QColor("#ffffff"))
            else:
                item.setBackground(QColor(0, 0, 0, 0))
                item.setForeground(QColor("#cfd2da"))

    def add_paths(self, paths) -> int:
        paths = [p for p in paths if p.lower().endswith(MIDI_EXTS) and os.path.isfile(p)]
        added = self.playlist.add(paths)
        self._save_list()
        self._refresh_list()
        return added

    def add_files(self):
        start = os.path.dirname(self.playlist.items[-1]) if self.playlist.items else os.path.expanduser("~")
        paths, _f = QFileDialog.getOpenFileNames(
            self, "Add MIDI files", start if os.path.isdir(start) else "",
            "MIDI files (*.mid *.midi *.MID *.MIDI);;All files (*)")
        if paths:
            self.add_paths(paths)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add every MIDI file in a folder (with subfolders)")
        if folder:
            n = self.add_paths(find_midi_files(folder))
            if not n:
                self.now.set_text("No new MIDI files found in that folder.", "#e0a13a")

    def remove_selected(self):
        sel = sorted({i.row() for i in self.list.selectedIndexes()}, reverse=True)
        for i in sel:
            if self.playlist.remove(i):   # the loaded song is no longer in the list
                self._last.pop("now", None)
        self._save_list()
        self._refresh_list()

    def clear(self):
        self.playlist.clear()
        self._save_list()
        self._refresh_list()

    # ------------------------------------------------------------ playback
    def _play_selected(self):
        sel = self.list.currentRow()
        if sel >= 0:
            self._play_from(sel, lambda: self.playlist.next())

    def _play_from(self, i, advance, remember=True) -> bool:
        """Load and play entry ``i``; unreadable files are skipped by asking ``advance`` for the next entry."""
        page = self.page
        for _ in range(len(self.playlist.items) + 1):
            if i is None:
                return False
            if page.load_path(self.playlist.items[i], remember=False):
                self.playlist.go(i, remember)
                self._save_list()
                self._mark_current()
                self._apply_repeat()
                page.transport.play()
                page.update_view()
                self._last.pop("now", None)
                return True
            self.now.set_text(f"⚠ {os.path.basename(self.playlist.items[i])}: skipped", "#ff7b72")
            self.playlist.go(i, remember=False)
            i = advance()
        return False

    def use_mode(self, mode: str):
        """Play this list on ``mode`` (the main player playlist controls it)."""
        if mode != self.mode:
            self.set_mode(mode)

    def start(self):
        """Play the current (or first) entry of the list."""
        if self.playlist.items:
            self._play_from(max(self.playlist.index, 0), lambda: self.playlist.next())

    def toggle_play(self):
        page = self.page
        if page.song is None and self.playlist.items:
            self.start()
        else:
            page.on_play()

    def stop(self):
        self.page.on_stop()

    def next(self):
        self._play_from(self.playlist.next(), lambda: self.playlist.next())

    def prev(self):
        page = self.page
        if page.song is not None and page.transport.position() > RESTART_AFTER:
            page.transport.seek(0.0)
            return
        i = self.playlist.prev()
        if i is not None:
            self._play_from(i, lambda: self.playlist.prev(), remember=False)

    def on_finished(self):
        """The loaded song ended by itself: continue with the list."""
        page = self.page
        if page.song is not None and page.song.path == self.playlist.current():
            self._play_from(self.playlist.next(auto=True), lambda: self.playlist.next(auto=True))

    def hotkey(self, method: str, *args):
        """Global hotkeys act on this window's player while it is open."""
        page = self.page
        if method == "on_hotkey_play" and page.song is None and self.playlist.items:
            self.start()
        else:
            getattr(page, method)(*args)

    # -------------------------------------------------------------- options
    def set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.page.on_stop()
        self.mode = mode
        self.cfg.set("player.mode", mode)
        self._apply_repeat()
        self._refresh_mode_buttons()
        cur = self.playlist.current()
        if cur and (self.page.song is None or self.page.song.path != cur):
            self.page.load_path(cur, remember=False, quiet=True)
        self._last.clear()

    def _refresh_mode_buttons(self):
        for key, btn in self.mode_btns.items():
            btn.set_glass_kind("blue" if key == self.mode else "clear")

    def _apply_repeat(self):
        """Repeat one = the page's Loop switch; the other modes are handled by the list."""
        self.cfg.set(f"{self.mode}.loop", self.playlist.repeat == "one")

    def cycle_repeat(self):
        self.playlist.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.playlist.repeat) + 1) % len(REPEAT_MODES)]
        self.cfg.set("player.repeat", self.playlist.repeat)
        self._apply_repeat()

    def toggle_preview(self):
        self.cfg.set("piano.previewSound", not self.cfg.get("piano.previewSound", False))

    def toggle_shuffle(self):
        self.playlist.shuffle = not self.playlist.shuffle
        self.playlist._played = {self.playlist.index} if self.playlist.index >= 0 else set()
        self.cfg.set("player.shuffle", self.playlist.shuffle)

    def change_speed(self, sign: int):
        self.page.change_speed(sign)

    def on_settings_reset(self):
        """Settings were reset to defaults: forget the list too."""
        self.page.on_stop()
        self.playlist.clear()
        self.playlist.repeat, self.playlist.shuffle, self.mode = "off", False, "piano"
        self._refresh_mode_buttons()
        self._refresh_list()
        self._last.clear()

    # ----------------------------------------------------------------- tick
    def _on_drag(self, v):
        p = self.page
        if p.song:
            txt = f"{format_time(v * p.song.length)}/{format_time(p.song.length)}"
            if self._last.get("time") != txt:
                self._last["time"] = txt
                self.time.setText(txt)

    def _on_commit(self, v):
        p = self.page
        if p.song:
            p.transport.seek(v * p.song.length)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self.toggle_play()
        else:
            super().keyPressEvent(e)

    def update_view(self):
        p = self.page
        t = p.transport
        if t.consume_finished():
            self.on_finished()
        length = t.length if p.song else 0.0
        pos = t.position()
        if not self.slider.dragging:
            self.slider.set_fraction(pos / length if length else 0.0)
            txt = f"{format_time(pos)}/{format_time(length)}"
            if self._last.get("time") != txt:
                self._last["time"] = txt
                self.time.setText(txt)
        want = ("PAUSE", "amber") if t.state == PLAYING else ("PLAY", "green")
        if self._last.get("play") != want:
            self._last["play"] = want
            self.play_btn.setText(want[0])
            self.play_btn.set_glass_kind(want[1])
        name = p.song.name if p.song else "Nothing loaded. Add files, then double-click a song."
        if self._last.get("now") != name:
            self._last["now"] = name
            self.now.set_text(name, "#e2e2e6" if p.song else "#9c9ca4")
        self._set_text("speed", f"{int(round(self.app.speed[self.mode] * 100))}%", self.speed.setText)
        for key, text, btn, active in (
                ("repeat", f"Repeat: {self.playlist.repeat}", self.repeat_btn, self.playlist.repeat != "off"),
                ("shuffle", f"Shuffle: {'on' if self.playlist.shuffle else 'off'}", self.shuffle_btn,
                 self.playlist.shuffle),
                ("preview", f"Preview sound: {'on' if self.cfg.get('piano.previewSound', False) else 'off'}",
                 self.preview_btn, bool(self.cfg.get("piano.previewSound", False)))):
            state = (text, active)
            if self._last.get(key) != state:
                self._last[key] = state
                btn.setText(text)
                btn.set_glass_kind("blue" if active else "clear")

    # ---------------------------------------------------------------- close
    def closeEvent(self, e):
        """Hide the window; an instrument that is no longer on screen stops sending keys."""
        if self.app.current != self.mode:
            self.page.on_stop()
        e.ignore()
        self.hide()
