"""Project Aegis — Streamlit Dashboard (Phase 4).

Antarmuka sederhana untuk: upload PDF laporan keuangan, tanya jawab RAG,
dan analisis saham lengkap (skor + sinyal + tabel posisi risiko).

Jalankan: streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("AEGIS_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Project Aegis — Stock AI Copilot", page_icon="🛡️", layout="wide")
st.title("🛡️ Project Aegis — Stock AI Copilot")
st.caption("Decision support: Fundamental (RAG) • Technical • Sentiment • Risk • Master Score")

with st.sidebar:
    st.header("⚙️ Koneksi & Modal")
    api_url = st.text_input("Backend API URL", value=API_URL)
    total_capital = st.number_input("Total Modal (IDR)", min_value=1_000_000, value=100_000_000, step=1_000_000)
    max_risk_pct = st.slider("Risiko per Trade (%)", 0.5, 10.0, 2.0, 0.5) / 100
    atr_multiplier = st.slider("ATR Multiplier (k)", 1.0, 3.0, 2.0, 0.25)
    win_rate = st.slider("Win Rate Historis", 0.30, 0.80, 0.55, 0.05)
    reward_risk = st.slider("Reward : Risk Ratio", 1.0, 4.0, 2.0, 0.5)

    try:
        health = requests.get(f"{api_url}/health", timeout=5).json()
        st.success(f"API OK — RAG ready: {health.get('rag_ready')}")
        if health.get("ingested_files"):
            st.caption("Dokumen ter-ingest: " + ", ".join(health["ingested_files"]))
    except Exception:
        st.error("Backend tidak terjangkau. Jalankan: uvicorn rag_financial_api:app")

tab_analyze, tab_upload, tab_qa = st.tabs(["📈 Analisis Saham", "📄 Upload Laporan", "💬 Tanya Laporan"])

# ---------------------------------------------------------------------------
with tab_upload:
    st.subheader("Upload & Ingest Laporan Keuangan (PDF)")
    pdf_file = st.file_uploader("Pilih file PDF (laporan Q1–Q4 / tahunan)", type=["pdf"])
    if pdf_file and st.button("🚀 Proses ke Vector DB", type="primary"):
        with st.spinner("Meng-ingest dokumen..."):
            try:
                resp = requests.post(
                    f"{api_url}/upload-pdf",
                    files={"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")},
                    timeout=300,
                )
                if resp.ok:
                    data = resp.json()
                    st.success(f"✅ {data['message']} ({data['pages_processed']} halaman)")
                else:
                    st.error(f"Gagal: {resp.json().get('detail', resp.text)}")
            except Exception as exc:
                st.error(f"Error koneksi: {exc}")

# ---------------------------------------------------------------------------
with tab_qa:
    st.subheader("Tanya Jawab Laporan Keuangan (RAG)")
    question = st.text_area("Pertanyaan", placeholder="Contoh: Berapa laba bersih kuartal terakhir dan bagaimana trennya?")
    top_k = st.slider("Jumlah sumber (top_k)", 1, 10, 3)
    if st.button("🔍 Tanya AI") and question.strip():
        with st.spinner("Mencari jawaban dari dokumen..."):
            try:
                resp = requests.post(
                    f"{api_url}/query",
                    json={"query": question, "top_k": top_k},
                    timeout=120,
                )
                if resp.ok:
                    data = resp.json()
                    st.markdown("#### 💡 Jawaban")
                    st.write(data["answer"])
                    with st.expander("📚 Sumber kutipan"):
                        for i, src in enumerate(data["sources"], start=1):
                            st.markdown(
                                f"**{i}. {src.get('file_name')} — hal. {src.get('page_label')} "
                                f"(skor {src.get('score', 0):.3f})**"
                            )
                            st.caption(src["content"][:600] + ("..." if len(src["content"]) > 600 else ""))
                else:
                    st.error(f"Gagal: {resp.json().get('detail', resp.text)}")
            except Exception as exc:
                st.error(f"Error koneksi: {exc}")

# ---------------------------------------------------------------------------
with tab_analyze:
    st.subheader("Analisis Multi-Engine + Rekomendasi Posisi")
    col_t, col_b = st.columns([3, 1])
    ticker = col_t.text_input("Ticker", value="BBCA.JK", help="Saham IDX memakai sufiks .JK")
    run = col_b.button("⚡ Analisis Sekarang", type="primary", use_container_width=True)

    if run and ticker.strip():
        with st.spinner(f"Menganalisis {ticker}..."):
            try:
                resp = requests.post(
                    f"{api_url}/analyze-stock",
                    json={
                        "ticker": ticker,
                        "total_capital": total_capital,
                        "max_risk_pct": max_risk_pct,
                        "atr_multiplier": atr_multiplier,
                        "win_rate": win_rate,
                        "reward_risk_ratio": reward_risk,
                    },
                    timeout=180,
                )
            except Exception as exc:
                st.error(f"Error koneksi: {exc}")
                st.stop()

        if not resp.ok:
            st.error(f"Gagal: {resp.json().get('detail', resp.text)}")
            st.stop()

        data = resp.json()
        signal = data["signal"]
        signal_color = {
            "STRONG BUY": "🟢", "BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "STRONG SELL": "🔴",
        }.get(signal, "⚪")

        st.markdown(f"## {signal_color} Sinyal: **{signal}** — Skor Total: **{data['total_score']:.1f} / 100**")

        c1, c2, c3 = st.columns(3)
        comps = data["scores"]["components"]
        c1.metric("Fundamental (50%)", f"{comps['fundamental']:.1f}", help=f"Sumber: {data['fundamental'].get('source')}")
        c2.metric("Technical (30%)", f"{comps['technical']:.1f}")
        c3.metric("Sentiment (20%)", f"{comps['sentiment']:.1f}", data["sentiment"].get("label", ""))

        st.divider()
        left, right = st.columns(2)

        with left:
            st.markdown("### 📊 Indikator Teknikal")
            ind = data["technical"]["indicators"]
            st.dataframe(
                pd.DataFrame(
                    {
                        "Indikator": [
                            "Harga Terakhir", "EMA 20", "EMA 50", "EMA 200",
                            "RSI 14", "MACD", "MACD Signal", "ATR 14",
                            "Support", "Resistance",
                        ],
                        "Nilai": [
                            ind["last_price"], ind["ema_20"], ind["ema_50"], ind["ema_200"],
                            ind["rsi_14"], ind["macd"], ind["macd_signal"], ind["atr_14"],
                            ind["support"], ind["resistance"],
                        ],
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )

        with right:
            st.markdown("### 🛡️ Rencana Risiko & Posisi")
            rp = data["risk_plan"]
            st.dataframe(
                pd.DataFrame(
                    {
                        "Parameter": [
                            "Harga Entry", "Stop Loss (ATR)", "Take Profit",
                            "Lot Direkomendasikan", "Total Alokasi (IDR)",
                            "Maks. Potensi Rugi (IDR)", "Eksposur Portofolio (%)",
                            "Fractional Kelly",
                        ],
                        "Nilai": [
                            f"{rp['entry_price']:,.0f}",
                            f"{rp['stop_loss_price']:,.0f}",
                            f"{rp['take_profit_price']:,.0f}",
                            rp["recommended_lots"],
                            f"{rp['total_allocation_idr']:,.0f}",
                            f"{rp['max_potential_loss_idr']:,.0f}",
                            f"{rp['portfolio_exposure_pct']:.2f}",
                            rp["kelly_fraction"],
                        ],
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )
            for warning in rp.get("warnings", []):
                st.warning(warning)

        if data["sentiment"].get("details"):
            with st.expander("📰 Rincian Sentimen Berita"):
                st.dataframe(pd.DataFrame(data["sentiment"]["details"]), hide_index=True, use_container_width=True)

        if data["fundamental"].get("rationale"):
            with st.expander("🧾 Rasional Fundamental (RAG)"):
                st.write(data["fundamental"]["rationale"])
        if data["fundamental"].get("components"):
            with st.expander("🧮 Komponen Rasio Fundamental"):
                st.json(data["fundamental"]["components"])

        st.caption(
            "⚠️ Bukan nasihat keuangan. Output bersifat decision support — "
            "selalu lakukan riset mandiri sebelum bertransaksi."
        )
