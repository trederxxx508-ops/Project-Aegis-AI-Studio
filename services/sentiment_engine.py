"""Sentiment Engine — skor sentimen berita per ticker (0-100).

Implementasi ringan berbasis lexicon keuangan (EN + ID) di atas judul
berita dari yfinance. Tanpa berita / tanpa jaringan, skor jatuh ke 50
(netral) sehingga pipeline analisis tetap berjalan.
"""
from __future__ import annotations

POSITIVE_WORDS = {
    # English
    "beat", "beats", "growth", "surge", "surges", "rally", "record", "profit",
    "profits", "upgrade", "upgraded", "bullish", "gain", "gains", "strong",
    "outperform", "buy", "dividend", "expansion", "expands", "rebound",
    "recovery", "soar", "soars", "jump", "jumps", "rise", "rises", "boost",
    "positive", "optimistic", "breakthrough", "wins", "award",
    # Indonesian
    "naik", "menguat", "laba", "untung", "tumbuh", "pertumbuhan", "rekor",
    "ekspansi", "dividen", "positif", "optimis", "melonjak", "melesat",
    "cuan", "akumulasi",
}

NEGATIVE_WORDS = {
    # English
    "miss", "misses", "loss", "losses", "fall", "falls", "drop", "drops",
    "plunge", "plunges", "downgrade", "downgraded", "bearish", "weak",
    "lawsuit", "fraud", "probe", "investigation", "layoff", "layoffs",
    "bankruptcy", "default", "sell", "underperform", "decline", "declines",
    "negative", "warning", "cut", "cuts", "slump", "crash", "risk",
    # Indonesian
    "turun", "melemah", "rugi", "kerugian", "anjlok", "merosot", "negatif",
    "pailit", "gagal", "denda", "sanksi", "phk", "koreksi", "tekanan",
}


def fetch_news_headlines(ticker: str, limit: int = 15) -> list[str]:
    """Ambil judul berita terbaru untuk ticker via yfinance."""
    import yfinance as yf  # lazy import

    items = yf.Ticker(ticker).news or []
    headlines: list[str] = []
    for item in items[:limit]:
        # struktur payload yfinance berubah antar versi — dukung keduanya
        title = item.get("title") or (item.get("content") or {}).get("title")
        if title:
            headlines.append(str(title))
    return headlines


def score_headlines(headlines: list[str]) -> dict:
    """Skor lexicon: polaritas rata-rata [-1, 1] dipetakan ke 0-100."""
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
        tokens = {t.strip(".,!?:;()'\"").lower() for t in title.split()}
        pos = len(tokens & POSITIVE_WORDS)
        neg = len(tokens & NEGATIVE_WORDS)
        polarity = 0.0 if (pos + neg) == 0 else (pos - neg) / (pos + neg)
        polarities.append(polarity)
        details.append({"headline": title, "polarity": round(polarity, 2)})

    avg = sum(polarities) / len(polarities)
    score = round(50 + avg * 50, 2)
    label = "POSITIVE" if score >= 60 else "NEGATIVE" if score <= 40 else "NEUTRAL"
    return {
        "score": score,
        "label": label,
        "headline_count": len(headlines),
        "details": details,
    }


def sentiment_score(ticker: str) -> dict:
    """Pipeline lengkap: fetch berita lalu skor. Aman terhadap kegagalan jaringan."""
    try:
        headlines = fetch_news_headlines(ticker)
    except Exception as exc:  # jaringan/API bermasalah -> netral
        return {
            "score": 50.0,
            "label": "NEUTRAL",
            "headline_count": 0,
            "details": [],
            "note": f"Gagal mengambil berita ({exc}); skor netral dipakai.",
        }
    return score_headlines(headlines)
