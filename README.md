# 🛡️ Project Aegis AI Studio — Stock AI Copilot

> ## 🚀 Cara tercepat menjalankan (Windows)
> 1. Pasang **Python** dari [python.org/downloads](https://www.python.org/downloads/) — ✅ centang **"Add Python to PATH"** saat instalasi
> 2. Klik dua kali **`JALANKAN-WINDOWS.bat`**
> 3. Tunggu (pertama kali 3–10 menit), dashboard terbuka sendiri di browser
> 4. Buka tab **🔎 Pemindai Otomatis** → klik **Pindai Sekarang**
>
> macOS / Linux: jalankan `bash jalankan.sh`

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
JALANKAN-WINDOWS.bat          # Peluncur satu klik untuk Windows
jalankan.sh                   # Peluncur untuk macOS / Linux
rag_financial_api.py          # FastAPI backend: /scan, /analyze-stock, /upload-pdf, /query, /health
services/
  market_data.py              # Fetch OHLCV (yfinance, dengan retry) + indikator + skor teknikal
  analysis.py                 # Pipeline satu ticker (dipakai endpoint & scanner)
  scanner.py                  # Pemindai watchlist paralel + peringkat
  cache.py                    # Cache TTL agar tidak menembak API berulang kali
  risk_engine.py              # Position sizing ATR + Fractional Kelly (Section 5 blueprint)
  sentiment_engine.py         # Skor sentimen berita 0-100
  fundamental_engine.py       # Skor fundamental: RAG → rasio yfinance → netral
  rag_engine.py               # LlamaIndex + Qdrant + OpenAI (lazy init)
  scoring_engine.py           # Master Scoring Engine + klasifikasi sinyal
dashboard/streamlit_app.py    # Dashboard Streamlit — mode otomatis penuh
web/aegis_copilot.html        # Aplikasi web mandiri (semua engine berjalan di browser)
tests/                        # Pytest suite (offline, sumber eksternal di-mock)
```

> **Versi web instan**: `web/aegis_copilot.html` adalah aplikasi satu-file yang bisa dibuka
> langsung di browser tanpa server — seluruh engine (teknikal, risiko, sentimen, skoring)
> diporting 1:1 ke JavaScript. Input data via CSV (format Yahoo Finance) atau data demo.
> Data live & RAG PDF tetap membutuhkan backend FastAPI di bawah.

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
| `GET` | `/watchlists` | Daftar preset watchlist siap pakai |
| `POST` | `/scan` | **Pemindai otomatis**: analisis banyak saham paralel, diperingkat skor tertinggi |
| `POST` | `/analyze-stock` | Analisis lengkap satu saham: skor per engine, sinyal, rekomendasi lot |
| `POST` | `/upload-pdf` | Upload & ingest laporan keuangan PDF ke Vector DB |
| `POST` | `/query` | Tanya jawab atas laporan yang ter-ingest (jawaban + sumber kutipan) |
| `GET` | `/macro` | Kondisi makro ekonomi + asal-usul & kesegaran tiap indikator |
| `POST` | `/analyze-gold` | **Analisis emas**: makro + teknikal + sentimen + ukuran posisi (USD/oz) |
| `POST` | `/cache/clear` | Kosongkan cache data pasar (paksa ambil data terbaru) |

### Contoh `/scan` — pemindai otomatis

```bash
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"watchlist": "idx_bluechip", "total_capital": 100000000, "max_risk_pct": 0.02}'
```

Preset watchlist tersedia: `idx_bluechip`, `idx_energy_mining`, `idx_consumer_retail`, `us_megacap`.
Atau kirim daftar sendiri: `{"tickers": ["BBCA.JK", "TLKM.JK", "ASII.JK"]}`.

Respons memuat peringkat saham (`results`, terurut skor tertinggi), ringkasan siap-tabel (`table`),
`top_pick`, jumlah `buy_candidates`, serta `errors` per ticker yang gagal — satu ticker bermasalah
tidak menggagalkan seluruh pemindaian.

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

## 🥇 Modul Emas & Makro Ekonomi

Emas tidak punya laba, utang, atau laporan keuangan — sehingga mesin fundamental tidak
berlaku. Penggantinya adalah **Skor Makro**:

> Saham: `Fundamental×0,5 + Teknikal×0,3 + Sentimen×0,2`
> **Emas: `Makro×0,5 + Teknikal×0,3 + Sentimen×0,2`**

### Inflasi tidak perlu menunggu sebulan

Data CPI resmi memang terbit bulanan, tetapi pasar obligasi AS **memberi harga pada
inflasi setiap hari kerja**. Modul ini memakai dua seri harian tersebut, sehingga skor
makro ikut bergerak setiap hari — bukan sebulan sekali:

| Faktor | Bobot | Seri FRED | Frekuensi | Logika |
|---|---|---|---|---|
| Suku bunga riil 10 thn | 40 | `DFII10` | **Harian** | Riil negatif → uang tunai rugi → emas menarik |
| Indeks dolar | 25 | `DTWEXBGS` | Harian | Emas dihargai dalam dolar → berlawanan arah |
| Ekspektasi inflasi | 20 | `T10YIE` | **Harian** | Inflasi diperkirakan naik → emas sebagai lindung nilai |
| Imbal hasil obligasi | 15 | `DGS10` | Harian | Obligasi pesaing emas → yield naik menekan emas |

Konteks tambahan yang ditampilkan: suku bunga acuan The Fed (`DFF`) dan inflasi CPI
tahunan (`CPIAUCSL`) lengkap dengan tanggal terbitnya.

**Tidak memerlukan kunci API.** Data diambil lewat endpoint CSV publik FRED. Bila FRED
tidak terjangkau, tersedia proksi Yahoo Finance untuk sebagian indikator.

### Kejujuran data — mekanismenya, bukan sekadar janji

1. **Setiap angka membawa asal-usul**: nilai, tanggal observasi, sumber, dan umur hari.
   Bisa Anda periksa sendiri di `fred.stlouisfed.org` — angkanya harus sama persis.
2. **Gagal ambil = dinyatakan tidak tersedia**, komponennya diberi nilai netral, tidak
   pernah ditebak lalu disajikan seolah pasti.
3. **`completeness_pct`** memberi tahu berapa persen komponen yang benar-benar berhasil
   diambil, sehingga Anda tahu seberapa utuh skornya.
4. **Data basi ditandai** bila umurnya melewati batas wajar seri tersebut.
5. **Model bahasa (LLM) tidak menyentuh angka apa pun** di modul ini — seluruhnya data
   resmi + rumus deterministik.

### Sumber harga emas — apa adanya

Spot XAU/USD **tidak tersedia gratis** pada penyedia data publik (`XAUUSD=X` mengembalikan
404). Yang dipakai berurutan:

| Prioritas | Simbol | Keterangan |
|---|---|---|
| 1 | `GC=F` | Emas berjangka COMEX — bergerak sangat dekat dengan spot, **per troy ounce** |
| 2 | `GLD` | ETF SPDR — harga per unit ETF, **BUKAN per ounce** (ditandai jelas di hasil) |
| 3 | `IAU` | ETF iShares — sama, ditandai jelas |

Sumber yang benar-benar terpakai selalu dicantumkan; bila yang terpakai adalah ETF,
peringatan eksplisit muncul bahwa angkanya bukan harga per troy ounce.

### Sentimen emas berlawanan arah dengan saham

Kamus sentimen saham tidak bisa dipakai — bahkan sering terbalik artinya. Bagi saham
"resesi" adalah kabar buruk; bagi emas justru mendorong harga naik. Karena itu modul ini
memakai kamus tersendiri (perang, krisis, safe haven, pangkas suku bunga, bank sentral
borong emas → naik; pengetatan, dolar menguat, selera risiko → turun).

### Jam pasar & kesegaran harga

Emas berdagang hampir 24 jam (Minggu 18:00 – Jumat 17:00 waktu New York, dengan jeda
harian). Bila pasar tutup, sistem **menyatakannya terang-terangan** beserta umur harga
terakhir — bukan menampilkan harga penutupan seolah harga sedang berjalan.

## 🧮 Formula Risk Engine (Section 5 Blueprint)

1. **Stop loss berbasis volatilitas** — `SL = Entry − (k × ATR)`, k = 1.5–2.0
2. **Risk-based position sizing** — `Lembar = (Modal × Risiko%) ÷ (Entry − SL)`
3. **Fractional Kelly** — `f* = c × ((W·R − (1−W)) ÷ R)`, c = 0.25, di-clamp ≥ 0
4. Konversi ke satuan pasar, dibatasi maksimal 100% modal:
   - Saham IDX: **lot bulat** (1 lot = 100 lembar), mata uang IDR
   - Emas: **troy ounce pecahan** (mis. 1,3839 oz), mata uang USD

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

## 🔁 Ketahanan Operasional

| Situasi | Yang dilakukan aplikasi |
|---|---|
| Penyedia data membatasi permintaan (HTTP 429) | Coba ulang 3× dengan jeda, lalu pesan jelas + saran (`429`) |
| Koneksi internet putus | Pesan `ConnectionError` yang menyebut penyebabnya, bukan crash |
| Ticker salah ketik | `404` dengan pengingat format `.JK` untuk saham IDX |
| Satu saham gagal saat scanning | Dilewati, masuk daftar `errors`; saham lain tetap dianalisis |
| Data harga sama diminta berulang | Dilayani dari cache (10 menit), hemat kuota API |
| Tidak ada laporan PDF / rasio | Skor fundamental jatuh ke netral 50, pipeline tetap jalan |
| Kunci OpenAI belum diisi | Fitur RAG memberi pesan `503` yang jelas; fitur lain tetap jalan |

## 🎯 Integritas Penilaian

Dua keputusan desain agar skor tidak menyesatkan:

**Saham datar dinilai netral, bukan overbought.** Rumus RSI standar membagi rata-rata
kenaikan dengan rata-rata penurunan. Jika harga tidak bergerak sama sekali (saham tidak
likuid atau disuspend), pembaginya nol dan implementasi naif menghasilkan RSI 100 —
seolah-olah saham itu sedang euforia beli. Di sini kasus tersebut dikembalikan sebagai
**RSI 50 (netral)**.

**Rata-rata panjang tidak dinilai dari riwayat pendek.** EMA 200 yang dihitung dari data
6 bulan tetap menghasilkan angka, tapi angkanya bukan rata-rata 200 hari. Bila riwayat
kurang dari 200 bar, komponen tren EMA 200 diberi **nilai netral setengah** disertai
catatan, bukan poin penuh. Snapshot indikator menyertakan `data_points`,
`ema_50_reliable`, dan `ema_200_reliable` agar hal ini transparan.

## ⚠️ Disclaimer Penting

Output aplikasi ini bersifat **decision support**, bukan nasihat keuangan.

**Tidak ada sistem — termasuk ini — yang bisa memprediksi pasar saham dengan probabilitas 100%.**
Harga saham dipengaruhi peristiwa yang tidak dapat diketahui sebelumnya (kebijakan, berita mendadak,
sentimen global). Yang bisa dilakukan sistem ini adalah membuat keputusan Anda **konsisten,
berbasis data, dan terukur risikonya** — lewat stop loss otomatis berbasis volatilitas (ATR) dan
pembatasan ukuran posisi, sehingga satu transaksi yang salah tidak menghabiskan modal.

Selalu lakukan riset mandiri dan konsultasikan keputusan investasi dengan profesional berlisensi.
