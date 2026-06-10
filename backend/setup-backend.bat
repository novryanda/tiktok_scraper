@echo off
REM ============================================================
REM  SETUP BACKEND TIKTOK SCRAPER (Windows)
REM  - Buat virtual environment
REM  - Install semua dependencies
REM  - Install browser Chromium untuk Playwright
REM ============================================================
echo.
echo ====================================================
echo   SETUP BACKEND TIKTOK SCRAPER
echo ====================================================
echo.

cd /d "%~dp0"

echo [1/4] Membuat virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 (
    echo  X Gagal buat venv. Pastikan Python terinstall dan ada di PATH.
    pause
    exit /b 1
)

echo [2/4] Mengaktifkan venv...
call .venv\Scripts\activate

echo [3/4] Install dependencies dari requirements.txt...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo  X Gagal install dependencies.
    pause
    exit /b 1
)

echo [4/4] Install browser Chromium untuk Playwright...
playwright install chromium

echo.
echo ====================================================
echo   SETUP SELESAI!
echo ====================================================
echo.
echo  Langkah berikutnya:
echo   1. Pindahkan file engine TikTok ke folder backend\engine\
echo   2. Login TikTok: jalankan engine\tiktok_session_manager.py
echo   3. Jalankan backend: double-click run-backend.bat
echo.
echo  Di VS Code, pilih interpreter:
echo   Ctrl+Shift+P -> Python: Select Interpreter -> .venv\Scripts\python.exe
echo.
pause
