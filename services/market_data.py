"""Technical Engine — market data fetcher & indikator harian.

Sumber data default: yfinance (gratis). Fungsi indikator menerima
``pandas.DataFrame``/``Series`` murni sehingga bisa diuji tanpa akses jaringan.

Indikator yang dihitung: EMA(20/50/200), RSI(14, metode Wilder),
MACD(12/26/9), ATR(14, metode Wilder), dan area Support/Resistance
berbasis pivot high/low.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

MAX_FETCH_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 3.0)  # jeda sebelum percobaan ke-2 dan ke-3


class RateLimitedError(RuntimeError):
    """Penyedia data menolak permintaan karena terlalu sering (HTTP 429)."""


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Ambil data OHLCV historis via yfinance, dengan percobaan ulang.

    Ticker Bursa Efek Indonesia memakai sufiks ``.JK`` (contoh: ``BBCA.JK``).

    Raises:
        ValueError: simbol tidak dikenal atau data tidak lengkap.
        RateLimitedError: penyedia data membatasi permintaan.
    """
    import time

    import yfinance as yf  # lazy import: indikator tetap bisa dipakai offline

    last_error: Exception | None = None
    for attempt in range(MAX_FETCH_ATTEMPTS):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        except Exception as exc:  # jaringan putus / rate limit / API berubah
            last_error = exc
            if attempt < MAX_FETCH_ATTEMPTS - 1:
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue
            if _is_rate_limit(exc):
                raise RateLimitedError(
                    f"Penyedia data membatasi permintaan saat mengambil '{ticker}'. "
                    "Tunggu sekitar satu menit lalu coba lagi, atau kurangi jumlah saham "
                    "yang dipindai sekaligus."
                ) from exc
            raise ConnectionError(
                f"Gagal mengambil data '{ticker}': {exc}. Periksa koneksi internet Anda."
            ) from exc

        if df is not None and not df.empty:
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                raise ValueError(f"Data {ticker} tidak lengkap, kolom hilang: {missing}")
            return df

        # Respons kosong bisa berarti simbol salah, bisa juga throttling sesaat
        if attempt < MAX_FETCH_ATTEMPTS - 1:
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])

    raise ValueError(
        f"Tidak ada data harga untuk ticker '{ticker}'. "
        "Pastikan simbol benar (saham IDX memakai sufiks .JK, mis. BBCA.JK)."
        + (f" Kesalahan terakhir: {last_error}" if last_error else "")
    )


# ---------------------------------------------------------------------------
# Indicators (pure functions)
# ---------------------------------------------------------------------------

def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    if span <= 0:
        raise ValueError("span EMA harus > 0")
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index dengan smoothing Wilder."""
    if period <= 0:
        raise ValueError("period RSI harus > 0")
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(delta.notna(), np.nan)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, dan histogram."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range dengan smoothing Wilder."""
    if period <= 0:
        raise ValueError("period ATR harus > 0")
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def support_resistance(
    df: pd.DataFrame, window: int = 5, lookback: int = 120
) -> dict[str, Optional[float]]:
    """Deteksi area Support/Resistance dari pivot high/low.

    Pivot = titik ekstrem lokal dalam jendela ``2*window+1`` bar. Support
    adalah pivot low tertinggi di bawah harga sekarang; resistance adalah
    pivot high terendah di atasnya. Fallback: min/max periode lookback.
    """
    data = df.tail(lookback)
    close = float(data["Close"].iloc[-1])
    highs, lows = data["High"], data["Low"]

    pivot_highs, pivot_lows = [], []
    for i in range(window, len(data) - window):
        seg_h = highs.iloc[i - window : i + window + 1]
        seg_l = lows.iloc[i - window : i + window + 1]
        if highs.iloc[i] >= seg_h.max():
            pivot_highs.append(float(highs.iloc[i]))
        if lows.iloc[i] <= seg_l.min():
            pivot_lows.append(float(lows.iloc[i]))

    supports = [p for p in pivot_lows if p < close]
    resistances = [p for p in pivot_highs if p > close]
    support = max(supports) if supports else float(lows.min())
    resistance = min(resistances) if resistances else float(highs.max())
    if support >= close:
        support = float(lows.min())
    if resistance <= close:
        resistance = float(highs.max())
    return {"support": round(support, 2), "resistance": round(resistance, 2)}


# ---------------------------------------------------------------------------
# Snapshot + scoring
# ---------------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> dict:
    """Hitung snapshot indikator dari DataFrame OHLCV harian."""
    if len(df) < 30:
        raise ValueError("Butuh minimal 30 bar data untuk menghitung indikator.")

    close = df["Close"]
    macd_line, signal_line, histogram = macd(close)
    sr = support_resistance(df)

    last = lambda s: float(s.iloc[-1])  # noqa: E731
    return {
        "last_price": round(last(close), 2),
        "ema_20": round(last(ema(close, 20)), 2),
        "ema_50": round(last(ema(close, 50)), 2),
        "ema_200": round(last(ema(close, 200)), 2),
        "rsi_14": round(last(rsi(close, 14)), 2),
        "macd": round(last(macd_line), 4),
        "macd_signal": round(last(signal_line), 4),
        "macd_histogram": round(last(histogram), 4),
        "atr_14": round(last(atr(df, 14)), 4),
        "support": sr["support"],
        "resistance": sr["resistance"],
    }


def technical_score(ind: dict) -> dict:
    """Konversi snapshot indikator menjadi skor teknikal 0-100.

    Bobot: struktur tren EMA (45), momentum RSI (20), MACD (25),
    posisi terhadap Support/Resistance (10).
    """
    price = ind["last_price"]
    breakdown: dict[str, float] = {}

    trend = 0.0
    trend += 10 if price > ind["ema_20"] else 0
    trend += 10 if price > ind["ema_50"] else 0
    trend += 15 if price > ind["ema_200"] else 0
    trend += 5 if ind["ema_20"] > ind["ema_50"] else 0
    trend += 5 if ind["ema_50"] > ind["ema_200"] else 0
    breakdown["trend_ema"] = trend

    r = ind["rsi_14"]
    if 45 <= r <= 65:
        momentum = 20.0  # momentum sehat
    elif 30 <= r < 45:
        momentum = 12.0  # netral-lemah
    elif 65 < r <= 75:
        momentum = 10.0  # mulai jenuh beli
    elif r < 30:
        momentum = 8.0   # oversold, rawan tapi potensi rebound
    else:
        momentum = 4.0   # overbought ekstrem
    breakdown["momentum_rsi"] = momentum

    macd_score = 0.0
    macd_score += 15 if ind["macd"] > ind["macd_signal"] else 0
    macd_score += 10 if ind["macd"] > 0 else 0
    breakdown["macd"] = macd_score

    sr_score = 5.0
    support, resistance = ind["support"], ind["resistance"]
    if support and support > 0:
        dist_support = (price - support) / price
        if 0 <= dist_support <= 0.05:
            sr_score = 10.0  # dekat support: risk/reward menarik
    if resistance and resistance > 0:
        dist_resistance = (resistance - price) / price
        if 0 <= dist_resistance <= 0.02:
            sr_score = 2.0  # menempel resistance: upside terbatas
    breakdown["support_resistance"] = sr_score

    total = round(min(100.0, sum(breakdown.values())), 2)
    return {"score": total, "breakdown": breakdown}
