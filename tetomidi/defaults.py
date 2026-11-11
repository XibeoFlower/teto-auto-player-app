"""Default configuration for tetoMIDI."""

from __future__ import annotations

import copy

from .defaults_maps import PIANO_MAP


def _common(**extra):
    base = {
        "currentFile": "",
        "loop": False,
        "noteLengths": True,   # off: every note is short and the same length (roll and key presses)
        "releaseOnPause": True,
        "customHoldLength": {"enabled": False, "noteLength": 0.1},
        "fingerLimit": 11,  # 11 = unlimited (same convention as nanoMIDIPlayer)
        "randomFail": {"enabled": False, "speed": 5.0},
    }
    base.update(extra)
    return base


DEFAULTS = {
    "hotkeys": {"play": "f2", "pause": "f3", "stop": "f4", "speedup": "f5", "slowdown": "f6"},
    "app": {"topmost": False, "speedStep": 5, "opacity": 1.0},
    "player": {"playlist": [], "index": -1, "repeat": "off", "shuffle": False, "mode": "piano"},
    "mini": {"console": True},
    # MIDI Hub: server address ("" = the built-in HUB_API_URL); preview sound = piano SoundFont (hub.soundfont:
    # path of an .sf2, "" = the bundled assets/sounds/Piano.sf2) or, when off, the synthesised piano
    "hub": {"apiUrl": "", "useSoundfont": True, "soundfont": ""},
    # fake keyboard sound: a typing click per key press, sent to an audio device (e.g. a virtual cable -> Roblox mic)
    "fakeSound": {"enabled": False, "volume": 80, "device": "", "alsoSpeakers": False},
    "roll": {"fallSeconds": 3.0, "glow": True, "keyLabels": True, "noteColor": "blue",
             "mode3d": False,   # off: flat 2D roll (default) / on: 3D roll with the perspective floor
             "background": "", "backgroundDim": 50},   # background: copied image file ("" = plain colour)
    "piano": _common(
        **{
            "hand": "all",   # all / left / right: which hand plays (split at C4, like the Lua script)
            "88Keys": True,
            "previewSound": False,   # on: Play sounds the MIDI as piano and presses no keys (no macro)
            "sustain": False,
            "velocity": False,
            "noDoubles": True,
            "sustainCutoff": 63,
            "pitchOffset": 0,
            "transposeOffset": 0,
            "skipPercussion": True,
            "randomFail": {"enabled": False, "speed": 5.0, "transpose": 5.0},
            "pianoMap": PIANO_MAP,
        }
    ),
    # Drums: the nanoMIDI 21-hit layout, one key per drum (see defaults_maps.DRUMS_MAP).
    "drums": _common(
        **{
            "randomFail": {"enabled": False, "speed": 5.0, "transpose": 5.0},
        }
    ),
    # Guitar: plays the same computer-keyboard layout as the piano (61 keys + CTRL layer).
    "guitar": _common(
        **{
            "skipPercussion": True,
            "randomFail": {"enabled": False, "speed": 5.0, "transpose": 5.0},
        }
    ),
}


def fresh_defaults() -> dict:
    return copy.deepcopy(DEFAULTS)
