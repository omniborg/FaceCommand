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
py -3.12 -m pip install PyQt6 opencv-python==4.10.0.84 mediapipe==0.10.31 numpy==1.26.4 --quiet
echo.
echo  Starting FaceCommand (Administrator)...
echo.
py -3.12 facecommand.py
echo.
pause
