"""Piano-roll data model (no GUI): notes -> lanes, with a fast 'what is visible at time t' query.

The lane assignment uses the *same* mapping rules as the macro dispatchers (pitch/key offsets and
88/61-key range for the piano, drum lanes, guitar strings), so the
roll shows exactly the notes that will be pressed.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from .midi_data import PERCUSSION_CHANNEL, SongView
from .mappings import DRUM_LANE_LABELS, DRUM_NOTE_TO_LANE, GUITAR_STRING_LABELS, guitar_string_fret

SHORT_NOTE = 0.12   # length (s) of every note when "Note lengths" is off

PIANO_RANGE_88 = (21, 108)
PIANO_RANGE_61 = (36, 96)


@dataclass
class RollData:
    kind: str                       # 'piano' | 'drums' | 'guitar'
    starts: list[float] = field(default_factory=list)
    ends: list[float] = field(default_factory=list)
    lanes: list[int] = field(default_factory=list)    # MIDI pitch
    vels: list[int] = field(default_factory=list)
    prefix_end: list[float] = field(default_factory=list)
    key_range: tuple[int, int] = PIANO_RANGE_88

    def finish(self) -> "RollData":
        best = 0.0
        self.prefix_end = []
        for e in self.ends:
            best = max(best, e)
            self.prefix_end.append(best)
        return self

    def __len__(self) -> int:
        return len(self.starts)

    def window(self, pos: float, look: float) -> tuple[int, int]:
        """Index range [lo, hi) that may be visible between ``pos`` and ``pos + look``."""
        lo = bisect.bisect_right(self.prefix_end, pos)
        hi = bisect.bisect_left(self.starts, pos + look)
        return lo, max(lo, hi)

    def _add(self, n, lane: int, uniform: bool = False) -> None:
        self.starts.append(n.start)
        self.ends.append(n.start + SHORT_NOTE if uniform else n.end)
        self.lanes.append(lane)
        self.vels.append(n.velocity)


def build_piano(view: SongView | None, piano_cfg: dict) -> RollData:
    lo, hi = PIANO_RANGE_88 if piano_cfg.get("88Keys", True) else PIANO_RANGE_61
    data = RollData("piano", key_range=(lo, hi))
    uniform = not piano_cfg.get("noteLengths", True)
    if view:
        shift = piano_cfg.get("pitchOffset", 0) + piano_cfg.get("transposeOffset", 0)
        for n in view.notes:
            pitch = n.note + shift
            if lo <= pitch <= hi:
                data._add(n, pitch, uniform=uniform)
    return data.finish()


def build_drums(view: SongView | None, drums_cfg: dict) -> RollData:
    """Drum pads: one lane per nanoMIDI drum group, percussion channel only."""
    data = RollData("drums", key_range=(0, len(DRUM_LANE_LABELS) - 1))
    uniform = not drums_cfg.get("noteLengths", True)
    if view:
        for n in view.notes:
            if n.channel != PERCUSSION_CHANNEL:
                continue
            lane = DRUM_NOTE_TO_LANE.get(n.note)
            if lane is not None:
                data._add(n, lane, uniform=uniform)
    return data.finish()


def build_guitar(view: SongView | None, guitar_cfg: dict) -> RollData:
    """Guitar strings: one lane per string (E A D G B e), each note on its lowest usable fret."""
    data = RollData("guitar", key_range=(0, len(GUITAR_STRING_LABELS) - 1))
    uniform = not guitar_cfg.get("noteLengths", True)
    if view:
        for n in view.notes:
            sf = guitar_string_fret(n.note)
            if sf is not None:
                data._add(n, sf[0], uniform=uniform)
    return data.finish()


def build_roll(mode: str, view: SongView | None, mode_cfg: dict) -> RollData:
    if mode == "drums":
        return build_drums(view, mode_cfg)
    if mode == "guitar":
        return build_guitar(view, mode_cfg)
    return build_piano(view, mode_cfg)
