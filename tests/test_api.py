"""Test integrasi FastAPI — endpoint /health, /query, /analyze-stock.

Sumber data eksternal (yfinance, OpenAI) di-mock sehingga test berjalan offline.
"""
import pytest
from fastapi.testclient import TestClient

import rag_financial_api
from services import fundamental_engine, market_data, sentiment_engine
from tests.conftest import make_ohlcv

client = TestClient(rag_financial_api.app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["rag_ready"] is False


def test_query_requires_uploaded_pdf():
    resp = client.post("/query", json={"query": "Berapa laba bersih?"})
    assert resp.status_code == 400
    assert "Upload PDF" in resp.json()["detail"]


def test_upload_rejects_non_pdf():
    resp = client.post(
        "/upload-pdf",
        files={"file": ("report.txt", b"bukan pdf", "text/plain")},
    )
    assert resp.status_code == 400


def test_analyze_stock_full_pipeline(monkeypatch):
    monkeypatch.setattr(market_data, "fetch_ohlcv", lambda ticker, period="1y", interval="1d": make_ohlcv(trend=0.002))
    monkeypatch.setattr(
        sentiment_engine,
        "sentiment_score",
        lambda ticker: {"score": 70.0, "label": "POSITIVE", "headline_count": 3, "details": []},
    )
    monkeypatch.setattr(
        fundamental_engine,
        "score_fundamental",
        lambda ticker, use_rag=True: {"score": 80.0, "source": "yfinance_ratios"},
    )

    resp = client.post(
        "/analyze-stock",
        json={"ticker": "bbca.jk", "total_capital": 100_000_000, "max_risk_pct": 0.02},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["ticker"] == "BBCA.JK"
    assert body["signal"] in {"STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"}
    assert 0 <= body["total_score"] <= 100

    comps = body["scores"]["components"]
    assert comps["fundamental"] == 80.0
    assert comps["sentiment"] == 70.0
    expected_total = round(80 * 0.5 + comps["technical"] * 0.3 + 70 * 0.2, 2)
    assert body["total_score"] == pytest.approx(expected_total, abs=0.01)

    rp = body["risk_plan"]
    assert rp["recommended_lots"] >= 0
    assert rp["stop_loss_price"] < rp["entry_price"] < rp["take_profit_price"]
    assert rp["portfolio_exposure_pct"] <= 100.0

    ind = body["technical"]["indicators"]
    assert ind["atr_14"] > 0
    assert 0 <= ind["rsi_14"] <= 100


def test_analyze_stock_unknown_ticker(monkeypatch):
    def raise_not_found(ticker, period="1y", interval="1d"):
        raise ValueError(f"Tidak ada data harga untuk ticker '{ticker}'.")

    monkeypatch.setattr(market_data, "fetch_ohlcv", raise_not_found)
    resp = client.post("/analyze-stock", json={"ticker": "ZZZZ"})
    assert resp.status_code == 404


def test_analyze_stock_validates_params():
    resp = client.post(
        "/analyze-stock",
        json={"ticker": "BBCA.JK", "max_risk_pct": 5},  # 500% risiko -> invalid
    )
    assert resp.status_code == 422
