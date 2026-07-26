"""Sentiment Engine khusus emas — berbasis klausa, bukan sekadar hitung kata.

Kamus sentimen saham tidak bisa dipakai untuk emas dan sering **terbalik
artinya**: bagi saham "krisis" adalah kabar buruk, bagi emas justru mendorong
harga naik karena emas berperan sebagai aset lindung nilai.

Menghitung kata positif/negatif secara terpisah ternyata tidak cukup akurat.
Tiga kegagalan nyata yang mendorong perombakan modul ini:

    "Gold rises as dollar weakens"        -> netral (salah; seharusnya naik)
    "Treasury yields climb, pressuring gold" -> netral (salah; seharusnya turun)
    "Harga emas naik menyusul kenaikan suku bunga ditunda" -> turun (salah)

Penyebabnya: kata seperti "dollar" dan "yields" diberi polaritas sendiri
sehingga saling meniadakan dengan kata arah di sekitarnya, dan negasi
("ditunda", "batal") tidak dikenali sama sekali.

Pendekatan sekarang: kalimat dipecah menjadi klausa, lalu tiap klausa dinilai
berdasarkan **apa yang bergerak dan ke mana arahnya**:

- Klausa tentang EMAS      : arah harga = arah sinyal
- Klausa tentang PENGGERAK BERLAWANAN (dolar, imbal hasil, suku bunga):
  arah sinyal adalah **kebalikan** arahnya — dolar melemah berarti emas naik
- Klausa tanpa arah        : dinilai dari peristiwa (perang, krisis, bank sentral)
- Negasi ("ditunda", "batal", "urung") membalik arah klausa
"""
from __future__ import annotations

import re

# --- Subjek kalimat -------------------------------------------------------
GOLD_TERMS = ("gold", "bullion", "xau", "emas", "logam mulia")

# Penggerak yang hubungannya BERLAWANAN dengan emas: bila mereka naik,
# emas cenderung tertekan, dan sebaliknya.
# Catatan: kata "rate" telanjang sengaja TIDAK dimasukkan. "Inflation rate
# rises" berarti inflasi naik — bullish untuk emas — sedangkan "interest rate
# rises" bearish. Hanya frasa yang jelas merujuk suku bunga yang didaftarkan.
INVERSE_DRIVERS = (
    "dollar", "greenback", "dxy", "yield", "yields", "treasury", "bond",
    "real rate", "real yield", "interest rate", "interest rates",
    "policy rate", "rate cut", "rate cuts", "rate hike", "rate hikes",
    "fed funds", "borrowing cost",
    "dolar", "imbal hasil", "obligasi", "suku bunga", "bunga acuan",
)

# --- Arah gerak -----------------------------------------------------------
UP_WORDS = (
    "rise", "rises", "rising", "rose", "climb", "climbs", "climbing", "surge",
    "surges", "jump", "jumps", "soar", "soars", "gain", "gains", "advance",
    "strengthen", "strengthens", "stronger", "strength", "higher", "hike",
    "hikes", "raise", "raises", "rally", "rallies", "up", "spike", "spikes",
    "naik", "menguat", "melonjak", "meningkat", "kenaikan", "penguatan",
    "melesat", "reli", "menanjak",
)
DOWN_WORDS = (
    "fall", "falls", "falling", "fell", "drop", "drops", "decline", "declines",
    "weaken", "weakens", "weaker", "weakness", "lower", "slip", "slips",
    "ease", "eases", "easing", "cut", "cuts", "slump", "tumble", "tumbles",
    "plunge", "plunges", "retreat", "sink", "sinks", "down", "softer",
    "turun", "melemah", "anjlok", "merosot", "menurun", "dipangkas",
    "pemangkasan", "pelemahan", "koreksi", "tertekan", "terkoreksi",
)

# Kata yang membalik makna klausa
NEGATORS = (
    "ditunda", "batal", "dibatalkan", "urung", "tidak", "belum", "tanpa",
    "postponed", "delayed", "cancelled", "canceled", "no longer", "not ",
    "unchanged", "holds", "hold steady", "pause", "paused", "menahan", "tahan",
)

# --- Peristiwa (dipakai bila klausa tidak punya arah harga) ---------------
EVENT_BULLISH = (
    "war", "conflict", "tension", "tensions", "invasion", "attack", "sanction",
    "sanctions", "crisis", "turmoil", "unrest", "geopolitical", "recession",
    "default", "collapse", "uncertainty", "fear", "fears", "safe haven",
    "haven", "hedge", "shutdown", "stimulus", "dovish", "inflation",
    "inflationary", "stagflation", "debasement", "central bank buying",
    "central banks", "reserves", "flight to safety", "banking crisis",
    "debt ceiling", "trade war", "escalates", "escalate",
    "perang", "konflik", "ketegangan", "serangan", "sanksi", "krisis",
    "resesi", "gejolak", "ketidakpastian", "aset aman", "lindung nilai",
    "inflasi", "stimulus", "bank sentral", "cadangan", "borong",
)
EVENT_BEARISH = (
    "hawkish", "tightening", "tighten", "taper", "tapering", "restrictive",
    "risk appetite", "risk-on", "optimism", "recovery", "rebound", "boom",
    "outflows", "profit taking", "higher for longer", "pressuring",
    "pressures", "pressure", "resilient", "selloff",
    "pengetatan", "optimisme", "pemulihan", "aksi jual", "ambil untung",
    "menekan", "tekanan", "arus keluar",
)

# Pemisah klausa: penghubung sebab-akibat dan tanda baca
CLAUSE_SPLIT = re.compile(
    r",|;|\.|\bas\b|\bafter\b|\bamid\b|\bwhile\b|\bwhen\b|\bon\b|\bdue to\b|"
    r"\bsetelah\b|\bmenyusul\b|\bkarena\b|\bakibat\b|\bseiring\b|\bsaat\b|\bimbas\b",
    flags=re.IGNORECASE,
)


def _contains(text: str, terms) -> bool:
    return any(t in text for t in terms)


def _direction(text: str) -> int:
    """+1 bila klausa menyatakan kenaikan, -1 penurunan, 0 bila tak ada arah."""
    up = sum(1 for w in UP_WORDS if re.search(rf"\b{re.escape(w)}\b", text))
    down = sum(1 for w in DOWN_WORDS if re.search(rf"\b{re.escape(w)}\b", text))
    if up == down:
        return 0
    return 1 if up > down else -1


def _score_clause(clause: str) -> tuple[float, str]:
    """Nilai satu klausa: (-1..1, alasan singkat)."""
    text = clause.strip().lower()
    if not text:
        return 0.0, ""

    negated = _contains(text, NEGATORS)
    direction = _direction(text)
    if negated and direction != 0:
        direction = -direction

    about_gold = _contains(text, GOLD_TERMS)
    about_inverse = _contains(text, INVERSE_DRIVERS)

    if direction != 0:
        # Penggerak berlawanan diprioritaskan bila klausa tidak menyebut emas
        if about_inverse and not about_gold:
            return float(-direction), (
                f"{'kenaikan' if direction > 0 else 'penurunan'} penggerak berlawanan"
                + (" (dinegasikan)" if negated else "")
            )
        if about_gold:
            return float(direction), (
                f"emas {'naik' if direction > 0 else 'turun'}"
                + (" (dinegasikan)" if negated else "")
            )
        if about_inverse:
            # Menyebut keduanya: arah biasanya milik emas pada judul berita emas
            return float(direction), "emas & penggerak disebut bersama"

    # Tanpa arah harga -> nilai dari peristiwa
    bull = sum(1 for w in EVENT_BULLISH if w in text)
    bear = sum(1 for w in EVENT_BEARISH if w in text)
    if bull or bear:
        pol = (bull - bear) / (bull + bear)
        if negated:
            pol = -pol
        return pol, f"peristiwa ({bull} pendukung / {bear} penekan)"
    return 0.0, ""


def score_gold_headlines(headlines: list[str]) -> dict:
    """Skor sentimen emas 0-100 dari daftar judul berita.

    50 berarti netral; di atas 50 mendukung kenaikan emas, di bawah 50 menekan.
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
        clauses = [c for c in CLAUSE_SPLIT.split(title) if c and c.strip()]
        scores, reasons = [], []
        for clause in clauses:
            pol, why = _score_clause(clause)
            if why:
                scores.append(pol)
                reasons.append(why)

        polarity = sum(scores) / len(scores) if scores else 0.0
        polarity = max(-1.0, min(1.0, polarity))
        polarities.append(polarity)
        details.append({
            "headline": title,
            "polarity": round(polarity, 2),
            "bullish_hits": sum(1 for s in scores if s > 0),
            "bearish_hits": sum(1 for s in scores if s < 0),
            "reason": "; ".join(reasons) if reasons else "tidak ada penanda arah",
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
