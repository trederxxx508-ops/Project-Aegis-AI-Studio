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

from services import fundamental_engine, market_data, risk_engine, scoring_engine, sentiment_engine
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
    win_rate: float = Field(default=0.55, ge=0, le=1)
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
    ticker = request.ticker.strip().upper()

    # 1. Technical Engine
    try:
        df = market_data.fetch_ohlcv(ticker, period=request.period)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil data pasar: {exc}")

    try:
        indicators = market_data.compute_indicators(df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    technical = market_data.technical_score(indicators)

    # 2. Sentiment Engine (selalu punya fallback netral)
    sentiment = sentiment_engine.sentiment_score(ticker)

    # 3. Fundamental Engine (RAG -> rasio yfinance -> netral)
    fundamental = fundamental_engine.score_fundamental(ticker, use_rag=request.use_rag)

    # 4. Master Scoring Engine
    verdict = scoring_engine.master_score(
        fundamental=fundamental["score"],
        technical=technical["score"],
        sentiment=sentiment["score"],
    )

    # 5. Risk Engine — position sizing pada harga & volatilitas terkini
    try:
        risk_plan = risk_engine.calculate_position_size(
            total_capital=request.total_capital,
            max_risk_pct=request.max_risk_pct,
            entry_price=indicators["last_price"],
            atr_value=indicators["atr_14"],
            atr_multiplier=request.atr_multiplier,
            win_rate=request.win_rate,
            reward_risk_ratio=request.reward_risk_ratio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Risk engine: {exc}")

    return AnalyzeResponse(
        ticker=ticker,
        signal=verdict["signal"],
        total_score=verdict["total_score"],
        scores={"components": verdict["components"], "weights": verdict["weights"]},
        technical={"indicators": indicators, **technical},
        sentiment=sentiment,
        fundamental=fundamental,
        risk_plan=risk_plan,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("rag_financial_api:app", host="0.0.0.0", port=8000, reload=True)
