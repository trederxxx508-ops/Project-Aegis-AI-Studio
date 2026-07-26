"""Sentiment Engine khusus emas.

Kamus sentimen saham tidak bisa dipakai untuk emas — bahkan sering
**terbalik artinya**. Bagi saham, "krisis" dan "resesi" adalah kabar buruk;
bagi emas, keduanya justru mendorong harga naik karena emas berperan sebagai
aset lindung nilai (safe haven).

Karena itu modul ini memakai kamus tersendiri, disusun dari faktor yang
secara historis menggerakkan harga emas:

- Naik : ketegangan geopolitik, krisis, inflasi, pemangkasan suku bunga,
         pembelian bank sentral, pelemahan dolar
- Turun: pengetatan moneter, kenaikan suku bunga, penguatan dolar,
         selera risiko tinggi (dana mengalir ke saham)
"""
from __future__ import annotations

# Kata yang secara historis berasosiasi dengan KENAIKAN harga emas
GOLD_BULLISH = {
    # Geopolitik & krisis (English)
    "war", "conflict", "tension", "tensions", "invasion", "attack", "strike",
    "sanction", "sanctions", "crisis", "turmoil", "unrest", "geopolitical",
    "recession", "slowdown", "default", "downgrade", "collapse", "crash",
    "uncertainty", "fear", "haven", "safehaven", "hedge", "shutdown",
    # Moneter yang mendukung emas
    "cut", "cuts", "dovish", "easing", "stimulus", "qe", "weaker", "weakens",
    "inflation", "inflationary", "stagflation", "devaluation", "debasement",
    # Permintaan fisik
    "buying", "accumulate", "accumulation", "reserves", "demand", "inflows",
    "record", "rally", "surge", "soar", "soars", "climb", "climbs", "jumps",
    # Indonesia
    "perang", "konflik", "ketegangan", "serangan", "sanksi", "krisis",
    "resesi", "gejolak", "ketidakpastian", "aman", "lindung", "inflasi",
    "pangkas", "pelonggaran", "stimulus", "melemah", "borong", "cadangan",
    "melonjak", "rekor", "naik", "menguat", "permintaan",
}

# Kata yang secara historis berasosiasi dengan PENURUNAN harga emas
GOLD_BEARISH = {
    # Moneter yang menekan emas
    "hike", "hikes", "hawkish", "tightening", "tighten", "taper", "tapering",
    "raise", "raises", "higher", "yields", "restrictive",
    # Dolar & selera risiko
    "dollar", "greenback", "stronger", "strengthens", "resilient", "riskon",
    "optimism", "recovery", "rebound", "boom", "outflows", "selloff",
    "profittaking", "correction", "retreat", "slump", "tumble", "tumbles",
    "falls", "drops", "declines", "plunge", "plunges", "weakness",
    # Indonesia
    "kenaikan", "menaikkan", "pengetatan", "hawkish", "suku",
    "dolar", "menguatnya", "pemulihan", "optimisme", "aksi", "ambil",
    "untung", "koreksi", "anjlok", "merosot", "turun", "tertekan", "jual",
}

# Frasa (dua kata) yang lebih spesifik daripada kata tunggal
GOLD_BULLISH_PHRASES = (
    "rate cut", "rate cuts", "safe haven", "central bank buying",
    "central banks", "flight to safety", "debt ceiling", "banking crisis",
    "pangkas suku bunga", "bank sentral", "aset aman", "lindung nilai",
    "krisis perbankan", "perang dagang",
)
GOLD_BEARISH_PHRASES = (
    "rate hike", "rate hikes", "strong dollar", "stronger dollar",
    "risk appetite", "profit taking", "higher for longer",
    "naik suku bunga", "kenaikan suku bunga", "dolar menguat",
    "ambil untung", "aksi jual",
)


def score_gold_headlines(headlines: list[str]) -> dict:
    """Skor sentimen emas 0-100 dari daftar judul berita.

    Skor 50 berarti netral. Di atas 50 mendukung kenaikan emas,
    di bawah 50 menekan.
    """
    if not headlines:
        return {
            "score": 50.0,
            "label": "NEUTRAL",
            "headline_count": 0,
            "details": [],
            "note": "Tidak ada berita — skor netral.",
        }

    details = []
    polarities = []
    for title in headlines:
        lowered = title.lower()
        tokens = {
            t.strip(".,!?:;()'\"-").lower() for t in lowered.split()
        }
        bull = len(tokens & GOLD_BULLISH)
        bear = len(tokens & GOLD_BEARISH)
        # Frasa diberi bobot dua kali karena lebih tidak ambigu
        bull += 2 * sum(1 for p in GOLD_BULLISH_PHRASES if p in lowered)
        bear += 2 * sum(1 for p in GOLD_BEARISH_PHRASES if p in lowered)

        polarity = 0.0 if (bull + bear) == 0 else (bull - bear) / (bull + bear)
        polarities.append(polarity)
        details.append({
            "headline": title,
            "polarity": round(polarity, 2),
            "bullish_hits": bull,
            "bearish_hits": bear,
        })

    avg = sum(polarities) / len(polarities)
    score = round(50 + avg * 50, 2)
    label = "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL"
    return {
        "score": score,
        "label": label,
        "headline_count": len(headlines),
        "details": details,
    }


def fetch_gold_headlines(limit: int = 20) -> list[str]:
    """Ambil judul berita terkait emas dari beberapa simbol terkait."""
    import yfinance as yf

    headlines: list[str] = []
    for symbol in ("GC=F", "GLD"):
        try:
            for item in (yf.Ticker(symbol).news or [])[:limit]:
                title = item.get("title") or (item.get("content") or {}).get("title")
                if title and title not in headlines:
                    headlines.append(str(title))
        except Exception:
            continue
    return headlines[:limit]


def gold_sentiment(extra_headlines: list[str] | None = None) -> dict:
    """Pipeline sentimen emas; aman terhadap kegagalan jaringan.

    ``extra_headlines`` memungkinkan pengguna menempelkan judul berita
    sendiri (mis. dari media Indonesia) untuk ikut dinilai.
    """
    headlines = list(extra_headlines or [])
    try:
        headlines.extend(h for h in fetch_gold_headlines() if h not in headlines)
    except Exception as exc:
        if not headlines:
            return {
                "score": 50.0,
                "label": "NEUTRAL",
                "headline_count": 0,
                "details": [],
                "note": f"Gagal mengambil berita ({exc}); skor netral dipakai.",
            }
    return score_gold_headlines(headlines)
