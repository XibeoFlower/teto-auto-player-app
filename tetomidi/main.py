"""Program entry point."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys

from .paths import log_dir
from .platform_tweaks import process_setup

_PLUGIN_FIX_TEXT = (
    "Cach sua - chon 1 trong 2:\n"
    "  1. Mo CMD roi chay 2 lenh:\n"
    "       python -m pip uninstall -y PySide6\n"
    "       python -m pip install --force-reinstall PySide6\n"
    "  2. Cai Microsoft Visual C++ Redistributable 2015-2022 (x64):\n"
    "       https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
    "  Sau do chay lai bang START-tetoMIDI-WINDOWS.bat\n"
    "\n"
    "(English: reinstall PySide6 with 'python -m pip install --force-reinstall PySide6',\n"
    "or install the Microsoft Visual C++ Redistributable x64, then run\n"
    "START-tetoMIDI-WINDOWS.bat.)"
)


def _startup_text(head: str, detail: str) -> str:
    return f"{head}\n\nChi tiet / Details: {detail}\n\n{_PLUGIN_FIX_TEXT}"


def _show_startup_help(text: str) -> None:
    """In huong dan ra console + (Windows) hien message box, roi giu cua so lai neu can."""
    try:
        print(text, file=sys.stderr, flush=True)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "tetoMIDI", 0x10)
        except Exception:
            pass


def _setup_logging(debug: bool) -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir() / "tetomidi.log", maxBytes=512_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    if debug and sys.stderr:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=handlers or None)


def _install_qt_fatal_handler() -> None:
    """Chan qFatal cua Qt (vd: 'no Qt platform plugin could be initialized'): hien huong dan sua
    thay cho dialog loi cua Qt, roi ket thuc sach se. Handler phai toi gian - khong logging."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def _handler(mode, _ctx, message):
        if mode == QtMsgType.QtFatalMsg:
            text = _startup_text("tetoMIDI khong the khoi dong vi loi Qt platform plugin (PySide6).",
                                 message)
            try:
                print(text, file=sys.stderr, flush=True)
            except Exception:
                try:
                    print(message, file=sys.stderr, flush=True)
                except Exception:
                    pass
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(None, text, "tetoMIDI", 0x10)
                except Exception:
                    pass
            try:
                sys.stdout.flush()
            except Exception:
                pass
            os._exit(1)          # khong cho Qt abort sau khi handler tra ve

    qInstallMessageHandler(_handler)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="tetoMIDI")
    parser.add_argument("--debug", action="store_true", help="log to the console as well")
    args = parser.parse_args(argv)
    _setup_logging(args.debug)
    undo = process_setup()
    try:
        _install_qt_fatal_handler()
        from .qtui.app import TetoApp  # imported late so DPI awareness is set before Qt starts
        app = TetoApp(intro=True)
        app.run()
    except ImportError as exc:
        if "PySide6" not in str(exc):
            raise
        log.error("missing PySide6: %s", exc)
        _show_startup_help(_startup_text(
            "tetoMIDI khong the khoi dong vi thieu thu vien PySide6.", exc))
    except RuntimeError as exc:
        if "platform plugin" not in str(exc).lower():
            raise
        log.error("qt plugin: %s", exc)
        _show_startup_help(_startup_text(
            "tetoMIDI khong the khoi dong vi loi Qt platform plugin (PySide6).", exc))
    finally:
        if undo:
            undo()


if __name__ == "__main__":
    main()
