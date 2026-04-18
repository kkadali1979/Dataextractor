@echo off
color 0A
title AI Business Data Extractor
cls

echo.
echo ============================================
echo   AI Business Data Extractor
echo   Google Places + Apify + Claude AI
echo ============================================
echo.

REM Check Python
echo [1/3] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Python is NOT installed!
    echo  Download from: https://www.python.org/downloads
    echo  IMPORTANT: Check "Add Python to PATH" during install
    echo.
    pause
    exit /b 1
)
echo       Python found!
echo.

REM Install libraries
echo [2/3] Installing libraries...
pip install flask requests beautifulsoup4 apify-client
if %errorlevel% neq 0 (
    python -m pip install flask requests beautifulsoup4 apify-client
)
echo.
echo       Libraries installed!
echo.

REM Launch app
echo [3/3] Starting application...
echo.
echo ============================================
echo   Opening browser at http://localhost:5000
echo   Keep this window open!
echo ============================================
echo.

start http://localhost:5000
python app_hyderabad.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Application failed to start
    echo.
    pause
    exit /b 1
)

echo.
echo Application closed.
pause
