@echo off
:: Self-elevate to admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Set working directory to where the bat file lives
cd /d "%~dp0"

title FaceCommand
echo.
echo  Installing dependencies...
python -m pip install PyQt6 opencv-python mediapipe numpy --quiet
echo.
echo  Starting FaceCommand (Administrator)...
echo.
python facecommand.py
echo.
pause
