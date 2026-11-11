# Build tetoMIDI in GitHub Codespaces

tetoMIDI is Python + PySide6 (Qt). The devcontainer (`.devcontainer/`) installs PortAudio, the Qt runtime
libs (libegl1, libgl1, libxkbcommon0, libxcb-cursor0, ...) and `requirements.txt` for you.

1. Push this repository to GitHub.
2. On GitHub, choose **Code → Codespaces → Create codespace on main**.
3. When the setup finishes, in the Codespaces terminal:

```bash
python -m unittest discover -s tests -t .   # unit tests
python main.py                              # start the app
```

The Codespace has a built-in Linux desktop (desktop-lite): open the **Ports** panel, port **6080**, and the
app window appears in the browser (noVNC login `vscode` / `vscode`).

## Build the Windows .exe inside the Codespace (Wine + NSIS)

```bash
bash scripts/codespace_build_windows.sh
```

One command, 15-25 minutes the first time. It writes to `dist/`:

- `tetoMIDI-1.5.0-portable.exe` - portable exe, just run it
- `tetoMIDI-1.5.0-Setup.exe` - NSIS installer

Download both from the Explorer (right click → Download). Wine is not a real Windows: if a step fails,
build on a real Windows PC instead (README → "Build locally").

## Build the Linux AppImage + .deb inside the Codespace

```bash
bash scripts/codespace_build_linux.sh
```

Writes `dist/tetoMIDI-1.5.0-x86_64.AppImage` and `dist/tetomidi_1.5.0_amd64.deb`.

## Or let GitHub Actions build everything

Push a tag `v1.5.0` (or run the workflow manually: repo → **Actions** → *Build desktop apps* →
**Run workflow**). `.github/workflows/build-desktop.yml` builds the Windows and Linux artifacts and, on a
tag push, attaches them to a GitHub Release automatically (README → "GitHub Actions").
