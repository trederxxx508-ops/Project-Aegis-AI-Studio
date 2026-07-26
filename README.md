# 🛡️ Project Aegis AI Studio — Stock AI Copilot

> ## 🚀 Cara tercepat menjalankan (Windows)
> 1. Pasang **Python** dari [python.org/downloads](https://www.python.org/downloads/) — ✅ centang **"Add Python to PATH"** saat instalasi
> 2. **Klik KANAN file ZIP → "Extract All"** ⚠️ *(jangan jalankan file dari dalam ZIP)*
> 3. Buka folder hasil ekstrak → klik dua kali **`JALANKAN-WINDOWS.bat`**
> 4. Tunggu (pertama kali 3–8 menit), dashboard terbuka sendiri di browser
> 5. Buka tab **🔎 Pemindai Otomatis** → klik **Pindai Sekarang**
>
> macOS / Linux: `bash jalankan.sh`

## 🛠️ Bila Gagal Berjalan

| Pesan galat | Penyebab | Cara memperbaiki |
|---|---|---|
| `Could not open requirements file` atau `Berkas proyek tidak lengkap` | File `.bat` dijalankan dari **dalam ZIP** — Windows menyalinnya sendirian ke folder sementara | Klik kanan ZIP → **Extract All**, lalu jalankan `.bat` dari folder hasil ekstrak |
| `Python tidak ditemukan` | Python belum terpasang, atau lupa mencentang "Add Python to PATH" | Pasang ulang Python dan **centang "Add Python to PATH"** |
| `Python ... terlalu lama` | Versi di bawah 3.10 | Unduh Python terbaru |
| Pemasangan komponen gagal | Internet terputus, atau versi Python sangat baru sehingga komponen belum tersedia | Periksa koneksi; bila Python 3.14+ bermasalah, pasang Python 3.12 |
| Fitur PDF memberi pesan `requirements-rag.txt` | Komponen RAG memang opsional dan belum dipasang | `pip install -r requirements-rag.txt` — **fitur lain tetap jalan tanpa ini** |

Peluncur memeriksa semua hal di atas **sebelum** memasang apa pun, sehingga galat muncul
sebagai panduan yang jelas, bukan pesan teknis yang membingungkan.

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
pip install -r requirements.txt      # inti — cukup untuk hampir semua fitur
cp .env.example .env
```

**Komponen dipisah dengan sengaja.** `requirements.txt` hanya berisi yang ringan dan
diperlukan untuk analisis saham, emas, makro, uji mundur, riwayat, dan dashboard.
Komponen berat untuk membaca laporan PDF bersifat opsional:

```bash
pip install -r requirements-rag.txt   # hanya bila ingin fitur baca PDF
```

Alasannya sederhana: memaksa semua orang memasang LlamaIndex + Qdrant membuat pemasangan
jauh lebih lama dan menambah peluang gagal, padahal fitur utama tidak membutuhkannya
sama sekali. Bila komponen RAG belum ada, endpoint PDF memberi pesan yang memandu —
bukan gagal dengan galat teknis.

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
| `POST` | `/backtest` | **Uji mundur**: apakah sinyalnya terbukti? + kalibrasi win rate |
| `GET` | `/regime` | Apakah hubungan makro-emas sedang berlaku? |
| `POST` | `/snapshot/{asset}` | Rekam kondisi sekarang + laporkan perubahan sejak rekaman terakhir |
| `GET` | `/history/{asset}` | Riwayat skor + arah pergerakannya |
| `GET` | `/history` | Daftar aset yang punya riwayat |
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

### ⚠️ Model ini diuji terhadap datanya sendiri — dan sebagian tidak lolos

Jalankan sendiri: `python scripts/validate_macro_relationship.py`

**Yang terbukti** — hubungan sewaktu antara suku bunga riil dan emas nyata dan konsisten:

| Rentang perubahan | Korelasi dengan imbal hasil emas |
|---|---|
| Harian | −0,31 |
| Mingguan | −0,44 |
| Bulanan | −0,48 |
| Kuartalan | −0,45 |

Arahnya negatif persis seperti teori: suku bunga riil naik → emas tertekan.

**Yang TIDAK terbukti** — penilaian berdasarkan *level*. Model lama memberi 28 dari 40 poin
pada level suku bunga riil, dengan asumsi level rendah = baik untuk emas. Data 2016–2026
menunjukkan sebaliknya:

| Level suku bunga riil | Nilai model lama | Imbal hasil emas 3 bulan berikutnya |
|---|---|---|
| −2% s/d 0% | terbaik (40/40) | **+1,20%** |
| 0% s/d 1% | baik | +1,05% |
| 1% s/d 2% | netral | +6,71% |
| 2% s/d 3% | buruk (10/40) | **+8,15%** |

Korelasi level terhadap imbal hasil ke depan: **+0,349** — berlawanan dengan asumsi model.

**Yang dilakukan:** bobot level diturunkan dari 28 → 12 poin, arah dinaikkan 12 → 28 poin.
Bobotnya **tidak dibalik**, karena membalik berdasarkan satu rezim pasar berisiko menjadi
curve-fitting — sementara mempertahankan bobot besar pada asumsi tak berdasar sama saja
dengan percaya diri tanpa dasar.

**Keterbatasan yang harus dinyatakan:** sepuluh tahun terakhir adalah satu rezim di mana
emas naik hampir terus-menerus; jendela tiga bulan saling tumpang tindih sehingga
pengamatan independennya jauh lebih sedikit; dan sejak 2022 pembelian besar bank sentral
mendorong emas naik bersamaan naiknya suku bunga riil — perancu yang tidak tertangkap
model ini.

> **Kesimpulan yang bisa dipertanggungjawabkan:** skor makro menggambarkan **kondisi saat
> ini**, bukan ramalan harga. Skor rendah berarti angin makro sedang berlawanan — **bukan
> berarti harga emas pasti turun.** Kalimat ini ikut disertakan pada setiap respons `/macro`
> lewat field `interpretation`.

### 🔍 Deteksi rezim: sistem tahu kapan modelnya sendiri tidak berlaku

Skor makro bertumpu pada satu asumsi — suku bunga riil naik menekan emas. Asumsi itu
benar **sebagian besar waktu**, tetapi tidak selalu. Sistem yang jujur harus tahu kapan
modelnya sedang tidak berlaku, lalu mengatakannya.

Modul ini mengukur korelasi bergulir 6 bulan antara perubahan suku bunga riil dan imbal
hasil emas, lalu **menyesuaikan bobot secara otomatis**:

| Status | Korelasi | Seberapa sering* | Bobot makro | Bobot teknikal |
|---|---|---|---|---|
| ✅ **Berlaku** | < −0,20 | 88% | 50% | 30% |
| ⚠️ **Melemah** | −0,20 s/d 0 | 8% | 35% | 40% |
| 🚨 **Putus** | ≥ 0 | 4% | **20%** | **50%** |
| ❓ Tak terukur | — | — | 35% | 40% |

\* diukur pada data 2016–2026; ambangnya diturunkan dari sebaran nyata, bukan ditebak.

Ketika hubungan putus, bertumpu 50% pada skor makro tidak bisa dibenarkan — perannya
dialihkan ke pergerakan harga yang tetap terukur apa adanya. Bila kesehatan hubungan
**tidak dapat diukur**, bobot makro juga diturunkan: gagal mengukur harus menurunkan
keyakinan, bukan diam-diam memakai bobot penuh.

Endpoint `GET /regime` memberi status ini kapan saja. Contoh keluaran nyata:

```
Hubungan makro BERLAKU
  korelasi -0,42 | pola jangka panjang -0,44 | median historis -0,44
  bobot: makro 50%, teknikal 30%, sentimen 20%
```

Inilah jawaban langsung atas kelemahan yang ditemukan pada pengujian model: periode
2022–2026, saat pembelian bank sentral mendorong emas naik bersamaan naiknya suku bunga
riil, kini **terdeteksi otomatis** dan bobotnya menyesuaikan sendiri.

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

### Sentimen emas: analisis per-klausa, bukan hitung kata

Kamus sentimen saham tidak bisa dipakai — bahkan sering terbalik artinya. Bagi saham
"resesi" adalah kabar buruk; bagi emas justru mendorong harga naik.

Menghitung kata positif/negatif secara terpisah ternyata **tidak cukup akurat**. Tiga
kegagalan nyata yang terukur:

| Judul berita | Hitung kata | Seharusnya |
|---|---|---|
| "Gold rises as **dollar weakens**" | netral ❌ | naik |
| "Treasury **yields climb**, pressuring gold" | netral ❌ | turun |
| "Emas naik menyusul kenaikan suku bunga **ditunda**" | turun ❌ | naik |

Penyebabnya: kata "dollar" dan "yields" diberi polaritas sendiri sehingga saling
meniadakan dengan kata arah di sekitarnya, dan negasi tidak dikenali sama sekali.

Sekarang kalimat dipecah menjadi klausa, lalu dinilai berdasarkan **apa yang bergerak dan
ke mana arahnya**:

- Klausa tentang **emas** → arah harga = arah sinyal
- Klausa tentang **penggerak berlawanan** (dolar, imbal hasil, suku bunga) → sinyalnya
  **kebalikan** arah tersebut
- Klausa tanpa arah → dinilai dari peristiwa (perang, krisis, bank sentral borong emas)
- **Negasi** ("ditunda", "batal", "postponed") membalik arah klausa

Hasil pada 10 judul uji: **10/10 benar** (sebelumnya 7/10). Setiap penilaian menyertakan
field `reason` sehingga bisa ditelusuri, bukan kotak hitam.

Catatan: kata "rate" telanjang sengaja tidak dijadikan penggerak — *"inflation rate
rises"* bullish untuk emas, sedangkan *"interest rate rises"* bearish. Hanya frasa yang
jelas merujuk suku bunga yang didaftarkan.

### Kesegaran data: sumber tercepat dipakai lebih dulu

Indeks dolar broad FRED (`DTWEXBGS`) terbit mingguan dengan jeda — **terukur tertinggal 7
hari** dibanding indeks dolar ICE di Yahoo, padahal keduanya mengukur hal yang sama.
Karena itu untuk indikator ini sumber Yahoo dicoba lebih dulu, FRED jadi cadangan.
Sumber yang benar-benar terpakai selalu dicantumkan pada hasil.

**Umur data dihitung dalam hari kerja**, bukan hari kalender. Memakai hari kalender
membuat data hari Kamis salah ditandai basi setiap hari Senin, padahal pasar memang
tutup di akhir pekan.

**Waktu harga memakai waktu transaksi terakhir**, bukan indeks bar. Bar harian menandai
awal sesi, sehingga saat pasar berjalan sistem akan salah melaporkan harga "berumur 8
jam" padahal baru saja bergerak. Field `basis` menyatakan dasar waktu yang dipakai.

### Jam pasar & kesegaran harga

Emas berdagang hampir 24 jam (Minggu 18:00 – Jumat 17:00 waktu New York, dengan jeda
harian). Bila pasar tutup, sistem **menyatakannya terang-terangan** beserta umur harga
terakhir — bukan menampilkan harga penutupan seolah harga sedang berjalan.

## 🧪 Uji Mundur (Backtest) — bukti, bukan klaim

Tanpa uji mundur, sistem bisa memberi skor 78/100 dengan meyakinkan tanpa ada bukti
bahwa skor 78 lebih baik daripada skor 40. Modul ini menjawabnya dengan angka.

### Tiga pengaman terhadap lookahead bias

Lookahead bias — diam-diam memakai informasi masa depan — membuat hasil uji tampak hebat
padahal mustahil ditiru. Justru berbahaya, karena pengguna mengira sistemnya terbukti.

1. **Indikator kausal.** EMA/RSI/MACD/ATR nilainya pada bar ke-i hanya bergantung pada
   bar 0..i, sehingga menghitung sekali secara vektor setara persis dengan menghitung
   ulang pada jendela terpotong.
2. **Support/Resistance versi kausal.** Versi langsung memakai pivot terpusat; di
   backtest pivot hanya dikonfirmasi setelah seluruh jendelanya berlalu. Ada test yang
   memastikan hasilnya **sama persis dengan yang dihitung sistem live pada tanggal itu**.
3. **Masuk pada bar berikutnya.** Sinyal muncul pada penutupan bar ke-i, posisi dibuka
   pada **pembukaan bar ke-i+1** — bukan pada harga yang sudah diketahui.

Test kunci: `test_scores_do_not_change_when_future_bars_are_added` — skor pada bar ke-i
harus identik, ada atau tidak ada data sesudahnya. Bila menambah bar masa depan mengubah
skor masa lalu, berarti skor itu mengintip.

### Asumsi konservatif

- Bila stop loss dan target tersentuh pada bar yang sama, data harian tidak memberi tahu
  urutannya → diasumsikan **stop loss yang kena** (pesimistis, bukan optimistis).
- Posisi tidak menumpuk; satu posisi selesai dulu sebelum yang berikutnya.
- **Belum** memperhitungkan biaya transaksi, pajak, dan slippage.
- Hanya skor **teknikal** yang diuji — fundamental dan sentimen tidak punya riwayat yang
  bisa diuji mundur secara jujur.

### Perbandingan yang adil

Membandingkan hasil saja menyesatkan, karena strategi hanya terpapar pasar sebagian
waktu. Karena itu laporan menampilkan **hasil, penurunan terdalam, hasil per satuan
risiko, dan persentase waktu terpapar** — untuk strategi maupun beli-dan-tahan.

Hasil uji sungguhan (10 tahun, per Juli 2026):

| Simbol | Transaksi | Win rate | Faktor profit | Hasil | Beli-tahan | Penurunan | Beli-tahan | Efisiensi |
|---|---|---|---|---|---|---|---|---|
| SPY | 105 | 43,8% | 1,79 | 156,8% | 208,1% | −18,1% | −34,1% | **8,65 vs 6,10** |
| GLD | 105 | 47,6% | 1,78 | 159,7% | 220,5% | −17,6% | −26,4% | **9,07 vs 8,35** |
| GC=F | 122 | 48,4% | 1,67 | 158,5% | 231,3% | −22,8% | −25,1% | 6,96 vs 9,23 |

### Kenapa win rate hanya 44%? Karena memang seharusnya begitu

Win rate 44% terlihat buruk bila dibandingkan dengan 100%. Pembanding yang benar adalah
**titik masuk acak pada aturan keluar yang sama**. Dengan target dua kali lebih jauh
daripada stop loss, harga harus bergerak dua kali lebih jauh untuk menang — sehingga win
rate rendah adalah konsekuensi matematis, bukan tanda sistem rusak.

| R:R | Win rate sinyal | Win rate masuk **acak** | Selisih | Total hasil |
|---|---|---|---|---|
| 1 : 1 | 61,5% | 58,7% | +2,9 pp | 227,6% |
| 2 : 1 | 43,8% | 44,5% | −0,7 pp | 156,8% |
| 3 : 1 | 44,0% | 40,2% | +3,8 pp | 218,1% |

Perhatikan baris R:R 0,5 pada pengujian lain: win rate **72%** (terlihat hebat) tetapi
total hasil justru **paling rendah** (94,6%). **Win rate tinggi ≠ lebih untung.**

### Temuan paling jujur: keunggulan sinyal BELUM terbukti

Dari 9 pengujian (3 aset × 3 rasio imbal-risiko), 8 menunjukkan selisih positif terhadap
masuk acak — tetapi **setiap selisih masih berada di dalam rentang kebetulan** (di bawah
dua simpangan baku garis acak, ±3–5 poin persen).

Kesimpulan yang bisa dipertanggungjawabkan:

> Keuntungan sistem ini **terutama berasal dari manajemen risiko** — stop loss berbasis
> ATR yang memotong kerugian cepat dan rasio imbal-risiko yang membiarkan keuntungan
> berjalan — **bukan dari ketepatan sinyal dalam memilih waktu masuk.**

Karena itu `edge_is_significant` disertakan pada hasil, dan dashboard **menolak menyebut
selisih kecil sebagai keunggulan**. Sistem yang jujur harus berani mengatakan
"ini belum terbukti" tentang dirinya sendiri.

**Bacaan lengkapnya:** faktor profit di atas 1,5 pada ketiga aset menunjukkan hasil
positif yang konsisten. Namun **beli-dan-tahan tetap unggul dari sisi hasil mentah**
selama dekade pasar naik ini. Kelebihan strategi ada pada **risiko yang jauh lebih
rendah** — pada SPY, penurunan terdalamnya separuh dari beli-dan-tahan.

### Kalibrasi ukuran posisi

Selama ini `win_rate` diketik manual, sehingga Kelly Criterion menghitung memakai angka
karangan. Endpoint `/backtest` mengembalikan `calibration` berisi win rate terukur dan
Reward:Risk nyata — atau **menolak memberi angka** bila transaksinya di bawah 30, karena
sampel sekecil itu tidak layak jadi dasar ukuran posisi.

> Temuan nyata: win rate sesungguhnya **43–48%**, bukan 55% yang biasa diisi. Artinya
> ukuran posisi yang selama ini dihitung **terlalu besar**. Dashboard memberi peringatan
> otomatis bila angka yang Anda pakai menyimpang dari hasil uji.

## 📜 Riwayat Skor & Pemberitahuan Otomatis

Tanpa riwayat, setiap analisis berdiri sendiri: Anda tahu skor emas hari ini 28, tetapi
tidak tahu apakah itu **turun dari 60** minggu lalu atau **naik dari 15**. Arah pergerakan
sering lebih berguna daripada angkanya hari ini.

Riwayat disimpan di **SQLite** — satu berkas, tanpa server, ikut berpindah bersama folder
proyek. Dipilih agar pengguna yang menjalankan lewat satu klik tidak perlu memasang basis
data apa pun.

### Pemberitahuan hanya saat ada yang benar-benar berubah

Pemberitahuan yang terlalu sering membuat orang berhenti membacanya; yang terlambat tidak
berguna. Aturan yang memicu peringatan:

| Kejadian | Tingkat | Contoh |
|---|---|---|
| Sinyal berpindah | 🚨 Tinggi | `sinyal berubah SELL → BUY` |
| Hubungan makro putus | 🚨 Tinggi | `hubungan makro normal → putus` |
| Skor melewati ambang keputusan | ⚠️ Sedang | `skor naik melewati 55 (zona beli)` |
| Skor bergerak tajam (≥10 poin) | ⚠️ Sedang | `skor bergerak +12,4 poin` |
| Kelengkapan data menurun | ℹ️ Rendah | `kelengkapan data makro turun 100% → 75%` |

Setiap peringatan membawa **nilai sebelum dan sesudah**, sehingga bisa diperiksa — bukan
sekadar klaim "ada perubahan". Rekaman pertama sengaja **tidak** memicu pemberitahuan:
merekam untuk pertama kali bukan sebuah perubahan.

### Agar tidak perlu membuka aplikasi

```bash
python scripts/watch.py                    # emas, tiap 60 menit
python scripts/watch.py --interval 30 --stocks BBCA.JK TLKM.JK
python scripts/watch.py --once             # sekali jalan
```

Pemantau merekam berkala dan **hanya berbicara ketika ada perubahan**. Untuk menerimanya
di ponsel, isi `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` di `.env` (buat bot lewat
@BotFather). Tanpa kredensial itu, pengiriman **dilaporkan dilewati** — bukan
berpura-pura berhasil.

## 🧮 Formula Risk Engine (Section 5 Blueprint)

1. **Stop loss berbasis volatilitas** — `SL = Entry − (k × ATR)`, k = 1.5–2.0
2. **Risk-based position sizing** — `Lembar = (Modal × Risiko%) ÷ (Entry − SL)`
3. **Fractional Kelly** — `f* = c × ((W·R − (1−W)) ÷ R)`, c = 0.25, di-clamp ≥ 0
4. Konversi ke satuan pasar, dibatasi maksimal 100% modal:
   - Saham IDX: **lot bulat** (1 lot = 100 lembar), mata uang IDR
   - Emas: **troy ounce pecahan** (mis. 1,3839 oz), mata uang USD

### Dua penyimpangan sadar dari rumus mentah blueprint

**1. Batas risiko benar-benar menjadi batas.** Rumus blueprint mengalikan ukuran posisi
dengan `(1 + f*)` **setelah** batas risiko dihitung, sehingga risiko sebenarnya melampaui
angka yang diminta pengguna:

```
Diminta  : risiko maksimal 2,00%  =  Rp 2.000.000
Kenyataan: risiko             2,16%  =  Rp 2.160.000   ← melampaui 8%
```

Parameter bernama "risiko maksimal" tidak boleh dilampaui, jadi `cap_at_max_risk=True`
menjadi perilaku bawaan. Perilaku blueprint asli tetap tersedia lewat
`cap_at_max_risk=False`. Apa pun pilihannya, `actual_risk_pct` dan `within_risk_budget`
selalu dilaporkan — angkanya tidak pernah disembunyikan.

**2. Kelly tidak berjalan di atas tebakan.** `win_rate` bawaannya `None` → Kelly tidak
diterapkan sama sekali. Membesarkan posisi hanya sah bila keunggulan sudah **diukur**,
dan uji mundur menunjukkan keunggulan pemilihan waktu masuk **belum terbukti**. Isi
`win_rate` hanya dengan hasil `/backtest`.

| | Sebelum | Sesudah |
|---|---|---|
| Ukuran posisi | 432 lot | **400 lot** |
| Kerugian maksimal | Rp 2.160.000 | **Rp 2.000.000** |
| Risiko nyata | 2,16% (melampaui) | **2,00% (sesuai)** |
| Dasar Kelly | tebakan 55% | tidak dipakai sampai terukur |

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
