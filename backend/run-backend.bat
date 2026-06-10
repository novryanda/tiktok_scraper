@echo off
REM ============================================================
REM  RUN BACKEND TIKTOK SCRAPER (Windows)
REM ============================================================
cd /d "%~dp0"

if not exist .venv\Scripts\activate (
    echo  X venv belum ada. Jalankan setup-backend.bat dulu.
    pause
    exit /b 1
)

call .venv\Scripts\activate

echo.
echo ====================================================
echo   TIKTOK SCRAPER BRIDGE
echo   URL  : http://localhost:8000
echo   Docs : http://localhost:8000/docs
echo ====================================================
echo.

uvicorn main:app --reload --port 8000
pause
