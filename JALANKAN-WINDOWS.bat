@echo off
REM =====================================================================
REM  Project Aegis - Stock AI Copilot
REM  Klik dua kali file ini untuk menjalankan aplikasi.
REM  Syarat: Python 3.10+ terpasang (centang "Add Python to PATH").
REM =====================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Project Aegis - Stock AI Copilot

echo.
echo  ==========================================================
echo    PROJECT AEGIS - STOCK AI COPILOT
echo  ==========================================================
echo.

REM --- 0. Pastikan berkas proyek benar-benar ada di sini ---------------
REM Penyebab kegagalan paling umum: file .bat dijalankan langsung dari
REM DALAM file ZIP. Windows/WinRAR menyalin satu berkas itu ke folder
REM sementara, sehingga berkas proyek lainnya tidak ikut dan pemasangan
REM gagal dengan pesan "requirements.txt tidak ditemukan".
set "MISSING="
if not exist "requirements.txt"            set "MISSING=!MISSING! requirements.txt"
if not exist "rag_financial_api.py"        set "MISSING=!MISSING! rag_financial_api.py"
if not exist "dashboard\streamlit_app.py"  set "MISSING=!MISSING! dashboard\streamlit_app.py"
if not exist "services\market_data.py"     set "MISSING=!MISSING! services\market_data.py"

if defined MISSING (
    REM Layar dibersihkan agar pesan terbaca utuh dari atas — pesan yang
    REM tergulung ke atas membuat penyebabnya tidak terlihat.
    cls
    echo.
    echo  ==========================================================
    echo    PROJECT AEGIS - PEMERIKSAAN GAGAL
    echo  ==========================================================
    echo.
    echo  [X] Berkas proyek tidak lengkap di folder ini.
    echo      Tidak ditemukan:!MISSING!
    echo.
    echo      Folder saat ini:
    echo      %CD%
    echo.
    echo      Isi folder ini:
    dir /b /a 2>nul | findstr /n "^" | findstr /r "^[1-9]: ^1[0-9]:"
    echo.
    echo  ==========================================================
    echo   PENYEBAB TERSERING: file ini dijalankan dari DALAM ZIP.
    echo  ==========================================================
    echo.
    echo   Cara memperbaiki:
    echo     1. Tutup jendela ini.
    echo     2. Cari file ZIP di folder Downloads.
    echo     3. Klik KANAN pada ZIP - pilih "Extract All" / "Ekstrak ke...".
    echo        (Jangan hanya klik dua kali lalu buka file di dalamnya.)
    echo     4. Buka folder HASIL EKSTRAK.
    echo     5. Klik dua kali JALANKAN-WINDOWS.bat yang ada DI DALAM folder itu.
    echo.
    echo   Folder yang benar berisi banyak berkas, antara lain:
    echo     requirements.txt, rag_financial_api.py, folder services, folder dashboard
    echo.
    pause
    exit /b 1
)

REM --- 1. Cek Python ---------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python tidak ditemukan.
    echo.
    echo      Pasang Python dari https://www.python.org/downloads/
    echo      PENTING: centang "Add Python to PATH" saat instalasi,
    echo      lalu jalankan file ini lagi.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo  [1/4] Python !PYVER! terdeteksi.

REM Nilai bawaan agar perbandingan tidak error bila format versi tak terduga
set "PYMAJOR=0"
set "PYMINOR=0"
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set "PYMAJOR=%%a"
    set "PYMINOR=%%b"
)
REM Format versi tidak dikenali - lanjutkan saja, pip akan mengeluh bila bermasalah
if "!PYMAJOR!"=="0" goto :pyok
if !PYMAJOR! LSS 3 goto :pyterlalulama
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 10 goto :pyterlalulama
goto :pyok

:pyterlalulama
echo  [X] Python !PYVER! terlalu lama. Dibutuhkan Python 3.10 atau lebih baru.
echo      Unduh versi terbaru di https://www.python.org/downloads/
pause
exit /b 1

:pyok
if !PYMAJOR! EQU 3 if !PYMINOR! GEQ 14 (
    echo       Catatan: Python !PYVER! tergolong sangat baru. Bila ada komponen
    echo       yang gagal dipasang, memasang Python 3.12 biasanya paling mulus.
)

REM --- 2. Siapkan virtual environment -----------------------------------
if not exist ".venv\Scripts\activate.bat" (
    if exist ".venv" (
        echo  [2/4] Lingkungan lama tidak lengkap, membuat ulang...
        rmdir /s /q ".venv"
    ) else (
        echo  [2/4] Menyiapkan lingkungan Python ^(sekali saja, mohon tunggu^)...
    )
    python -m venv .venv
    if errorlevel 1 (
        echo  [X] Gagal membuat virtual environment.
        echo      Coba jalankan dari folder tanpa spasi/karakter khusus,
        echo      atau di luar folder OneDrive yang sedang menyinkron.
        pause
        exit /b 1
    )
) else (
    echo  [2/4] Lingkungan Python sudah siap.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo  [X] Gagal mengaktifkan lingkungan Python.
    pause
    exit /b 1
)

REM --- 3. Pasang komponen ------------------------------------------------
if not exist ".venv\.deps-installed" (
    echo  [3/4] Memasang komponen yang dibutuhkan ^(3-8 menit pertama kali^)...
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [X] Pemasangan komponen gagal.
        echo.
        echo      Kemungkinan penyebab:
        echo        - Koneksi internet terputus saat mengunduh.
        echo        - Python !PYVER! terlalu baru sehingga sebagian komponen
        echo          belum tersedia. Memasang Python 3.12 biasanya menyelesaikan ini.
        echo.
        echo      Coba jalankan ulang file ini setelah memperbaiki hal di atas.
        echo.
        pause
        exit /b 1
    )
    echo ok> ".venv\.deps-installed"
) else (
    echo  [3/4] Komponen sudah terpasang.
)

REM --- 4. Jalankan backend + dashboard ------------------------------------
echo  [4/4] Menyalakan aplikasi...
echo.

start "Aegis API" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn rag_financial_api:app --host 127.0.0.1 --port 8000"

echo  Menunggu mesin analisis siap...
REM curl tersedia pada Windows 10 versi 1803 ke atas. Bila tidak ada,
REM cukup beri jeda tetap daripada mengulang 20 kali tanpa guna.
REM Catatan: label TIDAK boleh diletakkan di dalam blok kurung pada batch —
REM goto ke dalamnya merusak konteks blok. Karena itu alurnya memakai goto.
where curl >nul 2>&1
if errorlevel 1 goto :tanpacurl

set /a tries=0
:waitloop
set /a tries+=1
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:8000/health 2>nul
if errorlevel 1 (
    if !tries! lss 20 goto waitloop
)
goto :siap

:tanpacurl
timeout /t 12 /nobreak >nul

:siap

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

REM --- Bersihkan: hentikan backend agar tidak tertinggal jalan ------------
echo.
echo  Menghentikan mesin analisis...
taskkill /F /FI "WINDOWTITLE eq Aegis API*" >nul 2>&1
echo  Aplikasi dihentikan sepenuhnya.
pause
