"""Macro dispatchers: turn MIDI note events into simulated key presses.

``PianoDispatcher`` (same key map, shift/ctrl layering for the 61/88-key layouts, velocity
via ALT+key, sustain via SPACE, finger limit, custom hold length, random transpose).
"""

from __future__ import annotations

import logging
import random
import re
import threading

from ..config import Config
from ..defaults_maps import DRUM_NOTE_TO_NAME, DRUMS_MAP, PIANO_MAP
from ..keysim import KeySim
from ..mappings import GUITAR_RANGE, fold_into_range
from ..rollmodel import SHORT_NOTE

# The guitar uses the piano layout: 61-key map + the 88-key CTRL layer, flattened to one table.
GUITAR_KEYMAP = {
    **{str(k): v for k, v in PIANO_MAP["61keyMap"].items()},
    **{str(k): v for k, v in PIANO_MAP["88keyMap"]["lowNotes"].items()},
    **{str(k): v for k, v in PIANO_MAP["88keyMap"]["highNotes"].items()},
}

log = logging.getLogger(__name__)

_SHIFTED_SYMBOLS = re.compile(r"[!@$%^*(]")


class Dispatcher:
    """Base class: finger limit, custom hold length and bookkeeping shared by all instruments."""

    mode = ""

    def __init__(self, keys: KeySim, cfg: Config):
        self.keys = keys
        self.cfg = cfg
        self._held_count = 0
        self._timers: list[threading.Timer] = []
        self._lock = threading.RLock()

    @property
    def c(self) -> dict:
        return self.cfg.data[self.mode]

    # -- interface used by Transport ---------------------------------
    def note_on(self, note: int, velocity: int, channel: int) -> None:
        raise NotImplementedError

    def note_off(self, note: int, channel: int) -> None:
        raise NotImplementedError

    def control(self, control: int, value: int) -> None:
        pass

    def release_all(self) -> None:
        with self._lock:
            for t in self._timers:
                t.cancel()
            self._timers.clear()
            self._held_count = 0
        self.keys.release_all()

    # -- helpers ------------------------------------------------------
    def _press_and_maybe_release(self, key: str) -> None:
        with self._lock:
            limit = int(self.c.get("fingerLimit", 11))
            if limit <= 10 and self._held_count >= limit:
                return  # finger limit reached: skip the note
            self._held_count += 1
        self.keys.press(key)
        hold = self.c.get("customHoldLength", {})
        if hold.get("enabled"):
            length = float(hold.get("noteLength", 0.1))
        elif not self.c.get("noteLengths", True):
            length = SHORT_NOTE   # "Note lengths" off: every key is tapped for the same short time
        else:
            return
        def _release():
            self.keys.release(key)
            with self._lock:
                self._held_count = max(0, self._held_count - 1)

        timer = threading.Timer(length, _release)
        timer.daemon = True
        with self._lock:
            self._timers = [t for t in self._timers if t.is_alive()]
            self._timers.append(timer)
        timer.start()

    def _note_released(self) -> None:
        with self._lock:
            self._held_count = max(0, self._held_count - 1)


class PianoDispatcher(Dispatcher):
    mode = "piano"

    def __init__(self, keys: KeySim, cfg: Config):
        super().__init__(keys, cfg)
        self.sustain_active = False
        self._transposed: dict[int, list[int]] = {}

    # -- mapping -------------------------------------------------------
    def resolve(self, note: int) -> tuple[int, str] | None:
        """Note (after pitch/key offsets) and the key it maps to, or None when out of range."""
        c = self.c
        note = note + c.get("pitchOffset", 0) + c.get("transposeOffset", 0)
        pm = c["pianoMap"]
        s = str(note)
        letter = pm["61keyMap"]
        if s in letter:
            return note, letter[s]
        if c.get("88Keys", True):
            if s in pm["88keyMap"]["lowNotes"]:
                return note, pm["88keyMap"]["lowNotes"][s]
            if s in pm["88keyMap"]["highNotes"]:
                return note, pm["88keyMap"]["highNotes"][s]
        return None

    def velocity_key(self, velocity: int) -> str:
        vmap = self.c["pianoMap"]["velocityMap"]
        thresholds = sorted(int(k) for k in vmap)
        lo, hi, idx = 0, len(thresholds) - 1, 0
        while lo <= hi:  # same search as nanoMIDIPlayer (kept for identical velocity buckets)
            idx = (lo + hi) // 2
            if idx == 0 or idx == len(thresholds) - 1:
                break
            if thresholds[idx] < velocity:
                lo = idx + 1
            else:
                hi = idx - 1
        return vmap[str(thresholds[idx])]

    # -- events --------------------------------------------------------
    def note_on(self, note, velocity, channel):
        c = self.c
        rf = c.get("randomFail", {})
        if rf.get("enabled") and random.random() < rf.get("transpose", 0) / 100:
            new_note = note + random.randint(-12, 12)
            self._transposed.setdefault(note, []).append(new_note)
            note = new_note
        resolved = self.resolve(note)
        if resolved is None:
            return
        note, key = resolved
        letter = c["pianoMap"]["61keyMap"]

        if c.get("velocity"):
            vk = self.velocity_key(velocity)
            self.keys.press("alt")
            self.keys.press(vk)
            self.keys.release(vk)
            self.keys.release("alt")

        if 36 <= note <= 96:
            symbol = bool(_SHIFTED_SYMBOLS.search(key))
            base = letter.get(str(note - 1), key.lower()) if symbol else None
            if c.get("noDoubles", True):
                self.keys.release(base if symbol else key.lower())
            if symbol:
                self.keys.press("shift")
                self._press_and_maybe_release(base)
                self.keys.release("shift")
            elif key.isupper():
                self.keys.press("shift")
                self._press_and_maybe_release(key.lower())
                self.keys.release("shift")
            else:
                self._press_and_maybe_release(key)
        else:  # extended 88-key range: CTRL layer
            self.keys.release(key.lower())
            self.keys.press("ctrl")
            self._press_and_maybe_release(key.lower())
            self.keys.release("ctrl")

    def note_off(self, note, channel):
        queue = self._transposed.get(note)
        if queue:  # this note was randomly transposed when it started: release the shifted one
            mapped = queue.pop(0)
            if not queue:
                del self._transposed[note]
            note = mapped
        resolved = self.resolve(note)
        if resolved is None:
            return
        note, key = resolved
        letter = self.c["pianoMap"]["61keyMap"]
        if 36 <= note <= 96 and _SHIFTED_SYMBOLS.search(key):
            self.keys.release(letter.get(str(note - 1), key.lower()))
        else:
            self.keys.release(key.lower())
        self._note_released()

    def control(self, control, value):
        if control != 64 or not self.c.get("sustain"):
            return
        cutoff = self.c.get("sustainCutoff", 63)
        if not self.sustain_active and value > cutoff:
            self.sustain_active = True
            self.keys.press("space")
        elif self.sustain_active and value < cutoff:
            self.sustain_active = False
            self.keys.release("space")

    def release_all(self):
        self.sustain_active = False
        self._transposed.clear()
        super().release_all()


def create_dispatcher(mode: str, keys: KeySim, cfg: Config) -> Dispatcher:
    if mode == "drums":
        return DrumDispatcher(keys, cfg)
    if mode == "guitar":
        return GuitarDispatcher(keys, cfg)
    return PianoDispatcher(keys, cfg)


class DrumDispatcher(Dispatcher):
    """Drum macro: the nanoMIDI 21-hit layout, one key per drum (see ``defaults_maps.DRUMS_MAP``)."""

    mode = "drums"

    def resolve(self, note: int) -> str | None:
        name = DRUM_NOTE_TO_NAME.get(note)
        return DRUMS_MAP.get(name) if name else None

    def note_on(self, note, velocity, channel):
        key = self.resolve(note)
        if not key:
            return
        self.keys.release(key)   # a second hit while the key is down: re-press it
        self._press_and_maybe_release(key)

    def note_off(self, note, channel):
        key = self.resolve(note)
        if key:
            self.keys.release(key)
        self._note_released()

    def release_all(self):
        super().release_all()


class GuitarDispatcher(Dispatcher):
    """Guitar macro: the same keyboard layout as the piano (61 keys + CTRL layer for 21-35 / 97-108,
    notes outside 21-108 fold back in by whole octaves — identical to the nanoMIDI guitar)."""

    mode = "guitar"

    def __init__(self, keys: KeySim, cfg: Config):
        super().__init__(keys, cfg)
        self._folded: dict[int, list[int]] = {}

    def resolve(self, note: int) -> tuple[int, str] | None:
        key = GUITAR_KEYMAP.get(str(note))
        if key:
            return note, key
        folded = fold_into_range(note, *GUITAR_RANGE)
        key = GUITAR_KEYMAP.get(str(folded))
        if key:
            return folded, key
        return None

    def note_on(self, note, velocity, channel):
        resolved = self.resolve(note)
        if resolved is None:
            return
        note, key = resolved
        if 36 <= note <= 96:
            symbol = bool(_SHIFTED_SYMBOLS.search(key))
            if symbol:
                base = PIANO_MAP["61keyMap"].get(str(note - 1), key.lower())
                if self.c.get("noDoubles", True):
                    self.keys.release(base)
                self.keys.press("shift")
                self._press_and_maybe_release(base)
                self.keys.release("shift")
            elif key.isupper():
                base = key.lower()
                if self.c.get("noDoubles", True):
                    self.keys.release(base)
                self.keys.press("shift")
                self._press_and_maybe_release(base)
                self.keys.release("shift")
            else:
                if self.c.get("noDoubles", True):
                    self.keys.release(key)
                self._press_and_maybe_release(key)
        else:   # extended range: CTRL layer
            self.keys.release(key.lower())
            self.keys.press("ctrl")
            self._press_and_maybe_release(key.lower())
            self.keys.release("ctrl")

    def note_off(self, note, channel):
        resolved = self.resolve(note)
        if resolved is None:
            return
        note, key = resolved
        if 36 <= note <= 96 and _SHIFTED_SYMBOLS.search(key):
            self.keys.release(PIANO_MAP["61keyMap"].get(str(note - 1), key.lower()))
        else:
            self.keys.release(key.lower())
        self._note_released()

    def release_all(self):
        self._folded.clear()
        super().release_all()
