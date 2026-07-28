@echo off
REM =====================================================================
REM  Project Aegis - Stock AI Copilot
REM  Klik dua kali file ini untuk menjalankan aplikasi.
REM  Syarat: Python 3.10+ terpasang (centang "Add Python to PATH").
REM
REM  CATATAN TEKNIS PENTING:
REM  Seluruh percabangan galat memakai GOTO, bukan blok "if ( ... )".
REM  Alasannya: cmd.exe mengurai isi blok kurung SEBELUM menjalankannya,
REM  dan saat itu %VAR% sudah disubstitusi. Bila nilainya mengandung
REM  tanda kurung - misalnya folder bernama "Aegis (1)" hasil unduhan
REM  kedua - kurung tutup itu mengakhiri blok lebih awal dan skrip mati
REM  pesan "was unexpected at this time", bahkan ketika kondisinya tidak
REM  terpenuhi. Menaruh pesan galat di label terpisah menghilangkan
REM  seluruh kelas masalah ini.
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
set "MISSING="
if not exist "requirements.txt"            set "MISSING=!MISSING! requirements.txt"
if not exist "rag_financial_api.py"        set "MISSING=!MISSING! rag_financial_api.py"
if not exist "dashboard\streamlit_app.py"  set "MISSING=!MISSING! dashboard\streamlit_app.py"
if not exist "services\market_data.py"     set "MISSING=!MISSING! services\market_data.py"
if defined MISSING goto :galat_berkas

REM --- 1. Cek Python ---------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 goto :galat_python_hilang

set "PYVER="
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo  [1/4] Python !PYVER! terdeteksi.

set "PYMAJOR=0"
set "PYMINOR=0"
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do set "PYMAJOR=%%a" & set "PYMINOR=%%b"

if "!PYMAJOR!"=="0" goto :python_ok
if !PYMAJOR! LSS 3 goto :galat_python_lama
if not !PYMAJOR! EQU 3 goto :python_ok
if !PYMINOR! LSS 10 goto :galat_python_lama
if !PYMINOR! GEQ 14 echo       Catatan: Python !PYVER! tergolong sangat baru. Bila ada komponen yang gagal, memasang Python 3.12 biasanya paling mulus.

:python_ok

REM --- 2. Siapkan virtual environment -----------------------------------
if exist ".venv\Scripts\activate.bat" goto :venv_siap
if not exist ".venv" goto :venv_baru

echo  [2/4] Lingkungan lama tidak lengkap, membuat ulang...
rmdir /s /q ".venv"
goto :venv_buat

:venv_baru
echo  [2/4] Menyiapkan lingkungan Python ^(sekali saja, mohon tunggu^)...

:venv_buat
python -m venv .venv
if errorlevel 1 goto :galat_venv
goto :venv_aktifkan

:venv_siap
echo  [2/4] Lingkungan Python sudah siap.

:venv_aktifkan
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :galat_venv

REM --- 3. Pasang komponen ------------------------------------------------
if exist ".venv\.deps-installed" goto :deps_siap

echo  [3/4] Memasang komponen yang dibutuhkan ^(3-8 menit pertama kali^)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 goto :galat_pip
echo ok> ".venv\.deps-installed"
goto :deps_selesai

:deps_siap
echo  [3/4] Komponen sudah terpasang.

:deps_selesai

REM --- 4. Jalankan backend + dashboard ------------------------------------
echo  [4/4] Menyalakan aplikasi...
echo.

start "Aegis API" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn rag_financial_api:app --host 127.0.0.1 --port 8000"

echo  Menunggu mesin analisis siap...
where curl >nul 2>&1
if errorlevel 1 goto :tanpa_curl

set /a tries=0
:tunggu
set /a tries+=1
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:8000/health 2>nul
if not errorlevel 1 goto :siap
if !tries! lss 20 goto :tunggu
goto :siap

:tanpa_curl
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

echo.
echo  Menghentikan mesin analisis...
taskkill /F /FI "WINDOWTITLE eq Aegis API*" >nul 2>&1
echo  Aplikasi dihentikan sepenuhnya.
pause
exit /b 0


REM =====================================================================
REM  Pesan galat - di luar blok kurung mana pun, sehingga aman menampilkan
REM  path yang mengandung tanda kurung atau spasi.
REM =====================================================================

:galat_berkas
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
echo      "%CD%"
echo.
echo      Isi folder ini:
dir /b /a 2>nul
echo.
echo  ==========================================================
echo   PENYEBAB TERSERING: file ini dijalankan dari DALAM ZIP.
echo  ==========================================================
echo.
echo   Cara memperbaiki:
echo     1. Tutup jendela ini.
echo     2. Cari file ZIP di folder Downloads.
echo     3. Klik KANAN pada ZIP - pilih "Extract All".
echo     4. Buka folder HASIL EKSTRAK.
echo     5. Klik dua kali JALANKAN-WINDOWS.bat yang ada DI DALAM folder itu.
echo.
echo   Folder yang benar berisi requirements.txt, rag_financial_api.py,
echo   folder services, dan folder dashboard.
echo.
pause
exit /b 1

:galat_python_hilang
echo.
echo  [X] Python tidak ditemukan.
echo.
echo      Pasang Python dari https://www.python.org/downloads/
echo      PENTING: centang "Add Python to PATH" saat instalasi,
echo      lalu jalankan file ini lagi.
echo.
pause
exit /b 1

:galat_python_lama
echo.
echo  [X] Python !PYVER! terlalu lama. Dibutuhkan Python 3.10 atau lebih baru.
echo      Unduh versi terbaru di https://www.python.org/downloads/
echo.
pause
exit /b 1

:galat_venv
echo.
echo  [X] Gagal menyiapkan lingkungan Python.
echo.
echo      Folder saat ini:
echo      "%CD%"
echo.
echo      Coba pindahkan folder aplikasi ke lokasi yang lebih sederhana,
echo      contohnya  C:\Aegis  - lalu jalankan lagi dari sana.
echo.
pause
exit /b 1

:galat_pip
echo.
echo  [X] Pemasangan komponen gagal.
echo.
echo      Kemungkinan penyebab:
echo        - Koneksi internet terputus saat mengunduh.
echo        - Python !PYVER! terlalu baru sehingga sebagian komponen
echo          belum tersedia. Memasang Python 3.12 biasanya menyelesaikan ini.
echo.
echo      Jalankan ulang berkas ini setelah memperbaiki hal di atas.
echo.
pause
exit /b 1
