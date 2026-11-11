"""Main window in TetoTranscriber style: frameless glass window, sliding sidebar and pages.

Wires config, engine, hotkeys and pages together (same role as the old Tk ``ui/app.py``).
"""
from __future__ import annotations

import logging
import sys
import webbrowser

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QBrush, QRadialGradient
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import APP_NAME, DISCORD_URL, VERSION_LABEL, WEBSITE_URL
from ..config import Config
from ..console import KeyConsole
from ..engine.dispatchers import create_dispatcher
from ..engine.transport import Transport
from ..fakesound import FakeKeySound
from ..hotkeys import HotkeyManager
from ..keysim import KeySim, ScopedKeys
from ..paths import resource_path
from ..pianosound import PianoPreviewDispatcher, PianoSound
from .glass import STYLE
from .glassbtn import GlassButton
from .hub_page import HubPage
from .icons import app_icon, discord_icon, page_icon, sidebar_icon
from .mini_player import MiniPlayer
from .player_page import MODE_TITLES, PlayerPage
from .settings_page import SettingsPage
from .sidebar import Sidebar

log = logging.getLogger(__name__)
MODES = ("piano", "drums", "guitar")
TICK_MS = 16
IDLE_TICK_MS = 50   # nothing on screen: hotkeys are still polled, drawing is not needed
MIN_OPACITY = 0.4
WIN_W, WIN_H = 1020, 680
PAGE_TITLES = {"hub": "midi hub", "settings": "settings", **MODE_TITLES}


class GlassWindow(QWidget):
    """Khung kính bo tròn kiểu TetoTranscriber: thanh tiêu đề + trang + danh mục trượt."""

    def __init__(self, app: "TetoApp"):
        super().__init__(None)
        self.app = app
        self._drag = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setObjectName("glassroot")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WIN_W, WIN_H)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 14)
        root.setSpacing(8)

        # --- thanh tiêu đề (menu | title+sub | discord · gear · minimize · close)
        top = QHBoxLayout()
        top.setSpacing(10)
        menu_btn = GlassButton()
        menu_btn.setObjectName("iconbtn")
        menu_btn.setIcon(sidebar_icon(18))
        menu_btn.setIconSize(QSize(18, 18))
        menu_btn.setToolTip("Menu")
        menu_btn.clicked.connect(lambda *_: self.sidebar.toggle_panel())
        top.addWidget(menu_btn)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel(APP_NAME)
        self.title.setObjectName("title")
        self.sub = QLabel(f"piano player · {VERSION_LABEL}")
        self.sub.setObjectName("sub")
        titles.addWidget(self.title)
        titles.addWidget(self.sub)
        top.addLayout(titles)
        top.addStretch()
        discord = GlassButton()
        discord.setObjectName("discord")
        discord.setIcon(discord_icon(18))
        discord.setIconSize(QSize(18, 18))
        discord.setToolTip("Join the Discord server")
        discord.clicked.connect(lambda *_: webbrowser.open(DISCORD_URL))
        top.addWidget(discord)
        gear = GlassButton("⚙")
        gear.setObjectName("iconbtn")
        gear.setToolTip("Settings")
        gear.clicked.connect(lambda *_: self.app.show_page("settings"))
        top.addWidget(gear)
        mini = GlassButton("▢")
        mini.setObjectName("iconbtn")
        mini.setToolTip("Show the mini player")
        mini.clicked.connect(lambda *_: self.app.show_mini())
        top.addWidget(mini)
        minimize = GlassButton("–")
        minimize.setObjectName("iconbtn")
        minimize.setToolTip("Minimize to taskbar")
        minimize.clicked.connect(self.showMinimized)
        top.addWidget(minimize)
        close = GlassButton("✕")
        close.setObjectName("iconbtn")
        close.setToolTip("Close")
        close.clicked.connect(lambda *_: self.app.quit())
        top.addWidget(close)
        root.addLayout(top)

        # --- các trang đổi ngay trong cửa sổ này (piano / drums / guitar / hub / settings)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages: dict[str, QWidget] = {m: PlayerPage(self.app, m) for m in MODES}
        self.pages["hub"] = HubPage(self.app)
        self.pages["settings"] = SettingsPage(self.app)
        for page in self.pages.values():
            self.stack.addWidget(page)

        # --- danh mục trượt từ trái; tạo sau cùng để nằm trên mọi nội dung
        self.sidebar = Sidebar(self, [
            ("piano", "Piano", page_icon("piano")),
            ("drums", "Drums", page_icon("drums")),
            ("guitar", "Guitar", page_icon("guitar")),
            ("hub", "MIDI Hub", page_icon("hub")),
            ("settings", "Settings", page_icon("settings")),
            ("discord", "Discord", page_icon("discord")),
        ])
        self.sidebar.itemChosen.connect(self._on_menu)

    # -------------------------------------------------------------- menu
    def _on_menu(self, key: str):
        if key == "discord":
            webbrowser.open(DISCORD_URL)
        else:
            self.app.show_page(key)

    def resizeEvent(self, e):
        self.sidebar.fit()
        super().resizeEvent(e)

    # ---------------------------------------------------------- glass paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 30, 30)
        p.fillPath(path, QColor(10, 10, 13, 236))
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(255, 255, 255, 40))
        g.setColorAt(0.10, QColor(255, 255, 255, 8))
        g.setColorAt(1.0, QColor(0, 0, 0, 140))
        p.fillPath(path, QBrush(g))
        w = float(self.width())
        sheen = QRadialGradient(w * 0.18, 0.0, w * 0.85)
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

    # ------------------------------------------------------------- kéo cửa sổ
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        e.accept()

    def closeEvent(self, e):
        self.app.quit()
        e.accept()


class TetoApp:
    """App root: owns engine + hotkeys + every window (main, MIDI player, mini)."""

    def __init__(self, config: Config | None = None, keys: KeySim | None = None, intro: bool = False):
        self.qapp = QApplication.instance() or QApplication([sys.argv[0]] if sys.argv else ["tetoMIDI"])
        self.qapp.setApplicationName(APP_NAME)
        self.qapp.setStyle("Fusion")
        self.qapp.setStyleSheet(STYLE)

        self.cfg = config or Config()
        self.keys = keys or KeySim()
        self.consoles = {m: KeyConsole() for m in MODES}   # key history per instrument
        self.keys.add_listener(self._on_key_event)
        self.fake_sound = FakeKeySound(self.cfg)
        self.keys.add_listener(self.fake_sound.on_key)
        self.fake_sound.apply()
        self.transports = {m: Transport(create_dispatcher(m, ScopedKeys(self.keys, m), self.cfg), self.cfg, mode=m)
                           for m in MODES}
        self.macro_dispatcher = self.transports["piano"].dispatcher
        self.preview_sound = PianoSound(self.cfg)
        self.preview_dispatcher = PianoPreviewDispatcher(self.preview_sound, self.cfg)
        self.speed = {m: 1.0 for m in MODES}
        self.hotkeys = HotkeyManager()
        self.hotkeys.start()
        self.current: str | None = None
        self.last_player = "piano"
        self.midi = None       # MIDI player (playlist) window, created on first use
        self._mini = None      # mini player window, created on first use
        self.splash = None     # intro splash (only when intro=True)

        self.window = GlassWindow(self)
        self.pages = self.window.pages

        self.cfg.on_change(self._cfg_changed)
        self._apply_preview()
        self._bind_hotkeys()
        self.set_topmost(bool(self.cfg.get("app.topmost", False)), save=False)
        self.show_page("piano")
        self._apply_opacity()

        self._timer = QTimer()
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        if intro:
            self._run_intro()

    # ---------------------------------------------------------------- intro
    def _run_intro(self):
        logo = QPixmap(str(resource_path("assets/icons/app.png")))
        if logo.isNull():
            return
        from .intro import IntroSplash
        self.window.hide()
        self.splash = IntroSplash(logo)
        self.splash.reveal.connect(self._intro_reveal)
        self.splash.finished.connect(self._intro_done)
        self.splash.start()

    def _intro_reveal(self):
        self.window.show()
        self._apply_opacity()

    def _intro_done(self):
        self.splash = None

    # -------------------------------------------------------------- window
    def opacity(self) -> float:
        try:
            return min(max(float(self.cfg.get("app.opacity", 1.0)), MIN_OPACITY), 1.0)
        except (TypeError, ValueError):
            return 1.0

    def set_opacity(self, value: float):
        self.cfg.set("app.opacity", round(min(max(float(value), MIN_OPACITY), 1.0), 2))

    def _apply_opacity(self):
        if self.splash is not None:   # the intro still owns the window's visibility
            return
        for win in (self.window, self.midi):
            if win is not None:
                win.setWindowOpacity(self.opacity())

    def set_topmost(self, value: bool, save: bool = True):
        flag = Qt.WindowType.WindowStaysOnTopHint
        for win in (self.window, self.midi, self._mini):
            if win is not None:
                visible = win.isVisible()
                win.setWindowFlag(flag, bool(value))
                if visible:
                    win.show()
        if save:
            self.cfg.set("app.topmost", bool(value))

    # -------------------------------------------------- MIDI player window
    def midi_window(self):
        """The MIDI player (playlist) window, created on first use."""
        if self.midi is None:
            from .midi_player_window import MidiPlayerWindow
            self.midi = MidiPlayerWindow(self)
        return self.midi

    def show_midi_player(self):
        self.midi_window()
        self.midi.show()
        self.midi.raise_()
        self.midi.activateWindow()
        self._apply_opacity()
        self.midi.update_view()

    def midi_visible(self) -> bool:
        return self.midi is not None and self.midi.isVisible()

    def midi_owns(self, mode: str) -> bool:
        """True while the MIDI player window is open on this instrument (its page keeps playing)."""
        return self.midi_visible() and self.midi.mode == mode

    def song_finished(self, mode: str):
        if self.midi is not None and self.midi.mode == mode and self.midi_visible():
            self.midi.on_finished()

    # -------------------------------------------------------------- pages
    def show_page(self, name: str):
        if name == self.current:
            return
        old = self.pages.get(self.current)
        if isinstance(old, (PlayerPage, HubPage)):
            old.leave()   # never keep sending keys for a page that is no longer shown
        self.current = name
        if name in MODES:
            self.last_player = name
        page = self.pages[name]
        self.window.stack.setCurrentWidget(page)
        if isinstance(page, SettingsPage):
            page.refresh()
        else:
            page.update_view()
        if isinstance(page, HubPage):
            page.on_show()
        self.window.sub.setText(f"{PAGE_TITLES.get(name, name)} · {VERSION_LABEL}")

    @property
    def page(self):
        return self.pages.get(self.current)

    def player_page(self) -> PlayerPage | None:
        """The player page the mini player drives: the visible one, or the last instrument shown."""
        page = self.pages.get(self.current)
        if isinstance(page, PlayerPage):
            return page
        return self.pages.get(self.last_player)

    # --------------------------------------------------------------- speed
    def set_speed(self, mode: str, value: float):
        value = min(max(float(value), 0.1), 5.0)
        self.speed[mode] = value
        self.transports[mode].set_speed(value)

    # ------------------------------------------------------------- hotkeys
    def _bind_hotkeys(self):
        def current_player():   # the hub page answers the same hotkeys for its preview
            return self.page if isinstance(self.page, (PlayerPage, HubPage)) else None

        def call(method, *args):
            def run():
                if self.midi_visible():   # while the MIDI player window is open the hotkeys drive it
                    self.midi.hotkey(method, *args)
                    return
                p = current_player()
                if p:
                    getattr(p, method)(*args)
            return run

        hk = self.cfg.data["hotkeys"]
        self.hotkeys.set_bindings({
            hk["play"]: call("on_hotkey_play"),
            hk["pause"]: call("on_pause"),
            hk["stop"]: call("on_stop"),
            hk["speedup"]: call("change_speed", 1),
            hk["slowdown"]: call("change_speed", -1),
        })

    def rebind_hotkey(self, name: str):
        """Wait for the next key press and bind it to ``name`` (Esc cancels)."""
        if not self.hotkeys.capturing and self.hotkeys._listener is None:
            QMessageBox.information(self.window, "Hotkeys unavailable",
                                    f"Global hotkeys cannot start on this system.\n{self.hotkeys.error}")
            return
        for page in self.pages.values():
            chips = getattr(page, "_hot_chips", None)
            if chips and name in chips:
                chips[name].set_key("…")
        self.pages["settings"].show_chip_capturing(name)

        def done(key: str):
            current = self.cfg.get(f"hotkeys.{name}")
            if key == "esc":
                key = current
            clash = [n for n, k in self.cfg.data["hotkeys"].items() if k == key and n != name]
            if clash:
                QMessageBox.information(self.window, "Keybind conflict",
                                        f"“{key}” is already used for {clash[0]}.")
                key = current
            self.cfg.set(f"hotkeys.{name}", key)
            self._cfg_changed("hotkeys." + name)
            for page in self.pages.values():   # restore chip text if nothing changed
                chips = getattr(page, "_hot_chips", None)
                if chips:
                    chips[name].set_key(self.cfg.get(f"hotkeys.{name}", ""))
            self.pages["settings"]._cfg_changed("hotkeys.")

        self.hotkeys.capture_next(done)

    def _on_key_event(self, source, action: str, label: str):
        console = self.consoles.get(source)
        if console is not None:
            console.add(f"{action}: {label}")

    def _cfg_changed(self, path: str):
        if path.startswith("hotkeys.") or path == "*":
            self._bind_hotkeys()
        if path in ("app.opacity", "*"):
            self._apply_opacity()
        if path in ("piano.previewSound", "hub.useSoundfont", "hub.soundfont", "*"):
            self._apply_preview(reopen=path != "piano.previewSound")
        if path.startswith("fakeSound.") or path == "*":
            if path != "fakeSound.volume":   # the volume is read on every click
                self.fake_sound.apply()

    # ------------------------------------------------------- preview sound
    def _apply_preview(self, reopen: bool = False):
        """Preview sound on: the piano transport plays the MIDI as sound and presses no keys."""
        on = bool(self.cfg.get("piano.previewSound", False))
        t = self.transports["piano"]
        if on:
            if reopen or t.dispatcher is not self.preview_dispatcher or self.preview_sound._stream is None:
                self.preview_sound.apply()
            t.set_dispatcher(self.preview_dispatcher)
            page = self.pages.get("piano")
            if self.preview_sound.error and page is not None:
                page.set_status(f"⚠ No sound: {self.preview_sound.error}", "#e0a13a")
        else:
            t.set_dispatcher(self.macro_dispatcher)
            self.preview_sound.close()

    # ---------------------------------------------------------- mini player
    def show_mini(self):
        if self._mini is None:
            self._mini = MiniPlayer(self)
        self._mini.place_near_root()
        self._mini.show()
        self._mini.raise_()
        self.window.hide()          # the mini player replaces the main window on screen
        self._apply_opacity()
        self._mini.update_view()

    def hide_mini(self):
        if self._mini is not None:
            self._mini.hide()
        self.window.show()
        self._apply_opacity()

    def mini_visible(self) -> bool:
        return self._mini is not None and self._mini.isVisible()

    # ---------------------------------------------------------------- misc
    def reset_settings(self):
        for t in self.transports.values():
            t.stop()
        self.cfg.reset()
        self.speed = {m: 1.0 for m in MODES}
        for t in self.transports.values():
            t.set_speed(1.0)
        # build a fresh Settings page so every control shows the default values again
        old = self.pages["settings"]
        index = self.window.stack.indexOf(old)
        new = SettingsPage(self)
        self.window.stack.removeWidget(old)
        old.deleteLater()
        self.window.stack.insertWidget(index, new)
        self.pages["settings"] = new
        self.window.stack.setCurrentWidget(new)
        self.set_topmost(False, save=False)
        if self.midi is not None:
            self.midi.on_settings_reset()
        self.show_page("settings")

    def _tick(self):
        delay = TICK_MS
        try:
            self.hotkeys.drain()
            page = self.page
            if isinstance(page, (PlayerPage, HubPage)):
                page.update_view()
            if self.midi_visible():
                self.midi.update_view()
            if self.mini_visible():
                self._mini.update_view()
            if not (self.window.isVisible() or self.midi_visible() or self.mini_visible()):
                delay = IDLE_TICK_MS
        except Exception:
            log.exception("tick failed")
        if self._timer.interval() != delay:
            self._timer.setInterval(delay)

    def quit(self):
        for t in self.transports.values():
            try:
                t.stop()
            except Exception:
                log.exception("stopping transport")
        self.keys.release_all()
        try:
            self.pages["hub"].shutdown()
        except Exception:
            log.exception("hub shutdown")
        self.fake_sound.close()
        self.preview_sound.close()
        self.cfg.save()
        self.hotkeys.stop()
        self._timer.stop()
        for win in (self._mini, self.midi, self.window):
            if win is not None:
                try:
                    win.close()
                except Exception:
                    pass
        self.qapp.quit()

    def run(self):
        self.window.show()
        self._apply_opacity()
        self.qapp.exec()
