@echo off
REM =====================================================================
REM  PASANG AEGIS - Pemasang satu berkas
REM
REM  Berbeda dari JALANKAN-WINDOWS.bat, berkas ini TIDAK membutuhkan
REM  berkas lain di sebelahnya. Ia mengunduh dan mengekstrak proyeknya
REM  sendiri, sehingga tetap bekerja walau dijalankan dari dalam ZIP,
REM  dari folder Downloads, atau dari mana pun.
REM
REM  Cukup klik dua kali. Tidak perlu mengekstrak apa pun secara manual.
REM =====================================================================
setlocal enabledelayedexpansion
title Pasang Project Aegis - Stock AI Copilot
color 0F

set "REPO=trederxxx508-ops/Project-Aegis-AI-Studio"
set "BRANCH=claude/stock-ai-copilot-blueprint-yfzddw"
set "ZIPURL=https://github.com/%REPO%/archive/refs/heads/%BRANCH%.zip"
set "TUJUAN=%USERPROFILE%\Aegis"
set "ZIPFILE=%TEMP%\aegis-download.zip"

echo.
echo  ==========================================================
echo    PEMASANG PROJECT AEGIS - STOCK AI COPILOT
echo  ==========================================================
echo.
echo   Aplikasi akan dipasang di:
echo     %TUJUAN%
echo.

REM --- 1. Cek Python ----------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python belum terpasang.
    echo.
    echo      1. Buka https://www.python.org/downloads/
    echo      2. Unduh dan pasang Python.
    echo      3. PENTING: centang "Add Python to PATH" di layar pertama.
    echo      4. Setelah selesai, jalankan berkas ini lagi.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo  [1/4] Python !PYVER! terdeteksi.

REM --- 2. Unduh proyek --------------------------------------------------
echo  [2/4] Mengunduh aplikasi dari GitHub...
if exist "%ZIPFILE%" del /f /q "%ZIPFILE%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; ^
   $ProgressPreference='SilentlyContinue'; ^
   try { Invoke-WebRequest -Uri '%ZIPURL%' -OutFile '%ZIPFILE%' -UseBasicParsing; exit 0 } ^
   catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo  [X] Gagal mengunduh. Periksa koneksi internet Anda lalu ulangi.
    echo.
    pause
    exit /b 1
)
if not exist "%ZIPFILE%" (
    echo  [X] Berkas unduhan tidak ditemukan. Coba ulangi.
    pause
    exit /b 1
)

REM --- 3. Ekstrak otomatis ----------------------------------------------
echo  [3/4] Mengekstrak berkas...
if not exist "%TUJUAN%" goto :buat_folder
echo        Menghapus pemasangan lama...
rmdir /s /q "%TUJUAN%" >nul 2>&1

:buat_folder
mkdir "%TUJUAN%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; ^
   try { Expand-Archive -Path '%ZIPFILE%' -DestinationPath '%TUJUAN%' -Force; exit 0 } ^
   catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo  [X] Gagal mengekstrak berkas.
    pause
    exit /b 1
)
del /f /q "%ZIPFILE%" >nul 2>&1

REM GitHub membungkus isi ZIP dalam satu folder bernama repo-branch.
REM Cari folder itu, lalu naikkan isinya agar rapi.
set "ISI="
for /d %%d in ("%TUJUAN%\*") do (
    if exist "%%d\requirements.txt" set "ISI=%%d"
)
if not defined ISI goto :galat_struktur

REM --- 4. Jalankan ------------------------------------------------------
echo  [4/4] Menyalakan aplikasi...
echo.
echo  ==========================================================
echo    PEMASANGAN SELESAI
echo.
echo    Lokasi aplikasi:
echo      !ISI!
echo.
echo    Lain kali cukup buka folder itu dan klik dua kali
echo    JALANKAN-WINDOWS.bat - tidak perlu memasang ulang.
echo  ==========================================================
echo.
timeout /t 4 /nobreak >nul

cd /d "!ISI!"
call "JALANKAN-WINDOWS.bat"
exit /b 0


REM =====================================================================
REM  Pesan galat - di luar blok kurung, aman untuk path apa pun.
REM =====================================================================

:galat_struktur
echo.
echo  [X] Struktur berkas tidak seperti yang diharapkan.
echo      Periksa isi folder:
echo      "%TUJUAN%"
echo.
pause
exit /b 1
