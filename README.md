<div align="center">

# tetoMIDI player

**MIDI macro player with a falling-note piano roll**

Load a `.mid` file and let tetoMIDI press the keyboard keys for you, while a falling-note roll shows what is being played.

[![Version](https://img.shields.io/badge/version-1.5.0-blue)](#)
[![License](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-join%20us-5865F2?logo=discord&logoColor=white)](https://discord.gg/peaqm6uqgB)

**Image Preview**

<img width="984" height="1320" alt="tetoMIDI-readmes-preview-player" src="https://github.com/user-attachments/assets/26845a42-bd9b-4243-a3d7-f927c11c038c" />

</div>

---

## What is tetoMIDI?

tetoMIDI is a desktop app (Python 3 + PySide6/Qt) that reads a MIDI file and **presses the matching keys on your computer keyboard** — a piano macro player. It also draws a Synthesia-style piano roll so you can follow the song.

By default it makes no sound of its own: it only sends key presses. If you want to hear the song, turn on **Preview sound** (see below).

The interface uses a dark "liquid glass" design with rounded corners, a sliding sidebar and an intro animation.

## Features

- **Piano, Drums and Guitar pages** — each with its own falling-note roll.
  - Piano: 61 or 88 keys, Shift symbols, Ctrl layer, velocity, sustain.
  - Drums: 21-hit map (Kick, Snare, Hi-hat, Open, Tom, Crash, Ride, Bell…).
  - Guitar: six strings (E A D G B e) on the piano key layout.
- **Falling-note piano roll**
  - **2D / 3D roll** switch (3D = perspective floor).
  - **Note colors**: Classic or Rainbow (Synthesia style).
  - **Key letters** printed on every piano key (keys played with Ctrl are blue).
  - **Custom background image** (JPG, PNG, GIF) with adjustable darkness.
- **Hand mode** — play everything, only the left hand or only the right hand (split at C4).
- **MIDI Player window** — playlist (add files or a whole folder), PREV / PLAY / STOP / NEXT, seek bar, repeat (off / all / one), shuffle and speed. The playlist is saved between runs.
- **Mini player** — a small always-on-top, title-bar-free window with transport buttons, song position and a **console** that lists the key presses being sent. Drag it from any empty spot.
- **Preview sound** — play the song as a piano (SoundFont or built-in synth) instead of pressing keys.
- **Fake keyboard sound** — optional typing-click sound per key press, sent to an audio device of your choice.
- **MIDI Hub** page.
- **Global hotkeys**, rebindable in Settings.
- Settings for playback options, window opacity, always-on-top and reset.

## Hotkeys

| Action | Default key |
|---|---|
| Play | `F2` |
| Pause | `F3` |
| Stop | `F4` |
| Speed up | `F5` |
| Slow down | `F6` |

All of them can be changed in **Settings**.

## Getting started

### Windows (easiest)

1. Extract the zip.
2. Open the `njsjs-main` folder and double-click **`START-tetoMIDI-WINDOWS.bat`**.
3. On the first run it installs the required libraries (internet needed). After that, just double-click it again.

You need Python 3.10 or newer. When installing Python, tick **"Add python.exe to PATH"**. See `HUONG-DAN-WINDOWS.txt` for a Vietnamese guide and fixes for the `no Qt platform plugin` error.

> If the game you are playing runs as administrator, run tetoMIDI as administrator too.

### Run from source

```bash
python -m pip install -r requirements.txt
python main.py
```

**Linux** needs the Qt runtime libraries and an **X11** session (key injection and global hotkeys do not work on Wayland-only sessions):

```bash
sudo apt install libegl1 libgl1 libxkbcommon0 libxcb-cursor0 libdbus-1-3
```

For a detailed log, run `python main.py --debug`.

### Build it yourself

```bash
python -m pip install -r requirements-build.txt
python scripts/build.py onedir      # dist/tetoMIDI/
python scripts/build.py onefile     # dist/tetoMIDI-portable(.exe)
```

The repo also ships a GitHub Actions workflow (`.github/workflows/build-desktop.yml`) that builds the Windows Setup / portable `.exe` and the Linux AppImage / `.deb`, and a Codespaces setup. See [CODESPACES.md](CODESPACES.md).

Run the tests with:

```bash
python -m unittest discover -s tests -t .
```

## Configuration

The config file is stored at:

- Windows: `%APPDATA%\tetoMIDI\config.json`
- Linux: `~/.config/tetoMIDI/config.json`

Set the `TETOMIDI_CONFIG_DIR` environment variable to use a different folder.

## Community

- Discord: **https://discord.gg/peaqm6uqgB**

## License and credits

tetoMIDI is released under the **GNU GPL v3** (see [LICENSE](LICENSE))
