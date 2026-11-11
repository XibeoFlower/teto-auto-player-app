"""Note <-> name helpers shared by the macro engine and the piano-roll view."""

from __future__ import annotations

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(note: int) -> str:
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def is_black(note: int) -> bool:
    return note % 12 in (1, 3, 6, 8, 10)


# --------------------------------------------------------------------- drums
# Key map + note names carried over unchanged from nanoMIDIPlayer (identical in v1.3, re-added in v1.5).
DRUM_LANES = [
    ("Kick", (35, 36)),
    ("Snare", (38, 40, 37)),
    ("Hi-hat", (42, 44)),
    ("Open", (46,)),
    ("Tom hi", (48, 50, 60, 62)),
    ("Tom lo", (45, 47)),
    ("Crash", (49, 55, 52, 57)),
    ("Ride", (51, 53)),
    ("Bell", (39,)),
]

DRUM_NOTE_TO_LANE = {note: i for i, (_label, notes) in enumerate(DRUM_LANES) for note in notes}
DRUM_LANE_LABELS = tuple(label for label, _notes in DRUM_LANES)


# -------------------------------------------------------------------- guitar
GUITAR_OPEN_STRINGS = (40, 45, 50, 55, 59, 64)   # E2 A2 D3 G3 B3 E4 (low -> high)
GUITAR_STRING_LABELS = ("E", "A", "D", "G", "B", "e")
GUITAR_MAX_FRET = 15
GUITAR_RANGE = (21, 108)   # outside this range notes fold back in by whole octaves


def fold_into_range(note: int, low: int, high: int) -> int:
    if high - low < 11:
        return note
    while note < low:
        note += 12
    while note > high:
        note -= 12
    return note


def guitar_string_fret(note: int) -> tuple[int, int] | None:
    """(string index 0-5 low->high, fret) of the lowest fret on the highest usable string, or None."""
    best: tuple[int, int] | None = None
    for s, open_pitch in enumerate(GUITAR_OPEN_STRINGS):
        fret = note - open_pitch
        if 0 <= fret <= GUITAR_MAX_FRET:
            if best is None or fret < best[1] or (fret == best[1] and s > best[0]):
                best = (s, fret)
    return best
