# 🛡️ Project Aegis AI Studio — Stock AI Copilot

AI Stock Copilot & Decision Support System yang menggabungkan **5 sudut pandang analisis pasar saham** secara otomatis, sesuai Master Blueprint:

| Engine | Fungsi |
|---|---|
| **Fundamental (RAG)** | Analisis laporan keuangan PDF (Q1–Q4) via LlamaIndex + Qdrant + OpenAI |
| **Technical** | EMA(20/50/200), RSI(14), MACD(12/26/9), ATR(14), Support/Resistance |
| **Sentiment** | Skor sentimen judul berita (lexicon EN + ID, fallback netral) |
| **Risk** | Position sizing berbasis risiko + stop loss ATR + Fractional Kelly (c=0.25) |
| **Master Scoring** | `Total = Fundamental×0.5 + Technical×0.3 + Sentiment×0.2` → sinyal akhir |

```
[User Query / Request]
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (rag_financial_api.py)     │
├───────────────┬───────────────┬───────────────┬─────────────┤
│ Fundamental   │ Technical     │ Sentiment     │ Risk        │
│ Engine (RAG)  │ Engine        │ Engine        │ Engine      │
└───────┬───────┴───────┬───────┴───────┬───────┴──────┬──────┘
        │               │               │              │
        ▼               ▼               ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Master Scoring Engine                    │
│ Total = (Fundamental*0.5) + (Technical*0.3) + (Sentiment*0.2)│
└──────────────────────────────┬──────────────────────────────┘
                               ▼
   [STRONG BUY / BUY / HOLD / SELL / STRONG SELL + Position Size]
```

## 📁 Struktur Proyek

```
rag_financial_api.py          # FastAPI backend: /upload-pdf, /query, /analyze-stock, /health
services/
  market_data.py              # Fetch OHLCV (yfinance) + indikator teknikal + skor teknikal
  risk_engine.py              # Position sizing ATR + Fractional Kelly (Section 5 blueprint)
  sentiment_engine.py         # Skor sentimen berita 0-100
  fundamental_engine.py       # Skor fundamental: RAG → rasio yfinance → netral
  rag_engine.py               # LlamaIndex + Qdrant + OpenAI (lazy init)
  scoring_engine.py           # Master Scoring Engine + klasifikasi sinyal
dashboard/streamlit_app.py    # Dashboard Streamlit (Phase 4)
tests/                        # Pytest suite (offline, sumber eksternal di-mock)
```

## 🚀 Quick Start

### 1. Setup environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # isi OPENAI_API_KEY untuk fitur RAG
```

### 2. Jalankan backend FastAPI

```bash
uvicorn rag_financial_api:app --reload
# Swagger UI: http://localhost:8000/docs
```

### 3. Jalankan dashboard Streamlit

```bash
streamlit run dashboard/streamlit_app.py
# UI: http://localhost:8501
```

### 4. Atau via Docker Compose (API + dashboard + Qdrant + Redis + TimescaleDB)

```bash
OPENAI_API_KEY=sk-... docker compose up --build
```

## 🔌 API Endpoints

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/health` | Status API + kesiapan RAG |
| `POST` | `/upload-pdf` | Upload & ingest laporan keuangan PDF ke Vector DB |
| `POST` | `/query` | Tanya jawab atas laporan yang ter-ingest (jawaban + sumber kutipan) |
| `POST` | `/analyze-stock` | Analisis lengkap: skor 0-100 per engine, sinyal akhir, rekomendasi lot |

### Contoh `/analyze-stock`

```bash
curl -X POST http://localhost:8000/analyze-stock \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "BBCA.JK",
    "total_capital": 100000000,
    "max_risk_pct": 0.02,
    "atr_multiplier": 2.0,
    "win_rate": 0.55,
    "reward_risk_ratio": 2.0
  }'
```

Respons berisi: `signal`, `total_score`, skor per engine (`fundamental` / `technical` / `sentiment`), snapshot indikator, dan `risk_plan` (stop loss ATR, take profit, lot direkomendasikan, alokasi IDR, maks. potensi rugi, eksposur portofolio, fractional Kelly).

> Ticker Bursa Efek Indonesia memakai sufiks `.JK` (mis. `BBCA.JK`, `TLKM.JK`).

## 🧮 Formula Risk Engine (Section 5 Blueprint)

1. **Stop loss berbasis volatilitas** — `SL = Entry − (k × ATR)`, k = 1.5–2.0
2. **Risk-based position sizing** — `Lembar = (Modal × Risiko%) ÷ (Entry − SL)`
3. **Fractional Kelly** — `f* = c × ((W·R − (1−W)) ÷ R)`, c = 0.25, di-clamp ≥ 0
4. Konversi ke **lot IDX** (1 lot = 100 lembar), dibatasi maksimal 100% modal

## ✅ Testing

Test suite berjalan **offline** — yfinance/OpenAI di-mock, indikator diuji dengan data sintetis deterministik:

```bash
pip install -r requirements-dev.txt
pytest
```

## ⚙️ Konfigurasi (.env)

| Variabel | Default | Keterangan |
|---|---|---|
| `OPENAI_API_KEY` | — | Wajib untuk fitur RAG (upload PDF / query) |
| `AEGIS_LLM_MODEL` | `gpt-4o` | Model LLM untuk RAG |
| `AEGIS_EMBED_MODEL` | `text-embedding-3-small` | Model embedding |
| `QDRANT_URL` | *(kosong = in-memory)* | URL server Qdrant, mis. `http://localhost:6333` |
| `QDRANT_COLLECTION` | `financial_reports` | Nama koleksi vektor |
| `AEGIS_API_URL` | `http://localhost:8000` | Lokasi backend untuk dashboard |

## ⚠️ Disclaimer

Output aplikasi ini bersifat **decision support**, bukan nasihat keuangan. Selalu lakukan riset mandiri dan konsultasikan keputusan investasi dengan profesional berlisensi.
