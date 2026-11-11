@echo off
setlocal
title tetoMIDI - Windows launcher
cd /d "%~dp0"

echo ==============================================
echo   tetoMIDI player v1.5.0 - Windows launcher
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python not found on this PC.
  echo     1. Download Python 3.10+ from https://www.python.org/downloads/
  echo     2. When installing, tick "Add python.exe to PATH".
  echo     3. Run this file again.
  echo.
  pause
  exit /b 1
)

echo [1/2] Checking PySide6 ...
python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo       PySide6 not found - installing all dependencies, please wait ...
  python -m pip install -r requirements.txt
  goto RUN
)

echo       Checking Qt platform plugin ...
python -c "import os,sys; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; QApplication([])" >nul 2>nul
if errorlevel 1 (
  echo [!]   PySide6 is broken - reinstalling it, please wait ...
  python -m pip uninstall -y PySide6 PySide6-Essentials PySide6-Addons >nul 2>nul
  python -m pip install --force-reinstall PySide6
  goto RUN
)

:RUN
echo [2/2] Starting tetoMIDI ...
python main.py
if errorlevel 1 (
  echo.
  echo [X] tetoMIDI could not start. Try these fixes:
  echo     1. python -m pip install --force-reinstall PySide6
  echo     2. Install "Microsoft Visual C++ Redistributable 2015-2022 (x64)":
  echo        https://aka.ms/vs/17/release/vc_redist.x64.exe
  echo     3. Read HUONG-DAN-WINDOWS.txt for more help.
  echo.
  pause
)
endlocal
