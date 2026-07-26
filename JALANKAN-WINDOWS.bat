@echo off
REM =====================================================================
REM  Project Aegis - Stock AI Copilot
REM  Klik dua kali file ini untuk menjalankan aplikasi.
REM  Syarat: Python 3.10+ sudah terpasang (centang "Add Python to PATH"
REM  saat instalasi dari python.org).
REM =====================================================================
setlocal
cd /d "%~dp0"
title Project Aegis - Stock AI Copilot

echo.
echo  ==========================================================
echo    PROJECT AEGIS - STOCK AI COPILOT
echo  ==========================================================
echo.

REM --- 1. Cek Python -------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python tidak ditemukan.
    echo.
    echo      Silakan pasang Python dari https://www.python.org/downloads/
    echo      PENTING: centang "Add Python to PATH" saat instalasi,
    echo      lalu jalankan file ini lagi.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo  [1/4] Python %%v terdeteksi.

REM --- 2. Siapkan virtual environment --------------------------------
if not exist ".venv" (
    echo  [2/4] Menyiapkan lingkungan Python ^(sekali saja, mohon tunggu^)...
    python -m venv .venv
    if errorlevel 1 (
        echo  [X] Gagal membuat virtual environment.
        pause
        exit /b 1
    )
) else (
    echo  [2/4] Lingkungan Python sudah siap.
)
call .venv\Scripts\activate.bat

REM --- 3. Pasang dependensi ------------------------------------------
if not exist ".venv\.deps-installed" (
    echo  [3/4] Memasang komponen yang dibutuhkan ^(3-10 menit pertama kali^)...
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [X] Pemasangan komponen gagal. Periksa koneksi internet lalu ulangi.
        pause
        exit /b 1
    )
    echo ok> ".venv\.deps-installed"
) else (
    echo  [3/4] Komponen sudah terpasang.
)

REM --- 4. Jalankan backend + dashboard --------------------------------
echo  [4/4] Menyalakan aplikasi...
echo.

start "Aegis API" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn rag_financial_api:app --host 127.0.0.1 --port 8000"

echo  Menunggu mesin analisis siap...
set /a tries=0
:waitloop
set /a tries+=1
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:8000/health 2>nul
if errorlevel 1 (
    if %tries% lss 20 goto waitloop
)

echo.
echo  ==========================================================
echo    APLIKASI SIAP
echo    Dashboard akan terbuka di browser Anda.
echo    Dokumentasi API: http://127.0.0.1:8000/docs
echo.
echo    Tekan Ctrl+C di jendela ini untuk menghentikan aplikasi.
echo  ==========================================================
echo.

python -m streamlit run dashboard\streamlit_app.py --server.port 8501

REM --- Bersihkan: hentikan backend agar tidak tertinggal jalan --------
echo.
echo  Menghentikan mesin analisis...
taskkill /F /FI "WINDOWTITLE eq Aegis API*" >nul 2>&1
echo  Aplikasi dihentikan sepenuhnya.
pause
