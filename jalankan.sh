#!/usr/bin/env bash
# =====================================================================
#  Project Aegis - Stock AI Copilot (macOS / Linux)
#  Jalankan dengan:  bash jalankan.sh
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo
echo "=========================================================="
echo "  PROJECT AEGIS - STOCK AI COPILOT"
echo "=========================================================="
echo

# --- 0. Pastikan berkas proyek lengkap -------------------------------
# Penyebab kegagalan tersering: skrip dijalankan dari lokasi yang hanya
# berisi berkas ini saja (mis. diekstrak sebagian dari ZIP).
missing=""
for f in requirements.txt rag_financial_api.py dashboard/streamlit_app.py services/market_data.py; do
  [ -f "$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
  echo "[X] Berkas proyek tidak lengkap di folder ini."
  echo "    Tidak ditemukan:$missing"
  echo "    Folder saat ini: $(pwd)"
  echo
  echo "    Pastikan ZIP sudah diekstrak SEPENUHNYA, lalu jalankan skrip"
  echo "    ini dari dalam folder hasil ekstrak."
  exit 1
fi

# --- 1. Cek Python ---------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "[X] Python 3 tidak ditemukan. Pasang dulu dari https://www.python.org/downloads/"
  exit 1
fi
echo "[1/4] $(python3 --version) terdeteksi."
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "[X] Dibutuhkan Python 3.10 atau lebih baru."
  exit 1
fi

# --- 2. Virtual environment ------------------------------------------
if [ ! -d ".venv" ]; then
  echo "[2/4] Menyiapkan lingkungan Python (sekali saja)..."
  python3 -m venv .venv
else
  echo "[2/4] Lingkungan Python sudah siap."
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- 3. Dependensi ----------------------------------------------------
if [ ! -f ".venv/.deps-installed" ]; then
  echo "[3/4] Memasang komponen (3-10 menit pertama kali)..."
  python -m pip install --upgrade pip --quiet
  python -m pip install -r requirements.txt
  touch .venv/.deps-installed
else
  echo "[3/4] Komponen sudah terpasang."
fi

# --- 4. Jalankan ------------------------------------------------------
echo "[4/4] Menyalakan aplikasi..."
python -m uvicorn rag_financial_api:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT INT TERM

echo "Menunggu mesin analisis siap..."
for _ in $(seq 1 20); do
  if curl -s -o /dev/null http://127.0.0.1:8000/health; then break; fi
  sleep 2
done

echo
echo "=========================================================="
echo "  APLIKASI SIAP"
echo "  Dashboard: http://localhost:8501"
echo "  Dokumentasi API: http://127.0.0.1:8000/docs"
echo "  Tekan Ctrl+C untuk berhenti."
echo "=========================================================="
echo

python -m streamlit run dashboard/streamlit_app.py --server.port 8501
