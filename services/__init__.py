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

Modul emas & makro:
- macro_engine      : suku bunga riil, dolar, ekspektasi inflasi, yield (FRED)
- gold              : pipeline emas (Makro x0,5 + Teknikal x0,3 + Sentimen x0,2)
- gold_sentiment    : kamus sentimen khusus emas (polaritas berbeda dari saham)
- market_hours      : status buka/tutup pasar + kesegaran harga
- regime            : deteksi saat hubungan makro-emas berhenti berlaku
- backtest          : uji mundur bebas lookahead + kalibrasi win rate terukur
"""
