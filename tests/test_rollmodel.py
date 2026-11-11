import os
import tempfile
import unittest

from tetomidi.midi_data import load_song
from tetomidi.rollmodel import build_piano
from tests.helpers import make_cfg, make_midi


class RollModelTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = make_cfg()

    def song(self, notes, **kw):
        return load_song(make_midi(os.path.join(self.dir, "r.mid"), notes, **kw))

    def test_piano_roll_applies_offsets_and_key_range(self):
        song = self.song([(0, 1, 60, 80), (1, 1, 22, 80), (2, 1, 100, 80)])
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual(sorted(data.lanes), [22, 60, 100])
        self.cfg.set("piano.88Keys", False)
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual(data.lanes, [60])                      # 22 and 100 are outside the 61-key map
        self.cfg.set("piano.pitchOffset", -12)                   # 60 -> 48, 100 -> 88 (both inside 36..96)
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual(sorted(data.lanes), [48, 88])

    def test_note_lengths_off_makes_every_note_short_and_equal(self):
        from tetomidi.rollmodel import SHORT_NOTE
        # make_midi takes beats; at the default 120 bpm one beat is 0.5 s, so these are 1.0 s, 0.25 s and 0.5 s
        song = self.song([(0, 2.0, 60, 80), (3, 0.5, 62, 80), (5, 1.0, 64, 80)])
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual([round(e - s, 3) for s, e in zip(data.starts, data.ends)], [1.0, 0.25, 0.5])
        self.cfg.set("piano.noteLengths", False)
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual([round(s, 3) for s in data.starts], [0.0, 1.5, 2.5])
        self.assertEqual({round(e - s, 3) for s, e in zip(data.starts, data.ends)}, {SHORT_NOTE})

    def test_piano_roll_matches_macro_mapping_with_offset(self):
        song = self.song([(0, 1, 100, 80)])
        self.cfg.set("piano.88Keys", False)
        self.cfg.set("piano.pitchOffset", -12)
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        self.assertEqual(data.lanes, [88])

    def test_window_finds_visible_notes_including_long_ones(self):
        song = self.song([(0, 8, 60, 80), (1, 0.5, 62, 80), (6, 0.5, 64, 80)])   # 120 bpm: 4s, .5s, 3s
        data = build_piano(song.view("piano"), self.cfg.data["piano"])
        lo, hi = data.window(pos=2.0, look=1.0)                 # 2.0..3.0 s
        visible = [i for i in range(lo, hi) if data.ends[i] > 2.0]
        self.assertEqual([data.lanes[i] for i in visible], [60])
        lo, hi = data.window(pos=2.5, look=1.0)                 # 2.5..3.5: 64 starts at 3.0
        visible = sorted(data.lanes[i] for i in range(lo, hi) if data.ends[i] > 2.5)
        self.assertEqual(visible, [60, 64])


if __name__ == "__main__":
    unittest.main()
