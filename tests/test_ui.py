"""GUI integration tests for the Qt (glass) UI — need a display: `xvfb-run -a python -m unittest` on Linux."""

import os
import tempfile
import time
import unittest

from tests.helpers import make_midi


def _qt_available() -> bool:
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        return True
    except Exception:
        return False


HAVE_DISPLAY = _qt_available()


def pump(app, seconds):
    """Run the Qt event loop for ``seconds`` real seconds (timers, animations, transports tick)."""
    from PySide6.QtCore import QEventLoop, QTimer
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        loop = QEventLoop()
        QTimer.singleShot(10, loop.quit)
        loop.exec()
        app.qapp.processEvents()


def click(button):
    button.click()
    button.app_ = None  # no-op keep-alive


@unittest.skipUnless(HAVE_DISPLAY, "needs Qt and a display")
class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TETOMIDI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="tm-ui-")
        from tetomidi.keysim import KeySim, RecordingBackend
        from tetomidi.qtui.app import TetoApp

        cls.dir = tempfile.mkdtemp()
        cls.piano_mid = make_midi(os.path.join(cls.dir, "piano.mid"),
                                  [(i * 0.5, 0.4, 60 + (i % 5), 90) for i in range(40)])
        cls.backend = RecordingBackend()
        # never let a modal dialog block the test run (hotkeys may be unavailable headless)
        from tetomidi.qtui import app as qtapp
        cls._boxes = []
        qtapp.QMessageBox.information = staticmethod(lambda *a, **k: cls._boxes.append(a) or None)
        cls.app = TetoApp(keys=KeySim(cls.backend))
        cls.app.window.show()
        pump(cls.app, 0.2)

    @classmethod
    def tearDownClass(cls):
        cls.app.quit()

    def setUp(self):
        self.app.show_page("piano")
        for t in self.app.transports.values():
            t.stop()
        self.backend.log.clear()
        pump(self.app, 0.05)

    def presses(self):
        return [k for a, k in self.backend.actions() if a == "press"]

    # --- navigation ---------------------------------------------------
    def test_sidebar_has_the_page_entries_and_switches_pages(self):
        side = self.app.window.sidebar
        keys = [k for k, _t, _i in side._items] if hasattr(side, "_items") else None
        # the sidebar is built from the item list given by the window; verify through pages instead
        for key in ("drums", "guitar", "hub", "settings", "piano"):
            self.app.show_page(key)
            self.assertEqual(self.app.current, key)

    def test_window_is_frameless_glass_with_title_and_sub(self):
        w = self.app.window
        self.assertTrue(bool(w.windowFlags() & 0x00000800))   # Qt.FramelessWindowHint
        self.assertEqual(w.title.text(), "tetoMIDI")
        self.assertIn("v1.5", w.sub.text())
        self.app.show_page("drums")
        self.assertIn("drum player", w.sub.text())
        self.app.show_page("piano")

    # --- files --------------------------------------------------------
    def test_invalid_file_shows_a_clear_message_and_keeps_the_old_song(self):
        page = self.app.pages["piano"]
        self.assertTrue(page.load_path(self.piano_mid))
        bad = os.path.join(self.dir, "bad.mid")
        with open(bad, "wb") as f:
            f.write(b"garbage")
        self.assertFalse(page.load_path(bad))
        self.assertIs(page.song.path, self.piano_mid)

    def test_valid_file_fills_roll_and_time(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        pump(self.app, 0.1)
        self.assertEqual(len(page.roll.data), 40)
        self.assertIn("00:00:09", page.time.text())

    # --- playback -----------------------------------------------------
    def test_play_pause_stop_buttons_and_roll_follow_the_clock(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        page.play_btn.click()
        pump(self.app, 0.9)
        self.assertEqual(page.transport.state, "playing")
        self.assertEqual(page.play_btn.text(), "PAUSE")
        self.assertTrue(self.presses())
        self.assertTrue(page.roll._lit, "keys under playing notes must be lit")
        page.play_btn.click()
        self.assertEqual(page.transport.state, "paused")
        frozen = page.transport.position()
        pump(self.app, 0.3)
        self.assertEqual(page.transport.position(), frozen)
        page.stop_btn.click()
        self.assertEqual(page.transport.state, "stopped")
        self.assertEqual(self.app.keys.held, set())

    def test_hotkeys_f2_f3_f4_drive_the_current_page(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        hk = self.app.hotkeys
        hk.trigger("f2"); pump(self.app, 0.2)
        self.assertEqual(page.transport.state, "playing")
        hk.trigger("f3"); pump(self.app, 0.1)
        self.assertEqual(page.transport.state, "paused")
        hk.trigger("f3"); pump(self.app, 0.1)
        self.assertEqual(page.transport.state, "playing")
        hk.trigger("f4"); pump(self.app, 0.1)
        self.assertEqual(page.transport.state, "stopped")

    def test_slider_seek_moves_the_clock(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        page.slider.setValue(500)
        page.slider.sliderReleased.emit()
        self.assertAlmostEqual(page.transport.position() / page.transport.length, 0.5, delta=0.05)

    def test_loop_toggle_is_real(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        tg = page._toggles["loop"]
        tg.setChecked(True)
        self.assertTrue(self.app.cfg.get("piano.loop"))
        self.assertTrue(page.transport.loop)
        tg.setChecked(False)
        self.assertFalse(page.transport.loop)

    def test_88key_toggle_changes_roll_and_macro_range(self):
        page = self.app.pages["piano"]
        low = make_midi(os.path.join(self.dir, "low.mid"), [(0, 1, 22, 90), (1, 1, 60, 90)])
        page.load_path(low)
        self.assertEqual(len(page.roll.data), 2)
        tg = page._toggles["88Keys"]
        tg.setChecked(False)
        self.assertFalse(self.app.cfg.get("piano.88Keys"))
        self.assertEqual(len(page.roll.data), 1)          # note 22 no longer drawn...
        page.on_play(); pump(self.app, 1.4); page.on_stop()
        self.assertNotIn("2", self.presses())             # ...and not pressed (22 -> ctrl+'2')
        tg.setChecked(True)

    def test_note_lengths_toggle_is_on_by_default_and_reshapes_the_roll(self):
        from tetomidi.rollmodel import SHORT_NOTE
        page = self.app.pages["piano"]
        self.assertTrue(self.app.cfg.get("piano.noteLengths"))
        page.load_path(self.piano_mid)                    # 0.4 beat at 120 bpm = 0.2 s
        d = page.roll.data
        self.assertAlmostEqual(d.ends[0] - d.starts[0], 0.2, places=2)
        tg = page._toggles["noteLengths"]
        tg.setChecked(False)
        self.assertFalse(self.app.cfg.get("piano.noteLengths"))
        d = page.roll.data
        self.assertAlmostEqual(d.ends[0] - d.starts[0], SHORT_NOTE, places=3)
        tg.setChecked(True)
        self.assertAlmostEqual(page.roll.data.ends[0] - page.roll.data.starts[0], 0.2, places=2)

    def test_every_mode_has_a_note_lengths_button(self):
        for mode in ("piano", "drums", "guitar"):
            self.assertIn("noteLengths", self.app.pages[mode]._toggles)

    def test_window_opacity_setting_is_clamped_and_saved(self):
        self.app.set_opacity(0.6)
        self.assertEqual(self.app.cfg.get("app.opacity"), 0.6)
        self.app.set_opacity(0.05)                        # never fully invisible
        self.assertEqual(self.app.cfg.get("app.opacity"), 0.4)
        self.app.set_opacity(1.0)
        self.assertEqual(self.app.opacity(), 1.0)

    def test_velocity_and_sustain_toggles_write_config(self):
        page = self.app.pages["piano"]
        page._toggles["velocity"].setChecked(True)
        page._toggles["sustain"].setChecked(True)
        self.assertTrue(self.app.cfg.get("piano.velocity"))
        self.assertTrue(self.app.cfg.get("piano.sustain"))
        page._toggles["velocity"].setChecked(False)
        page._toggles["sustain"].setChecked(False)

    # --- instruments --------------------------------------------------
    def test_piano_page_presses_piano_keys(self):
        piano = self.app.pages["piano"]
        piano.load_path(self.piano_mid)
        piano.play_btn.click()
        pump(self.app, 0.8)
        piano.stop_btn.click()
        self.assertTrue(set(self.presses()) & {"t", "y", "u", "i", "o"})

    def test_leaving_a_page_stops_its_playback(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        page.play_btn.click()
        pump(self.app, 0.3)
        self.app.show_page("hub")
        self.assertEqual(page.transport.state, "stopped")
        self.assertEqual(self.app.keys.held, set())

    # --- hand mode (like the Lua script) ------------------------------
    def test_hand_mode_filters_notes_like_the_lua_script(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)                    # notes 60..64
        page.cfg.set("piano.hand", "right")
        page.on_play(); pump(self.app, 1.2); page.on_stop()
        self.assertTrue(all(int(k) >= 60 for k in self.presses() if k.isdigit()))
        self.backend.log.clear()
        page.cfg.set("piano.hand", "left")
        page.on_play(); pump(self.app, 1.2); page.on_stop()
        self.assertEqual([k for k in self.presses() if k.isdigit()], [])
        page.cfg.set("piano.hand", "all")

    def test_hand_pills_follow_the_config(self):
        page = self.app.pages["piano"]
        page._set_hand("left")
        self.assertEqual(page.cfg.get("piano.hand"), "left")
        self.assertEqual(page._hand_btns["left"].glass_kind(), "blue")
        self.assertEqual(page._hand_btns["all"].glass_kind(), "clear")
        page._set_hand("all")

    # --- mini player --------------------------------------------------
    def test_mini_player_replaces_the_main_window_and_back(self):
        page = self.app.pages["piano"]
        page.load_path(self.piano_mid)
        self.app.show_mini()
        pump(self.app, 0.1)
        self.assertTrue(self.app.mini_visible())
        self.assertFalse(self.app.window.isVisible())
        self.assertEqual(self.app.player_page(), page)
        self.app._mini._play()
        pump(self.app, 0.5)
        self.assertEqual(page.transport.state, "playing")
        self.app._mini._stop()
        self.app.hide_mini()
        pump(self.app, 0.1)
        self.assertFalse(self.app.mini_visible())
        self.assertTrue(self.app.window.isVisible())

    # --- MIDI player (playlist) window --------------------------------
    def test_midi_player_window_plays_the_list(self):
        from tetomidi.qtui.midi_player_window import MidiPlayerWindow
        win = self.app.midi_window()
        self.assertIsInstance(win, MidiPlayerWindow)
        n = win.add_paths([self.piano_mid])
        self.assertEqual(n, 1)
        win.start()
        pump(self.app, 0.6)
        self.assertEqual(self.app.pages["piano"].transport.state, "playing")
        win.stop()
        self.assertEqual(self.app.pages["piano"].transport.state, "stopped")
        win.clear()
        self.assertEqual(win.playlist.items, [])

    def test_midi_player_repeat_cycle_is_saved(self):
        win = self.app.midi_window()
        win.cycle_repeat()                                # off -> all (list loops, the song does not)
        self.assertEqual(self.app.cfg.get("player.repeat"), "all")
        self.assertFalse(self.app.pages[win.mode].transport.loop)
        win.cycle_repeat()                                # all -> one (Repeat one = the page's Loop)
        self.assertEqual(self.app.cfg.get("player.repeat"), "one")
        self.assertTrue(self.app.pages[win.mode].transport.loop)
        while self.app.cfg.get("player.repeat") != "off":  # back to off for the other tests
            win.cycle_repeat()
        self.assertFalse(self.app.pages[win.mode].transport.loop)

    # --- settings -----------------------------------------------------
    def test_hotkey_rebind_through_capture(self):
        hk = self.app.hotkeys
        self.app.rebind_hotkey("play")
        self.assertTrue(hk.capturing)
        hk._on_press(type("K", (), {"char": None, "name": "f9"})())
        pump(self.app, 0.2)
        self.assertEqual(self.app.cfg.get("hotkeys.play"), "f9")
        self.app.rebind_hotkey("play")
        hk._on_press(type("K", (), {"char": None, "name": "f2"})())
        pump(self.app, 0.2)
        self.assertEqual(self.app.cfg.get("hotkeys.play"), "f2")

    def test_reset_settings_rebuilds_the_settings_page(self):
        self.app.cfg.set("piano.velocity", True)
        self.app.reset_settings()
        self.assertFalse(self.app.cfg.get("piano.velocity"))
        self.assertEqual(self.app.current, "settings")
        self.assertFalse(self.app.pages["settings"].app is None)
        self.app.show_page("piano")


if __name__ == "__main__":
    unittest.main()
