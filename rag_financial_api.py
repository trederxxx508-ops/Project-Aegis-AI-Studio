"""Project Aegis — Stock AI Copilot Backend.

FastAPI backend yang menggabungkan 5 engine analisis:
- Fundamental (RAG): /upload-pdf, /query  (FastAPI + LlamaIndex + Qdrant + PyPDF)
- Technical         : EMA(20/50/200), RSI(14), MACD, ATR(14), Support/Resistance
- Sentiment         : skor sentimen berita
- Risk              : position sizing ATR + Fractional Kelly
- Master Scoring    : Total = Fund*0.5 + Tech*0.3 + Sent*0.2 -> sinyal akhir

Jalankan: uvicorn rag_financial_api:app --reload
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services import (
    alerts, backtest, cache, gold, history, macro_engine, market_data, regime, scanner,
)
from services.analysis import analyze_ticker
from services.rag_engine import rag_engine

load_dotenv()

app = FastAPI(
    title="Project Aegis — Stock AI Copilot API",
    description=(
        "AI Stock Copilot & Decision Support System: RAG laporan keuangan, "
        "indikator teknikal, sentimen berita, risk management, dan master scoring."
    ),
    version="1.0.0",
)

TEMP_UPLOAD_DIR = "./temp_uploads"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=20)


class SourceNode(BaseModel):
    content: str
    page_label: Optional[str] = None
    file_name: Optional[str] = None
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceNode]


class AnalyzeRequest(BaseModel):
    ticker: str = Field(description="Simbol saham, saham IDX pakai sufiks .JK (mis. BBCA.JK)")
    total_capital: float = Field(default=100_000_000, gt=0, description="Total modal (IDR)")
    max_risk_pct: float = Field(default=0.02, gt=0, lt=1, description="Risiko per trade (0.02 = 2%)")
    atr_multiplier: float = Field(default=2.0, gt=0, le=5)
    win_rate: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Kosongkan bila belum diukur — Kelly tidak diterapkan atas tebakan.",
    )
    reward_risk_ratio: float = Field(default=2.0, gt=0)
    period: str = Field(default="1y", description="Periode data historis yfinance")
    use_rag: bool = Field(default=True, description="Pakai laporan PDF ter-ingest untuk skor fundamental")


class AnalyzeResponse(BaseModel):
    ticker: str
    signal: str
    total_score: float
    scores: dict
    technical: dict
    sentiment: dict
    fundamental: dict
    risk_plan: dict
    analyzed_at: Optional[str] = None


class GoldRequest(BaseModel):
    total_capital: float = Field(default=10_000, gt=0, description="Total modal dalam USD")
    max_risk_pct: float = Field(default=0.02, gt=0, lt=1)
    atr_multiplier: float = Field(default=2.0, gt=0, le=5)
    win_rate: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Kosongkan bila belum diukur — Kelly tidak diterapkan atas tebakan.",
    )
    reward_risk_ratio: float = Field(default=2.0, gt=0)
    period: str = Field(default="1y")
    extra_headlines: Optional[list[str]] = Field(
        default=None, description="Judul berita tambahan untuk ikut dinilai sentimennya"
    )
    use_cache: bool = Field(default=True)


class BacktestRequest(BaseModel):
    ticker: str = Field(description="Simbol yang diuji, mis. BBCA.JK atau GC=F (emas)")
    period: str = Field(default="10y", description="Panjang riwayat, mis. 5y / 10y / max")
    entry_threshold: float = Field(default=55.0, ge=0, le=100, description="Skor minimal untuk masuk")
    atr_multiplier: float = Field(default=2.0, gt=0, le=5)
    reward_risk_ratio: float = Field(default=2.0, gt=0)
    max_holding_days: int = Field(default=60, ge=1, le=365)
    include_trades: bool = Field(default=False, description="Sertakan rincian tiap transaksi")


class ScanRequest(BaseModel):
    tickers: Optional[list[str]] = Field(
        default=None, description="Daftar ticker. Kosongkan untuk memakai preset watchlist."
    )
    watchlist: Optional[str] = Field(
        default=None, description=f"Preset watchlist: {', '.join(scanner.WATCHLISTS)}"
    )
    total_capital: float = Field(default=100_000_000, gt=0)
    max_risk_pct: float = Field(default=0.02, gt=0, lt=1)
    atr_multiplier: float = Field(default=2.0, gt=0, le=5)
    win_rate: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Kosongkan bila belum diukur — Kelly tidak diterapkan atas tebakan.",
    )
    reward_risk_ratio: float = Field(default=2.0, gt=0)
    period: str = Field(default="1y")
    min_score: float = Field(default=0.0, ge=0, le=100, description="Saring hasil di bawah skor ini")
    use_cache: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check")
async def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "rag_ready": rag_engine.is_ready,
        "ingested_files": rag_engine.ingested_files,
    }


@app.post("/upload-pdf", summary="Upload & Ingest Laporan Keuangan PDF")
async def upload_financial_pdf(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File harus berformat PDF.")

    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(TEMP_UPLOAD_DIR, os.path.basename(file.filename))
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        pages = rag_engine.ingest_pdf(file_path, file.filename)
        return {
            "status": "success",
            "filename": file.filename,
            "pages_processed": pages,
            "message": "Dokumen berhasil diproses ke Vector DB.",
        }
    except RuntimeError as exc:  # konfigurasi (mis. API key) belum siap
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal memproses PDF: {exc}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/query", response_model=QueryResponse, summary="Tanya Jawab Laporan Keuangan")
async def query_financial_data(request: QueryRequest) -> QueryResponse:
    if not rag_engine.is_ready:
        raise HTTPException(status_code=400, detail="Upload PDF terlebih dahulu.")
    try:
        answer, sources = rag_engine.query(request.query, top_k=request.top_k)
        return QueryResponse(answer=answer, sources=[SourceNode(**s) for s in sources])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal memproses query: {exc}")


@app.post("/analyze-stock", response_model=AnalyzeResponse, summary="Analisis Lengkap + Sinyal + Position Sizing")
async def analyze_stock(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        result = analyze_ticker(
            request.ticker,
            total_capital=request.total_capital,
            max_risk_pct=request.max_risk_pct,
            atr_multiplier=request.atr_multiplier,
            win_rate=request.win_rate,
            reward_risk_ratio=request.reward_risk_ratio,
            period=request.period,
            use_rag=request.use_rag,
        )
    except market_data.RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ValueError as exc:
        # Ticker tidak ditemukan / data historis terlalu pendek
        message = str(exc)
        status = 404 if "Tidak ada data harga" in message else 422
        raise HTTPException(status_code=status, detail=message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil data pasar: {exc}")

    return AnalyzeResponse(**result)


@app.get("/watchlists", summary="Daftar Preset Watchlist")
async def list_watchlists() -> dict:
    return {
        "watchlists": {name: tickers for name, tickers in scanner.WATCHLISTS.items()},
        "default": "idx_bluechip",
    }


@app.post("/scan", summary="Pindai Watchlist Otomatis & Peringkat Saham Terbaik")
async def scan_stocks(request: ScanRequest) -> dict:
    if request.tickers:
        tickers = request.tickers
    else:
        name = request.watchlist or "idx_bluechip"
        if name not in scanner.WATCHLISTS:
            raise HTTPException(
                status_code=400,
                detail=f"Watchlist '{name}' tidak dikenal. Pilihan: {', '.join(scanner.WATCHLISTS)}",
            )
        tickers = scanner.WATCHLISTS[name]

    try:
        result = scanner.scan_watchlist(
            tickers,
            total_capital=request.total_capital,
            max_risk_pct=request.max_risk_pct,
            atr_multiplier=request.atr_multiplier,
            win_rate=request.win_rate,
            reward_risk_ratio=request.reward_risk_ratio,
            period=request.period,
            min_score=request.min_score,
            use_cache=request.use_cache,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result["analyzed"] == 0:
        if result["rate_limited"]:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Penyedia data sedang membatasi permintaan. Tunggu sekitar satu "
                    "menit, lalu pindai lagi dengan daftar saham yang lebih pendek."
                ),
            )
        raise HTTPException(
            status_code=502,
            detail=(
                "Tidak ada satu pun ticker yang berhasil dianalisis. "
                "Periksa koneksi internet atau simbol ticker. "
                f"Detail: {result['errors'][:3]}"
            ),
        )

    result["table"] = scanner.summarize(result)
    return result


@app.get("/macro", summary="Kondisi Makro Ekonomi (Pendorong Harga Emas)")
async def get_macro(use_cache: bool = True) -> dict:
    """Skor makro 0-100 beserta asal-usul dan kesegaran tiap indikator."""
    try:
        return macro_engine.macro_score(use_cache=use_cache)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil data makro: {exc}")


@app.get("/regime", summary="Apakah Hubungan Makro-Emas Sedang Berlaku?")
async def get_regime(use_cache: bool = True) -> dict:
    """Ukur apakah emas masih mengikuti suku bunga riil seperti biasanya.

    Bila hubungannya sedang putus, bobot skor makro diturunkan otomatis dan
    hal itu dinyatakan terang-terangan pada hasil analisis emas.
    """
    try:
        df, _ = gold.fetch_gold_prices(use_cache=use_cache)
        closes = {idx.date(): float(val) for idx, val in df["Close"].dropna().items()}
        return regime.relationship_health(closes, use_cache=use_cache)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/analyze-gold", summary="Analisis Emas: Makro + Teknikal + Sentimen + Posisi")
async def analyze_gold_endpoint(request: GoldRequest) -> dict:
    """Analisis emas (USD per troy ounce) memakai Makro×0,5 + Teknikal×0,3 + Sentimen×0,2."""
    try:
        return gold.analyze_gold(
            total_capital=request.total_capital,
            max_risk_pct=request.max_risk_pct,
            atr_multiplier=request.atr_multiplier,
            win_rate=request.win_rate,
            reward_risk_ratio=request.reward_risk_ratio,
            period=request.period,
            extra_headlines=request.extra_headlines,
            use_cache=request.use_cache,
        )
    except market_data.RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/backtest", summary="Uji Mundur: Apakah Skor Ini Terbukti Berguna?")
async def run_backtest_endpoint(request: BacktestRequest) -> dict:
    """Uji aturan sinyal pada data historis, tanpa memakai data masa depan.

    Hasilnya juga menghasilkan kalibrasi win rate terukur, menggantikan angka
    yang selama ini diisi manual oleh pengguna.
    """
    def _fetch(ticker: str, period: str = request.period):
        # Simbol komoditas/indeks kerap gagal di klien yfinance; jalur chart
        # API mandiri dipakai sebagai cadangan otomatis.
        try:
            return market_data.fetch_ohlcv(ticker, period=period)
        except market_data.RateLimitedError:
            raise
        except Exception:
            return market_data.fetch_chart_api(ticker, range_=period)

    try:
        result = backtest.backtest_ticker(
            request.ticker,
            period=request.period,
            entry_threshold=request.entry_threshold,
            atr_multiplier=request.atr_multiplier,
            reward_risk_ratio=request.reward_risk_ratio,
            max_holding_days=request.max_holding_days,
            fetcher=_fetch,
        )
    except market_data.RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal menjalankan backtest: {exc}")

    result["calibration"] = backtest.calibrated_risk_inputs(result)
    if not request.include_trades:
        result["trades"] = []
    return result


@app.get("/history/{asset}", summary="Riwayat Skor — Arah Pergerakan, Bukan Cuma Angka Hari Ini")
async def get_asset_history(asset: str, days: int = 90) -> dict:
    return {
        "asset": asset.upper(),
        "trend": history.summarize_trend(asset, days=days),
        "snapshots": history.get_history(asset, days=days),
    }


@app.get("/history", summary="Daftar Aset yang Punya Riwayat")
async def list_history() -> dict:
    return history.stats()


@app.post("/snapshot/{asset}", summary="Rekam Kondisi Sekarang + Deteksi Perubahan")
async def take_snapshot(asset: str) -> dict:
    """Analisis, simpan ke riwayat, lalu laporkan perubahan sejak rekaman terakhir."""
    name = asset.upper()
    try:
        if name == "GOLD":
            analysis = gold.analyze_gold()
        else:
            analysis = analyze_ticker(name)
    except market_data.RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal menganalisis {name}: {exc}")

    previous = history.get_latest(name)
    history.record_snapshot(name, analysis)
    current = history.get_latest(name)
    found = alerts.evaluate(previous, current)

    return {
        "asset": name,
        "signal": analysis.get("signal"),
        "total_score": analysis.get("total_score"),
        "alerts": found,
        "is_first_snapshot": previous is None,
        "trend": history.summarize_trend(name),
    }


@app.post("/cache/clear", summary="Kosongkan Cache Data Pasar")
async def clear_cache() -> dict:
    before = cache.stats()["entries"]
    cache.clear()
    return {"status": "ok", "cleared_entries": before}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("rag_financial_api:app", host="0.0.0.0", port=8000, reload=True)
