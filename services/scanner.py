"""Watchlist Scanner — analisis banyak saham sekaligus lalu diperingkat.

Ini bagian "otomatis": pengguna tidak perlu memilih saham satu per satu.
Scanner menjalankan pipeline lengkap untuk setiap ticker secara paralel,
mengurutkan hasilnya berdasarkan skor akhir, dan menandai kandidat terbaik.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from services import market_data
from services.analysis import analyze_ticker

# Dijaga rendah dengan sengaja: penyedia data gratis membatasi permintaan
# per IP. Paralelisme berlebihan justru memicu HTTP 429 dan memperlambat.
MAX_WORKERS = 4

# Preset watchlist siap pakai
WATCHLISTS: dict[str, list[str]] = {
    "idx_bluechip": [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK",
        "ASII.JK", "ICBP.JK", "INDF.JK", "KLBF.JK", "UNVR.JK",
    ],
    "idx_energy_mining": [
        "ADRO.JK", "PTBA.JK", "ITMG.JK", "ANTM.JK", "INCO.JK",
        "MDKA.JK", "TINS.JK", "PGAS.JK",
    ],
    "idx_consumer_retail": [
        "AMRT.JK", "MAPI.JK", "ACES.JK", "ERAA.JK", "CPIN.JK",
        "JPFA.JK", "MYOR.JK", "SIDO.JK",
    ],
    "us_megacap": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
    ],
}


def scan_watchlist(
    tickers: list[str],
    total_capital: float = 100_000_000,
    max_risk_pct: float = 0.02,
    atr_multiplier: float = 2.0,
    win_rate: float = 0.55,
    reward_risk_ratio: float = 2.0,
    period: str = "1y",
    min_score: float = 0.0,
    use_cache: bool = True,
) -> dict:
    """Analisis seluruh ticker secara paralel, kembalikan peringkat.

    Ticker yang gagal (simbol salah, data kosong, jaringan) tidak
    menggagalkan seluruh pemindaian — dilaporkan terpisah di ``errors``.
    """
    unique = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not unique:
        raise ValueError("Daftar ticker kosong.")

    results: list[dict] = []
    errors: list[dict] = []

    def run(tkr: str) -> dict:
        # Skor fundamental dari RAG dimatikan saat scanning: dokumen PDF
        # merujuk satu emiten, sementara scanner memproses banyak emiten.
        return analyze_ticker(
            tkr,
            total_capital=total_capital,
            max_risk_pct=max_risk_pct,
            atr_multiplier=atr_multiplier,
            win_rate=win_rate,
            reward_risk_ratio=reward_risk_ratio,
            period=period,
            use_rag=False,
            use_cache=use_cache,
        )

    workers = min(MAX_WORKERS, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, t): t for t in unique}
        for future in as_completed(futures):
            tkr = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({
                    "ticker": tkr,
                    "error": str(exc),
                    "kind": type(exc).__name__,
                    "rate_limited": isinstance(exc, market_data.RateLimitedError),
                })

    results.sort(key=lambda r: r["total_score"], reverse=True)
    ranked = [r for r in results if r["total_score"] >= min_score]
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    buy_signals = [r for r in ranked if r["signal"] in ("STRONG BUY", "BUY")]

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "requested": len(unique),
        "analyzed": len(results),
        "passed_filter": len(ranked),
        "buy_candidates": len(buy_signals),
        "top_pick": ranked[0]["ticker"] if ranked else None,
        "rate_limited": bool(errors) and all(e.get("rate_limited") for e in errors),
        "results": ranked,
        "errors": errors,
    }


def summarize(scan: dict) -> list[dict]:
    """Ringkasan tabel untuk UI: satu baris per saham."""
    rows = []
    for r in scan["results"]:
        ind = r["technical"]["indicators"]
        rp = r["risk_plan"]
        rows.append({
            "rank": r.get("rank"),
            "ticker": r["ticker"],
            "signal": r["signal"],
            "total_score": r["total_score"],
            "fundamental": r["scores"]["components"]["fundamental"],
            "technical": r["scores"]["components"]["technical"],
            "sentiment": r["scores"]["components"]["sentiment"],
            "price": ind["last_price"],
            "rsi_14": ind["rsi_14"],
            "atr_14": ind["atr_14"],
            "support": ind["support"],
            "resistance": ind["resistance"],
            "stop_loss": rp["stop_loss_price"],
            "take_profit": rp["take_profit_price"],
            "lots": rp["recommended_lots"],
            "allocation_idr": rp["total_allocation_idr"],
            "max_loss_idr": rp["max_potential_loss_idr"],
            "exposure_pct": rp["portfolio_exposure_pct"],
        })
    return rows
