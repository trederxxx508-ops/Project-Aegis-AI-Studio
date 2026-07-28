"""Macro Engine — kondisi makro ekonomi yang menggerakkan harga emas.

Sumber utama: FRED (Federal Reserve Bank of St. Louis) lewat endpoint CSV
publik, sehingga **tidak memerlukan kunci API**. Bila FRED tidak terjangkau,
tersedia proksi dari Yahoo Finance untuk sebagian indikator.

Prinsip kejujuran data yang dipegang modul ini:

1. Setiap angka membawa asal-usulnya: nilai, tanggal observasi, sumber, dan
   umur data dalam hari.
2. Indikator yang gagal diambil dilaporkan sebagai tidak tersedia dan diberi
   nilai netral — tidak pernah ditebak lalu disajikan seolah pasti.
3. ``completeness_pct`` memberi tahu berapa persen komponen yang benar-benar
   berhasil diambil, agar pengguna tahu seberapa utuh skornya.

Mengapa suku bunga riil paling menentukan: emas tidak memberi bunga. Ketika
suku bunga riil (bunga dikurangi inflasi) negatif, memegang uang tunai justru
kehilangan daya beli, sehingga emas menjadi relatif menarik. Hubungan ini
adalah pendorong harga emas yang paling konsisten secara historis.
"""
from __future__ import annotations

import csv
import io

import numpy as np
from datetime import date, datetime, timezone
from typing import Optional

from services import cache

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FRED_TTL_SECONDS = 3600  # data harian; sekali per jam lebih dari cukup
HTTP_TIMEOUT = 20

# Seri FRED yang dipakai
SERIES = {
    "real_yield_10y": "DFII10",     # Suku bunga riil 10 tahun (TIPS) — harian
    "breakeven_10y": "T10YIE",      # Ekspektasi inflasi 10 tahun — harian
    "nominal_yield_10y": "DGS10",   # Imbal hasil obligasi 10 tahun — harian
    "dollar_index": "DTWEXBGS",     # Indeks dolar broad — harian
    "fed_funds_rate": "DFF",        # Suku bunga acuan The Fed — harian
    "cpi": "CPIAUCSL",              # Indeks harga konsumen AS — bulanan
}

# Proksi Yahoo bila FRED tidak terjangkau (tidak ada padanan untuk suku bunga riil)
YAHOO_PROXY = {
    "nominal_yield_10y": "^TNX",
    "dollar_index": "DX-Y.NYB",
}

# Indikator yang datanya lebih cepat tersedia di Yahoo daripada di FRED.
# Indeks dolar broad FRED (DTWEXBGS) terbit mingguan dengan jeda — terukur
# tertinggal sekitar 7 hari dibanding indeks dolar ICE di Yahoo, sementara
# keduanya sama-sama mengukur kekuatan dolar. Karena kesegaran data adalah
# tujuan utama modul ini, sumber tercepat dicoba lebih dulu.
PREFER_YAHOO_FIRST = {"dollar_index"}

# Batas umur data sebelum ditandai basi, dihitung dalam **hari kerja**.
# Memakai hari kalender akan salah menandai data hari Kamis sebagai basi
# setiap hari Senin, padahal pasar memang tutup di akhir pekan.
STALE_AFTER_BUSINESS_DAYS = {
    "real_yield_10y": 3,
    "breakeven_10y": 3,
    "nominal_yield_10y": 3,
    "dollar_index": 4,
    "fed_funds_rate": 3,
    "cpi": 32,
}

LABELS = {
    "real_yield_10y": "Suku bunga riil 10 thn",
    "breakeven_10y": "Ekspektasi inflasi 10 thn",
    "nominal_yield_10y": "Imbal hasil obligasi 10 thn",
    "dollar_index": "Indeks dolar",
    "fed_funds_rate": "Suku bunga acuan The Fed",
    "cpi": "Indeks harga konsumen AS",
}


# ---------------------------------------------------------------------------
# Pengambilan data
# ---------------------------------------------------------------------------

def _parse_fred_csv(text: str) -> list[tuple[date, float]]:
    """Ubah CSV FRED menjadi deret (tanggal, nilai). Nilai '.' berarti kosong."""
    rows: list[tuple[date, float]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise ValueError("Format CSV FRED tidak dikenali.")
    for row in reader:
        if len(row) < 2:
            continue
        raw_date, raw_value = row[0].strip(), row[1].strip()
        if not raw_date or raw_value in ("", "."):
            continue  # FRED memakai '.' untuk hari libur / data belum terbit
        try:
            rows.append((datetime.strptime(raw_date, "%Y-%m-%d").date(), float(raw_value)))
        except ValueError:
            continue
    if not rows:
        raise ValueError("Tidak ada observasi valid dalam CSV FRED.")
    return rows


# Sebagian jaringan/CDN memperlakukan User-Agent berbeda untuk unduhan CSV:
# UA menyerupai browser bisa digantung oleh penyaring bot, sementara UA
# pustaka biasa dilayani normal — di jaringan lain bisa sebaliknya. Karena itu
# beberapa varian dicoba berurutan sebelum menyerah.
USER_AGENTS = (
    "curl/8.0",
    "python-requests/2.31",
    "Mozilla/5.0 (compatible; ProjectAegis/1.0)",
)


def fetch_fred_series(series_id: str, use_cache: bool = True) -> list[tuple[date, float]]:
    """Ambil satu seri FRED lewat endpoint CSV publik (tanpa kunci API)."""

    def _download() -> list[tuple[date, float]]:
        import requests

        url = FRED_CSV_URL.format(series_id=series_id)
        last_error: Optional[Exception] = None
        for agent in USER_AGENTS:
            try:
                resp = requests.get(
                    url,
                    timeout=HTTP_TIMEOUT,
                    headers={"User-Agent": agent, "Accept": "text/csv,*/*"},
                )
                resp.raise_for_status()
                return _parse_fred_csv(resp.text)
            except Exception as exc:
                last_error = exc
                continue
        raise ConnectionError(
            f"Gagal mengambil seri '{series_id}' dari FRED setelah "
            f"{len(USER_AGENTS)} percobaan. Kesalahan terakhir: {last_error}"
        )

    if use_cache:
        return cache.get_or_compute(f"fred:{series_id}", FRED_TTL_SECONDS, _download)
    return _download()


def _fetch_yahoo_proxy(symbol: str, use_cache: bool = True) -> list[tuple[date, float]]:
    """Proksi cadangan dari Yahoo Finance untuk indikator tertentu."""
    from services.market_data import fetch_chart_api

    def _download() -> list[tuple[date, float]]:
        df = fetch_chart_api(symbol, range_="1y", interval="1d")
        return [(idx.date(), float(val)) for idx, val in df["Close"].dropna().items()]

    if use_cache:
        return cache.get_or_compute(f"yahoo_macro:{symbol}", FRED_TTL_SECONDS, _download)
    return _download()


# ---------------------------------------------------------------------------
# Indikator + asal-usul
# ---------------------------------------------------------------------------

def _change_over(series: list[tuple[date, float]], lookback: int) -> Optional[float]:
    """Selisih nilai terakhir terhadap ``lookback`` observasi sebelumnya."""
    if len(series) <= lookback:
        return None
    return series[-1][1] - series[-1 - lookback][1]


def _average_of_last(series: list[tuple[date, float]], n: int) -> Optional[float]:
    if len(series) < n:
        return None
    return sum(v for _, v in series[-n:]) / n


def _business_days_between(start: date, end: date) -> int:
    """Jumlah hari kerja antara dua tanggal (akhir pekan tidak dihitung)."""
    if end <= start:
        return 0
    return int(np.busday_count(start, end))


def load_indicator(key: str, use_cache: bool = True) -> dict:
    """Ambil satu indikator lengkap dengan asal-usul dan status kesegaran.

    Sumber dicoba berurutan dari yang paling cepat tersedia untuk indikator
    tersebut; sumber yang benar-benar terpakai selalu dicantumkan.
    """
    today = datetime.now(timezone.utc).date()
    series_id = SERIES[key]
    proxy = YAHOO_PROXY.get(key)

    attempts: list[tuple[str, callable]] = []
    if key in PREFER_YAHOO_FIRST and proxy:
        attempts.append((f"Yahoo Finance ({proxy})", lambda: _fetch_yahoo_proxy(proxy, use_cache=use_cache)))
        attempts.append((f"FRED ({series_id}) — cadangan", lambda: fetch_fred_series(series_id, use_cache=use_cache)))
    else:
        attempts.append((f"FRED ({series_id})", lambda: fetch_fred_series(series_id, use_cache=use_cache)))
        if proxy:
            attempts.append((f"Yahoo Finance ({proxy}) — cadangan", lambda: _fetch_yahoo_proxy(proxy, use_cache=use_cache)))

    series: Optional[list[tuple[date, float]]] = None
    source = attempts[0][0]
    errors: list[str] = []

    for label, fetch in attempts:
        try:
            series = fetch()
            source = label
            break
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if series is None:
        return {
            "key": key,
            "label": LABELS[key],
            "available": False,
            "value": None,
            "as_of": None,
            "age_days": None,
            "age_business_days": None,
            "stale": None,
            "source": source,
            "error": "; ".join(errors),
        }

    as_of, value = series[-1]
    age_business = _business_days_between(as_of, today)
    return {
        "key": key,
        "label": LABELS[key],
        "available": True,
        "value": round(value, 4),
        "as_of": as_of.isoformat(),
        "age_days": (today - as_of).days,
        "age_business_days": age_business,
        "stale": age_business > STALE_AFTER_BUSINESS_DAYS.get(key, 4),
        "source": source,
        "change_1m": _change_over(series, 21),
        "change_3m": _change_over(series, 63),
        "avg_50": _average_of_last(series, 50),
        "observations": len(series),
        "error": None,
    }


def cpi_year_over_year(use_cache: bool = True) -> dict:
    """Inflasi tahunan AS dari indeks CPI (perubahan 12 bulan)."""
    info = load_indicator("cpi", use_cache=use_cache)
    if not info["available"]:
        return {**info, "yoy_pct": None}
    try:
        series = fetch_fred_series(SERIES["cpi"], use_cache=use_cache)
        if len(series) < 13:
            return {**info, "yoy_pct": None}
        latest, year_ago = series[-1][1], series[-13][1]
        yoy = (latest / year_ago - 1) * 100 if year_ago else None
        return {**info, "yoy_pct": round(yoy, 2) if yoy is not None else None}
    except Exception:
        return {**info, "yoy_pct": None}


# ---------------------------------------------------------------------------
# Skor makro
# ---------------------------------------------------------------------------

def _score_real_yield(ind: dict) -> tuple[float, float, str]:
    """Suku bunga riil: 12 poin level + 28 poin arah. Maksimum 40.

    Pembagian bobot ini diubah setelah pengujian terhadap data 2016-2026
    (lihat ``scripts/validate_macro_relationship.py``, silakan jalankan
    sendiri). Temuannya:

    - **Arah** perubahan suku bunga riil berkorelasi negatif dengan imbal
      hasil emas (-0,31 harian sampai -0,48 bulanan) — sesuai teori.
    - **Level** suku bunga riil TIDAK mendukung teori pada sampel tersebut.
      Justru saat level berada di 2-3% (yang model lama nilai buruk), imbal
      hasil emas tiga bulan berikutnya rata-rata +8,15%, sementara saat level
      di bawah 0% (yang model lama nilai terbaik) hanya +1,20%.

    Karena itu bobot level diturunkan drastis alih-alih dibalik: membalik
    berdasarkan satu rezim pasar berisiko menjadi curve-fitting, sementara
    mempertahankan bobot besar pada asumsi yang tidak didukung data sama
    saja dengan percaya diri tanpa dasar.
    """
    level_max, trend_max = 12.0, 28.0
    if not ind["available"]:
        return level_max / 2 + trend_max / 2, level_max + trend_max, "tidak tersedia"

    v = ind["value"]
    if v < 0:
        level, desc = level_max, "negatif secara teori mendukung emas"
    elif v < 1:
        level, desc = level_max * 0.75, "rendah"
    elif v < 2:
        level, desc = level_max * 0.5, "sedang"
    elif v < 3:
        level, desc = level_max * 0.25, "tinggi (level bukan peramal yang terbukti)"
    else:
        level, desc = level_max * 0.12, "sangat tinggi (level bukan peramal yang terbukti)"

    change = ind.get("change_3m")
    if change is None:
        trend = trend_max / 2
    elif change < -0.15:
        trend, desc = trend_max, f"{desc}, dan sedang turun"
    elif change > 0.15:
        trend, desc = 0.0, f"{desc}, dan sedang naik"
    else:
        trend, desc = trend_max / 2, f"{desc}, cenderung datar"
    return level + trend, level_max + trend_max, desc


def _score_dollar(ind: dict) -> tuple[float, float, str]:
    """Indeks dolar: emas dihargai dalam dolar, jadi arahnya berlawanan. 25 poin."""
    total_max = 25.0
    if not ind["available"]:
        return total_max / 2, total_max, "tidak tersedia"

    score = 0.0
    avg50 = ind.get("avg_50")
    if avg50:
        below = ind["value"] < avg50
        score += 13.0 if below else 0.0
        desc = "di bawah rata-rata 50 hari — mendukung emas" if below else \
               "di atas rata-rata 50 hari — menekan emas"
    else:
        score += 6.5
        desc = "rata-rata 50 hari belum tersedia"

    change = ind.get("change_3m")
    if change is None:
        score += 6.0
    elif change < 0:
        score += 12.0
        desc += ", sedang melemah"
    else:
        desc += ", sedang menguat"
    return score, total_max, desc


def _score_breakeven(ind: dict) -> tuple[float, float, str]:
    """Ekspektasi inflasi pasar: naik = emas sebagai pelindung nilai. 20 poin."""
    total_max = 20.0
    if not ind["available"]:
        return total_max / 2, total_max, "tidak tersedia"

    v = ind["value"]
    if v >= 2.5:
        level, desc = 10.0, "tinggi — inflasi diperkirakan panas"
    elif v >= 2.0:
        level, desc = 7.0, "moderat — sesuai target bank sentral"
    elif v >= 1.5:
        level, desc = 4.0, "rendah"
    else:
        level, desc = 2.0, "sangat rendah — risiko deflasi"

    change = ind.get("change_3m")
    if change is None:
        trend = 5.0
    elif change > 0.05:
        trend, desc = 10.0, f"{desc}, dan sedang naik"
    elif change < -0.05:
        trend, desc = 0.0, f"{desc}, dan sedang turun"
    else:
        trend, desc = 5.0, f"{desc}, cenderung datar"
    return level + trend, total_max, desc


def _score_nominal_yield(ind: dict) -> tuple[float, float, str]:
    """Imbal hasil obligasi: pesaing emas. Turun = mendukung emas. 15 poin."""
    total_max = 15.0
    if not ind["available"]:
        return total_max / 2, total_max, "tidak tersedia"

    change = ind.get("change_3m")
    if change is None:
        return total_max / 2, total_max, "arah belum bisa dinilai"
    if change < -0.2:
        return total_max, total_max, "turun tajam — mendukung emas"
    if change < 0:
        return total_max * 0.75, total_max, "sedikit turun — mendukung emas"
    if change < 0.2:
        return total_max * 0.4, total_max, "relatif datar"
    return 0.0, total_max, "naik tajam — menekan emas"


def macro_score(use_cache: bool = True) -> dict:
    """Hitung Skor Makro 0-100 untuk emas, lengkap dengan asal-usul tiap angka.

    Komponen yang gagal diambil diberi nilai netral (separuh) dan dicatat,
    sehingga skor tetap bisa dihitung tanpa berpura-pura datanya lengkap.
    """
    indicators = {
        key: load_indicator(key, use_cache=use_cache)
        for key in ("real_yield_10y", "dollar_index", "breakeven_10y", "nominal_yield_10y")
    }
    context = {
        "fed_funds_rate": load_indicator("fed_funds_rate", use_cache=use_cache),
        "cpi": cpi_year_over_year(use_cache=use_cache),
    }

    scorers = {
        "real_yield": (_score_real_yield, indicators["real_yield_10y"]),
        "dollar": (_score_dollar, indicators["dollar_index"]),
        "inflation_expectation": (_score_breakeven, indicators["breakeven_10y"]),
        "bond_yield": (_score_nominal_yield, indicators["nominal_yield_10y"]),
    }

    breakdown: dict[str, dict] = {}
    total = 0.0
    notes: list[str] = []
    for name, (fn, ind) in scorers.items():
        points, max_points, desc = fn(ind)
        total += points
        breakdown[name] = {
            "label": ind["label"],
            "points": round(points, 2),
            "max_points": max_points,
            "reading": ind["value"],
            "as_of": ind["as_of"],
            "source": ind["source"],
            "available": ind["available"],
            "interpretation": desc,
        }
        if not ind["available"]:
            notes.append(f"{ind['label']}: data tidak tersedia — dinilai netral.")
        elif ind["stale"]:
            notes.append(
                f"{ind['label']}: data terakhir {ind['as_of']} "
                f"({ind['age_business_days']} hari kerja lalu) — lebih lama dari biasanya."
            )

    available = sum(1 for _, ind in scorers.values() if ind["available"])
    completeness = round(available / len(scorers) * 100, 1)

    return {
        "score": round(min(100.0, total), 2),
        "interpretation": (
            "Skor makro menggambarkan KONDISI SAAT INI, bukan ramalan harga. "
            "Hubungan sewaktu antara suku bunga riil/dolar dengan emas terbukti "
            "kuat (korelasi perubahan -0,31 s/d -0,48 pada data 2016-2026), "
            "tetapi daya ramalnya terhadap imbal hasil ke depan TIDAK terbukti. "
            "Skor rendah berarti angin makro sedang berlawanan — bukan berarti "
            "harga emas pasti turun."
        ),
        "evidence_script": "scripts/validate_macro_relationship.py",
        "breakdown": breakdown,
        "completeness_pct": completeness,
        "components_available": available,
        "components_total": len(scorers),
        "notes": notes,
        "context": context,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
