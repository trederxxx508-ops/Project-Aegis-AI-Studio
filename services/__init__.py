"""Project Aegis — service engines untuk Stock AI Copilot.

Modul:
- market_data       : fetch OHLCV (dengan retry) + indikator teknikal (EMA, RSI, MACD, ATR, S/R)
- analysis          : pipeline lima engine untuk satu ticker
- scanner           : pemindai watchlist paralel + peringkat
- cache             : cache TTL agar API pasar tidak ditembak berulang kali
- risk_engine       : position sizing berbasis risiko + ATR stop loss + Kelly
- sentiment_engine  : skor sentimen berita (lexicon-based, fallback netral)
- fundamental_engine: skor fundamental (RAG -> yfinance heuristik -> netral)
- scoring_engine    : Master Scoring Engine (0-100) + sinyal akhir
- rag_engine        : RAG laporan keuangan (LlamaIndex + Qdrant + OpenAI)
"""
