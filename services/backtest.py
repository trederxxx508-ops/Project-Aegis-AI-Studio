"""Backtest Engine — menguji apakah skor benar-benar berguna.

Tanpa modul ini, sistem bisa memberi skor 78/100 dengan sangat meyakinkan
tanpa ada bukti bahwa skor 78 lebih baik daripada skor 40. Modul ini
menjawabnya dengan angka.

Yang paling dijaga: **lookahead bias** — kesalahan klasik backtest berupa
diam-diam memakai informasi masa depan, yang membuat hasil uji tampak hebat
padahal mustahil ditiru di dunia nyata. Tiga pengamanannya:

1. Indikator EMA/RSI/MACD/ATR bersifat kausal (nilai pada bar ke-i hanya
   bergantung pada bar 0..i), sehingga menghitungnya sekali secara vektor
   setara persis dengan menghitung ulang pada jendela terpotong.
2. Support/Resistance versi langsung memakai jendela pivot **terpusat** yang
   melihat bar sesudahnya. Untuk backtest dipakai varian kausal yang hanya
   melihat ke belakang.
3. Sinyal muncul pada penutupan bar ke-i, tetapi posisi baru dibuka pada
   **pembukaan bar ke-i+1** — bukan pada harga yang sudah diketahui.

Asumsi konservatif lain: bila dalam satu bar harga menyentuh stop loss dan
target sekaligus, data harian tidak memberi tahu mana yang lebih dulu, maka
diasumsikan **stop loss yang kena** (hasil uji jadi pesimistis, bukan
optimistis).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd

from services import market_data, scoring_engine

BUY_SIGNALS = ("STRONG BUY", "BUY")
DEFAULT_WARMUP = 200
DEFAULT_MAX_HOLDING = 60


# ---------------------------------------------------------------------------
# Indikator kausal untuk seluruh riwayat
# ---------------------------------------------------------------------------

def causal_support_resistance(
    df: pd.DataFrame, window: int = 5, lookback: int = 120
) -> tuple[pd.Series, pd.Series]:
    """Support/Resistance yang hanya melihat ke belakang.

    Versi langsung memakai pivot terpusat (melihat ``window`` bar sesudahnya).
    Itu tidak tersedia saat keputusan nyata diambil, jadi di sini pivot hanya
    dikonfirmasi bila seluruh jendelanya sudah berlalu.
    """
    highs, lows, closes = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    supports = np.full(n, np.nan)
    resistances = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - lookback + 1)
        seg_h, seg_l = highs[start : i + 1], lows[start : i + 1]
        close = closes[i]

        pivot_highs: list[float] = []
        pivot_lows: list[float] = []
        # Pivot hanya sah bila window penuh di kiri DAN kanan sudah lewat,
        # sehingga tidak ada bar masa depan yang ikut dipakai.
        for j in range(window, len(seg_h) - window):
            if seg_h[j] >= seg_h[j - window : j + window + 1].max():
                pivot_highs.append(seg_h[j])
            if seg_l[j] <= seg_l[j - window : j + window + 1].min():
                pivot_lows.append(seg_l[j])

        below = [p for p in pivot_lows if p < close]
        above = [p for p in pivot_highs if p > close]
        sup = max(below) if below else float(seg_l.min())
        res = min(above) if above else float(seg_h.max())
        supports[i] = sup if sup < close else float(seg_l.min())
        resistances[i] = res if res > close else float(seg_h.max())

    return pd.Series(supports, index=df.index), pd.Series(resistances, index=df.index)


def technical_score_history(df: pd.DataFrame) -> pd.DataFrame:
    """Hitung skor teknikal untuk setiap bar, tanpa memakai data masa depan."""
    close = df["Close"]
    ema20 = market_data.ema(close, 20)
    ema50 = market_data.ema(close, 50)
    ema200 = market_data.ema(close, 200)
    rsi14 = market_data.rsi(close, 14)
    macd_line, macd_signal, _ = market_data.macd(close)
    atr14 = market_data.atr(df, 14)
    support, resistance = causal_support_resistance(df)

    rows = []
    for i in range(len(df)):
        indicators = {
            "last_price": float(close.iloc[i]),
            "ema_20": float(ema20.iloc[i]),
            "ema_50": float(ema50.iloc[i]),
            "ema_200": float(ema200.iloc[i]),
            "rsi_14": float(rsi14.iloc[i]) if not pd.isna(rsi14.iloc[i]) else 50.0,
            "macd": float(macd_line.iloc[i]),
            "macd_signal": float(macd_signal.iloc[i]),
            "atr_14": float(atr14.iloc[i]),
            "support": float(support.iloc[i]),
            "resistance": float(resistance.iloc[i]),
            # Hanya bar yang sudah lewat yang boleh dihitung
            "data_points": i + 1,
            "ema_50_reliable": (i + 1) >= 50,
            "ema_200_reliable": (i + 1) >= 200,
        }
        scored = market_data.technical_score(indicators)
        rows.append({
            "score": scored["score"],
            "atr": indicators["atr_14"],
            "close": indicators["last_price"],
            "rsi": indicators["rsi_14"],
        })

    return pd.DataFrame(rows, index=df.index)


# ---------------------------------------------------------------------------
# Simulasi perdagangan
# ---------------------------------------------------------------------------

def _simulate_trades(
    df: pd.DataFrame,
    scores: pd.Series,
    atr: pd.Series,
    entry_threshold: float,
    atr_multiplier: float,
    reward_risk_ratio: float,
    max_holding_days: int,
    warmup: int,
) -> list[dict]:
    """Jalankan aturan masuk/keluar dan kembalikan daftar transaksi."""
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    index = df.index

    trades: list[dict] = []
    i = warmup
    n = len(df)

    while i < n - 1:
        if scores.iloc[i] < entry_threshold or not np.isfinite(atr.iloc[i]) or atr.iloc[i] <= 0:
            i += 1
            continue

        # Sinyal pada penutupan bar i -> masuk pada pembukaan bar i+1
        entry_idx = i + 1
        entry_price = float(opens[entry_idx])
        risk_per_unit = atr_multiplier * float(atr.iloc[i])
        stop_price = entry_price - risk_per_unit
        if stop_price <= 0 or risk_per_unit <= 0:
            i += 1
            continue
        target_price = entry_price + reward_risk_ratio * risk_per_unit

        exit_idx: Optional[int] = None
        exit_price: Optional[float] = None
        outcome = ""

        last_allowed = min(entry_idx + max_holding_days, n - 1)
        for j in range(entry_idx, last_allowed + 1):
            # Asumsi pesimistis: bila keduanya tersentuh dalam satu bar,
            # anggap stop loss yang lebih dulu kena.
            if lows[j] <= stop_price:
                exit_idx, exit_price, outcome = j, stop_price, "stop_loss"
                break
            if highs[j] >= target_price:
                exit_idx, exit_price, outcome = j, target_price, "take_profit"
                break
        if exit_idx is None:
            exit_idx, exit_price, outcome = last_allowed, float(closes[last_allowed]), "timeout"

        return_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            "entry_date": str(index[entry_idx].date()) if hasattr(index[entry_idx], "date") else str(index[entry_idx]),
            "exit_date": str(index[exit_idx].date()) if hasattr(index[exit_idx], "date") else str(index[exit_idx]),
            "entry_price": round(entry_price, 4),
            "exit_price": round(float(exit_price), 4),
            "stop_price": round(stop_price, 4),
            "target_price": round(target_price, 4),
            "score_at_entry": round(float(scores.iloc[i]), 2),
            "outcome": outcome,
            "holding_days": exit_idx - entry_idx,
            "return_pct": round(return_pct, 4),
        })

        i = exit_idx + 1  # tidak menumpuk posisi

    return trades


def _summarize(trades: list[dict], df: pd.DataFrame, warmup: int) -> dict:
    """Ubah daftar transaksi menjadi statistik yang bisa dinilai."""
    if not trades:
        return {
            "trades": 0,
            "win_rate": None,
            "verdict": "Tidak ada satu pun sinyal masuk pada periode ini.",
        }

    returns = np.array([t["return_pct"] for t in trades])
    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    win_rate = len(wins) / len(returns)
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(abs(losses.mean())) if len(losses) else 0.0
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    # Kurva ekuitas majemuk dari transaksi berurutan
    equity = np.cumprod(1 + returns / 100)
    peak = np.maximum.accumulate(equity)
    max_drawdown = float(((equity - peak) / peak).min() * 100)
    total_return = float((equity[-1] - 1) * 100)

    # Pembanding jujur: sekadar beli lalu tahan sepanjang periode uji.
    # Membandingkan hasil saja tidak adil — risiko dan lama terpapar pasar
    # juga harus ditampilkan, agar perbandingannya setara.
    test_slice = df.iloc[warmup:]
    if len(test_slice) > 1:
        closes_bh = test_slice["Close"].values
        buy_hold = float((closes_bh[-1] / closes_bh[0] - 1) * 100)
        bh_curve = closes_bh / closes_bh[0]
        bh_peak = np.maximum.accumulate(bh_curve)
        buy_hold_dd = float(((bh_curve - bh_peak) / bh_peak).min() * 100)
    else:
        buy_hold, buy_hold_dd = 0.0, 0.0

    days_in_market = sum(t["holding_days"] for t in trades)
    exposure_pct = (days_in_market / len(test_slice) * 100) if len(test_slice) else 0.0

    def _per_risk(ret: float, dd: float) -> Optional[float]:
        """Hasil per satu satuan penurunan terdalam — ukuran efisiensi risiko."""
        return round(ret / abs(dd), 2) if dd < 0 else None

    outcomes = {
        "take_profit": sum(1 for t in trades if t["outcome"] == "take_profit"),
        "stop_loss": sum(1 for t in trades if t["outcome"] == "stop_loss"),
        "timeout": sum(1 for t in trades if t["outcome"] == "timeout"),
    }

    return {
        "trades": len(trades),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": round(win_rate, 4),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "expectancy_pct": round(expectancy, 4),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "total_return_pct": round(total_return, 2),
        "buy_and_hold_pct": round(buy_hold, 2),
        "beats_buy_and_hold": bool(total_return > buy_hold),
        "max_drawdown_pct": round(max_drawdown, 2),
        "buy_and_hold_max_drawdown_pct": round(buy_hold_dd, 2),
        "return_per_drawdown": _per_risk(total_return, max_drawdown),
        "buy_and_hold_return_per_drawdown": _per_risk(buy_hold, buy_hold_dd),
        "market_exposure_pct": round(exposure_pct, 1),
        "avg_holding_days": round(float(np.mean([t["holding_days"] for t in trades])), 1),
        "outcomes": outcomes,
    }


def _verdict(stats: dict) -> str:
    """Kesimpulan dalam bahasa manusia — termasuk bila hasilnya mengecewakan."""
    if not stats.get("trades"):
        return stats.get("verdict", "Tidak ada transaksi.")

    if stats["trades"] < 30:
        dasar = (
            f"Hanya {stats['trades']} transaksi — terlalu sedikit untuk disimpulkan. "
            "Perpanjang periode uji atau turunkan ambang masuk."
        )
    else:
        dasar = f"Berdasarkan {stats['trades']} transaksi"

    pf = stats.get("profit_factor")
    if pf is None:
        mutu = "tidak ada transaksi rugi pada sampel ini — waspadai sampel terlalu kecil."
    elif pf >= 1.5:
        mutu = f"faktor profit {pf} tergolong baik."
    elif pf > 1.0:
        mutu = f"faktor profit {pf} sedikit di atas impas."
    else:
        mutu = f"faktor profit {pf} di bawah 1 — strategi ini merugi pada periode uji."

    banding = (
        f"Hasil: strategi {stats['total_return_pct']}% vs beli-dan-tahan "
        f"{stats['buy_and_hold_pct']}% — "
        + ("strategi unggul." if stats["beats_buy_and_hold"]
           else "beli-dan-tahan lebih unggul dari sisi hasil.")
    )

    # Perbandingan hasil saja tidak lengkap: strategi hanya terpapar pasar
    # sebagian waktu, sehingga risikonya berbeda.
    risiko = ""
    rpd, bh_rpd = stats.get("return_per_drawdown"), stats.get("buy_and_hold_return_per_drawdown")
    if rpd is not None and bh_rpd is not None:
        lebih_efisien = rpd > bh_rpd
        risiko = (
            f" Namun per satu satuan penurunan terdalam, strategi menghasilkan {rpd} "
            f"vs {bh_rpd} — "
            + ("strategi lebih efisien terhadap risiko" if lebih_efisien
               else "beli-dan-tahan tetap lebih efisien")
            + f", dengan paparan pasar hanya {stats.get('market_exposure_pct')}% dari waktu "
            f"(penurunan terdalam {stats['max_drawdown_pct']}% vs "
            f"{stats['buy_and_hold_max_drawdown_pct']}%)."
        )
    return f"{dasar}: {mutu} {banding}{risiko}"


# ---------------------------------------------------------------------------
# API publik
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    entry_threshold: float = 55.0,
    atr_multiplier: float = 2.0,
    reward_risk_ratio: float = 2.0,
    max_holding_days: int = DEFAULT_MAX_HOLDING,
    warmup: int = DEFAULT_WARMUP,
    score_series: Optional[pd.Series] = None,
) -> dict:
    """Uji mundur aturan sinyal pada satu DataFrame OHLCV.

    Args:
        entry_threshold: skor minimal untuk membuka posisi (55 = ambang BUY).
        score_series: skor siap pakai; bila None dipakai skor teknikal.
    """
    if len(df) < warmup + 30:
        raise ValueError(
            f"Butuh minimal {warmup + 30} bar untuk backtest "
            f"(tersedia {len(df)}). Perpanjang periode data atau turunkan warmup."
        )

    history = technical_score_history(df)
    scores = score_series if score_series is not None else history["score"]
    scores = scores.reindex(df.index).ffill()

    trades = _simulate_trades(
        df=df,
        scores=scores,
        atr=history["atr"],
        entry_threshold=entry_threshold,
        atr_multiplier=atr_multiplier,
        reward_risk_ratio=reward_risk_ratio,
        max_holding_days=max_holding_days,
        warmup=warmup,
    )
    stats = _summarize(trades, df, warmup)
    stats["verdict"] = _verdict(stats)

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "entry_threshold": entry_threshold,
            "atr_multiplier": atr_multiplier,
            "reward_risk_ratio": reward_risk_ratio,
            "max_holding_days": max_holding_days,
            "warmup_bars": warmup,
        },
        "period": {
            "from": str(df.index[warmup].date()) if hasattr(df.index[warmup], "date") else str(df.index[warmup]),
            "to": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
            "bars_total": len(df),
            "bars_tested": len(df) - warmup,
        },
        "stats": stats,
        "trades": trades,
        "assumptions": [
            "Sinyal pada penutupan, posisi dibuka pada pembukaan bar berikutnya.",
            "Bila stop loss dan target tersentuh pada bar yang sama, dianggap stop loss lebih dulu (pesimistis).",
            "Belum memperhitungkan biaya transaksi, pajak, dan selisih harga (slippage).",
            "Hanya skor teknikal yang diuji; fundamental dan sentimen tidak punya riwayat yang bisa diuji mundur.",
        ],
    }


def backtest_ticker(
    ticker: str,
    period: str = "5y",
    entry_threshold: float = 55.0,
    atr_multiplier: float = 2.0,
    reward_risk_ratio: float = 2.0,
    max_holding_days: int = DEFAULT_MAX_HOLDING,
    fetcher: Optional[Callable[..., pd.DataFrame]] = None,
) -> dict:
    """Ambil data historis lalu jalankan backtest untuk satu ticker."""
    fetch = fetcher or market_data.fetch_ohlcv
    df = fetch(ticker, period=period)
    result = run_backtest(
        df,
        entry_threshold=entry_threshold,
        atr_multiplier=atr_multiplier,
        reward_risk_ratio=reward_risk_ratio,
        max_holding_days=max_holding_days,
    )
    result["ticker"] = ticker.upper()
    return result


def calibrated_risk_inputs(backtest_result: dict) -> dict:
    """Ubah hasil backtest menjadi masukan risiko yang terukur.

    Selama ini ``win_rate`` diketik manual oleh pengguna, sehingga Kelly
    Criterion menghitung memakai angka karangan. Fungsi ini menggantinya
    dengan angka hasil pengujian — atau menolak memberi angka bila
    sampelnya terlalu kecil untuk dipercaya.
    """
    stats = backtest_result.get("stats", {})
    trades = stats.get("trades", 0)
    win_rate = stats.get("win_rate")

    if not trades or win_rate is None:
        return {
            "usable": False,
            "reason": "Tidak ada transaksi pada periode uji.",
            "win_rate": None,
            "reward_risk_ratio": None,
        }
    if trades < 30:
        return {
            "usable": False,
            "reason": (
                f"Hanya {trades} transaksi — di bawah 30, terlalu sedikit untuk "
                "dijadikan dasar ukuran posisi."
            ),
            "win_rate": round(win_rate, 4),
            "reward_risk_ratio": None,
        }

    avg_win = stats.get("avg_win_pct") or 0.0
    avg_loss = stats.get("avg_loss_pct") or 0.0
    realized_rr = (avg_win / avg_loss) if avg_loss > 0 else None

    return {
        "usable": True,
        "reason": f"Dikalibrasi dari {trades} transaksi hasil uji mundur.",
        "win_rate": round(win_rate, 4),
        "reward_risk_ratio": round(realized_rr, 3) if realized_rr else None,
        "expectancy_pct": stats.get("expectancy_pct"),
        "sample_size": trades,
    }
