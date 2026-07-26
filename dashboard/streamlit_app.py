"""Project Aegis — Streamlit Dashboard (mode otomatis penuh).

Antarmuka untuk:
- 🔎 Pemindai otomatis: analisis banyak saham sekaligus, diperingkat
- 📈 Analisis satu saham: data harga diambil otomatis dari internet
- 📄 Upload laporan keuangan PDF + tanya jawab RAG

Jalankan: streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("AEGIS_API_URL", "http://localhost:8000")

SIGNAL_ICON = {
    "STRONG BUY": "🟢", "BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "STRONG SELL": "🔴",
}


def _detail(resp) -> str:
    """Ambil pesan kesalahan backend; tahan terhadap respons non-JSON."""
    try:
        return resp.json().get("detail", resp.text)
    except Exception:
        return resp.text or f"Kesalahan HTTP {resp.status_code}"

st.set_page_config(page_title="Aegis — Stock AI Copilot", page_icon="🛡️", layout="wide")
st.title("🛡️ Project Aegis — Stock AI Copilot")
st.caption("Otomatis: data pasar, indikator, sentimen, fundamental, dan ukuran posisi — dalam satu klik.")


# ---------------------------------------------------------------------------
# Sidebar: koneksi + parameter modal/risiko
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Pengaturan")
    api_url = st.text_input("Alamat backend", value=API_URL)

    api_ok = False
    try:
        health = requests.get(f"{api_url}/health", timeout=5).json()
        api_ok = True
        st.success("Backend terhubung")
        if health.get("ingested_files"):
            st.caption("Laporan ter-ingest: " + ", ".join(health["ingested_files"]))
    except Exception:
        st.error("Backend belum jalan. Jalankan dulu:\n\n`uvicorn rag_financial_api:app`")

    st.divider()
    st.subheader("💰 Modal & Risiko")
    total_capital = st.number_input(
        "Total modal (IDR)", min_value=1_000_000, value=100_000_000, step=1_000_000
    )
    max_risk_pct = st.slider("Risiko per transaksi (%)", 0.5, 10.0, 2.0, 0.5) / 100
    atr_multiplier = st.slider("ATR multiplier (k)", 1.0, 3.0, 2.0, 0.25)
    win_rate = st.slider("Win rate historis", 0.30, 0.80, 0.55, 0.05)
    reward_risk = st.slider("Reward : Risk", 1.0, 4.0, 2.0, 0.5)

    st.divider()
    if st.button("🧹 Kosongkan cache data", use_container_width=True):
        try:
            requests.post(f"{api_url}/cache/clear", timeout=10)
            st.toast("Cache dikosongkan — data akan diambil ulang.")
        except Exception as exc:
            st.warning(f"Gagal: {exc}")

risk_params = {
    "total_capital": total_capital,
    "max_risk_pct": max_risk_pct,
    "atr_multiplier": atr_multiplier,
    "win_rate": win_rate,
    "reward_risk_ratio": reward_risk,
}

tab_scan, tab_single, tab_upload, tab_qa = st.tabs(
    ["🔎 Pemindai Otomatis", "📈 Analisis 1 Saham", "📄 Upload Laporan", "💬 Tanya Laporan"]
)


# ---------------------------------------------------------------------------
# TAB 1 — Pemindai otomatis
# ---------------------------------------------------------------------------
with tab_scan:
    st.subheader("Pindai banyak saham sekaligus, urutkan yang terbaik")

    watchlists = {}
    if api_ok:
        try:
            watchlists = requests.get(f"{api_url}/watchlists", timeout=10).json()["watchlists"]
        except Exception:
            watchlists = {}

    labels = {
        "idx_bluechip": "IDX — Saham Blue Chip",
        "idx_energy_mining": "IDX — Energi & Tambang",
        "idx_consumer_retail": "IDX — Konsumer & Ritel",
        "us_megacap": "AS — Mega Cap",
    }

    col_a, col_b = st.columns([2, 1])
    with col_a:
        mode = st.radio(
            "Sumber daftar saham",
            ["Preset watchlist", "Daftar sendiri"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if mode == "Preset watchlist" and watchlists:
            choice = st.selectbox(
                "Pilih watchlist",
                options=list(watchlists.keys()),
                format_func=lambda k: labels.get(k, k),
            )
            st.caption("Isi: " + ", ".join(watchlists[choice]))
            payload_source = {"watchlist": choice}
        else:
            custom = st.text_area(
                "Ticker (pisahkan koma atau baris baru)",
                value="BBCA.JK, BBRI.JK, TLKM.JK, ASII.JK",
                help="Saham Indonesia memakai akhiran .JK",
            )
            tickers = [t.strip() for t in custom.replace("\n", ",").split(",") if t.strip()]
            payload_source = {"tickers": tickers}

    with col_b:
        min_score = st.slider("Saring skor minimal", 0, 100, 0, 5)
        only_buy = st.checkbox("Hanya tampilkan sinyal BUY", value=False)

    if st.button("🚀 Pindai Sekarang", type="primary", use_container_width=True, disabled=not api_ok):
        with st.spinner("Mengambil data pasar dan menganalisis…"):
            try:
                resp = requests.post(
                    f"{api_url}/scan",
                    json={**payload_source, **risk_params, "min_score": min_score},
                    timeout=600,
                )
                if resp.ok:
                    st.session_state["scan"] = resp.json()
                elif resp.status_code == 429:
                    st.warning(
                        "⏳ Penyedia data sedang membatasi permintaan. "
                        "Tunggu sekitar satu menit, lalu coba lagi dengan daftar lebih pendek."
                    )
                else:
                    st.error(_detail(resp))
            except requests.Timeout:
                st.error("Waktu tunggu habis. Coba kurangi jumlah saham yang dipindai.")
            except Exception as exc:
                st.error(f"Gagal menghubungi backend: {exc}")

    scan = st.session_state.get("scan")
    if scan:
        rows = scan["table"]
        if only_buy:
            rows = [r for r in rows if r["signal"] in ("STRONG BUY", "BUY")]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Saham dianalisis", scan["analyzed"])
        c2.metric("Kandidat BUY", scan["buy_candidates"])
        c3.metric("Pilihan teratas", scan["top_pick"] or "—")
        waktu = datetime.fromisoformat(scan["scanned_at"].replace("Z", "+00:00"))
        c4.metric("Dipindai pukul", waktu.strftime("%H:%M UTC"))

        if not rows:
            st.info("Tidak ada saham yang lolos filter. Turunkan skor minimal atau matikan filter BUY.")
        else:
            df = pd.DataFrame(rows)
            df["signal"] = df["signal"].map(lambda s: f"{SIGNAL_ICON.get(s, '⚪')} {s}")
            tampil = df[[
                "rank", "ticker", "signal", "total_score", "fundamental", "technical",
                "sentiment", "price", "rsi_14", "stop_loss", "take_profit",
                "lots", "allocation_idr", "max_loss_idr", "exposure_pct",
            ]].rename(columns={
                "rank": "#", "ticker": "Saham", "signal": "Sinyal", "total_score": "Skor",
                "fundamental": "Fund", "technical": "Tek", "sentiment": "Sent",
                "price": "Harga", "rsi_14": "RSI", "stop_loss": "Stop Loss",
                "take_profit": "Take Profit", "lots": "Lot", "allocation_idr": "Alokasi (Rp)",
                "max_loss_idr": "Maks Rugi (Rp)", "exposure_pct": "Eksposur %",
            })
            st.dataframe(
                tampil,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Skor": st.column_config.ProgressColumn(
                        "Skor", min_value=0, max_value=100, format="%.1f"
                    ),
                    "Harga": st.column_config.NumberColumn(format="%.0f"),
                    "Stop Loss": st.column_config.NumberColumn(format="%.0f"),
                    "Take Profit": st.column_config.NumberColumn(format="%.0f"),
                    "Alokasi (Rp)": st.column_config.NumberColumn(format="%.0f"),
                    "Maks Rugi (Rp)": st.column_config.NumberColumn(format="%.0f"),
                },
            )

            best = rows[0]
            st.success(
                f"**{best['ticker']}** memimpin dengan skor {best['total_score']:.1f} "
                f"({best['signal']}). Rencana: masuk di {best['price']:,.0f}, "
                f"stop loss {best['stop_loss']:,.0f}, target {best['take_profit']:,.0f}, "
                f"ukuran {best['lots']} lot — risiko maksimal Rp {best['max_loss_idr']:,.0f}."
            )

            st.download_button(
                "⬇️ Unduh hasil (CSV)",
                data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
                file_name=f"aegis-scan-{waktu.strftime('%Y%m%d-%H%M')}.csv",
                mime="text/csv",
            )

        if scan.get("errors"):
            with st.expander(f"⚠️ {len(scan['errors'])} saham gagal dianalisis"):
                st.dataframe(pd.DataFrame(scan["errors"]), hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# TAB 2 — Analisis satu saham
# ---------------------------------------------------------------------------
with tab_single:
    st.subheader("Analisis mendalam satu saham")
    col_t, col_b = st.columns([3, 1])
    ticker = col_t.text_input("Ticker", value="BBCA.JK", help="Saham Indonesia memakai akhiran .JK")
    run = col_b.button("⚡ Analisis", type="primary", use_container_width=True, disabled=not api_ok)

    if run and ticker.strip():
        with st.spinner(f"Menganalisis {ticker}…"):
            try:
                resp = requests.post(
                    f"{api_url}/analyze-stock", json={"ticker": ticker, **risk_params}, timeout=180
                )
                if resp.ok:
                    st.session_state["single"] = resp.json()
                elif resp.status_code == 429:
                    st.warning("⏳ Penyedia data membatasi permintaan. Tunggu sebentar lalu ulangi.")
                elif resp.status_code == 404:
                    st.error(
                        f"Ticker '{ticker}' tidak ditemukan. "
                        "Saham Indonesia memakai akhiran .JK — contoh: BBCA.JK"
                    )
                else:
                    st.error(_detail(resp))
            except requests.Timeout:
                st.error("Waktu tunggu habis saat mengambil data. Coba lagi.")
            except Exception as exc:
                st.error(f"Gagal menghubungi backend: {exc}")

    data = st.session_state.get("single")
    if data:
        signal = data["signal"]
        st.markdown(
            f"## {SIGNAL_ICON.get(signal, '⚪')} {signal} — "
            f"skor **{data['total_score']:.1f} / 100** · {data['ticker']}"
        )

        comps = data["scores"]["components"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Fundamental (50%)", f"{comps['fundamental']:.1f}",
                  help=f"Sumber: {data['fundamental'].get('source')}")
        c2.metric("Teknikal (30%)", f"{comps['technical']:.1f}")
        c3.metric("Sentimen (20%)", f"{comps['sentiment']:.1f}", data["sentiment"].get("label", ""))

        st.divider()
        left, right = st.columns(2)
        ind = data["technical"]["indicators"]
        with left:
            st.markdown("### 📊 Indikator")
            st.dataframe(
                pd.DataFrame({
                    "Indikator": ["Harga", "EMA 20", "EMA 50", "EMA 200", "RSI 14",
                                  "MACD", "MACD Signal", "ATR 14", "Support", "Resistance"],
                    "Nilai": [ind["last_price"], ind["ema_20"], ind["ema_50"], ind["ema_200"],
                              ind["rsi_14"], ind["macd"], ind["macd_signal"], ind["atr_14"],
                              ind["support"], ind["resistance"]],
                }),
                hide_index=True, use_container_width=True,
            )
        with right:
            st.markdown("### 🛡️ Rencana Posisi")
            rp = data["risk_plan"]
            st.dataframe(
                pd.DataFrame({
                    "Parameter": ["Harga masuk", "Stop loss", "Take profit", "Lot",
                                  "Total alokasi", "Maks. rugi", "Eksposur portofolio"],
                    "Nilai": [f"{rp['entry_price']:,.0f}", f"{rp['stop_loss_price']:,.0f}",
                              f"{rp['take_profit_price']:,.0f}", f"{rp['recommended_lots']} lot",
                              f"Rp {rp['total_allocation_idr']:,.0f}",
                              f"Rp {rp['max_potential_loss_idr']:,.0f}",
                              f"{rp['portfolio_exposure_pct']:.2f} %"],
                }),
                hide_index=True, use_container_width=True,
            )
            for w in rp.get("warnings", []):
                st.warning(w)

        if data["sentiment"].get("details"):
            with st.expander("📰 Berita yang dinilai"):
                st.dataframe(pd.DataFrame(data["sentiment"]["details"]),
                             hide_index=True, use_container_width=True)
        if data["fundamental"].get("rationale"):
            with st.expander("🧾 Alasan fundamental (dari laporan PDF)"):
                st.write(data["fundamental"]["rationale"])


# ---------------------------------------------------------------------------
# TAB 3 — Upload laporan keuangan
# ---------------------------------------------------------------------------
with tab_upload:
    st.subheader("Upload laporan keuangan (PDF)")
    st.caption("Setelah di-upload, skor fundamental saham diambil dari isi laporan, bukan rasio umum.")
    pdf_file = st.file_uploader("Pilih file PDF laporan kuartalan / tahunan", type=["pdf"])
    if pdf_file and st.button("🚀 Proses laporan", type="primary", disabled=not api_ok):
        with st.spinner("Membaca dan mengindeks dokumen…"):
            try:
                resp = requests.post(
                    f"{api_url}/upload-pdf",
                    files={"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")},
                    timeout=600,
                )
                if resp.ok:
                    d = resp.json()
                    st.success(f"✅ Selesai — {d['pages_processed']} halaman diproses.")
                elif resp.status_code == 503:
                    st.warning(
                        "Fitur baca laporan PDF membutuhkan kunci OpenAI. "
                        "Isi `OPENAI_API_KEY` di file `.env`, lalu jalankan ulang aplikasi. "
                        "Fitur lain tetap berfungsi tanpa kunci ini."
                    )
                else:
                    st.error(_detail(resp))
            except Exception as exc:
                st.error(f"Gagal: {exc}")


# ---------------------------------------------------------------------------
# TAB 4 — Tanya jawab RAG
# ---------------------------------------------------------------------------
with tab_qa:
    st.subheader("Tanya apa saja tentang laporan yang sudah di-upload")
    question = st.text_area(
        "Pertanyaan",
        placeholder="Contoh: Berapa laba bersih kuartal terakhir dan bagaimana trennya?",
    )
    top_k = st.slider("Jumlah kutipan sumber", 1, 10, 3)
    if st.button("🔍 Tanya", disabled=not api_ok) and question.strip():
        with st.spinner("Mencari jawaban di dalam dokumen…"):
            try:
                resp = requests.post(
                    f"{api_url}/query", json={"query": question, "top_k": top_k}, timeout=180
                )
                if resp.ok:
                    d = resp.json()
                    st.markdown("#### 💡 Jawaban")
                    st.write(d["answer"])
                    with st.expander("📚 Kutipan sumber"):
                        for i, src in enumerate(d["sources"], start=1):
                            st.markdown(
                                f"**{i}. {src.get('file_name')} — hal. {src.get('page_label')} "
                                f"(kemiripan {src.get('score', 0):.3f})**"
                            )
                            st.caption(
                                src["content"][:600] + ("…" if len(src["content"]) > 600 else "")
                            )
                elif resp.status_code == 400:
                    st.info("Belum ada laporan yang di-upload. Buka tab 📄 Upload Laporan dulu.")
                else:
                    st.error(_detail(resp))
            except Exception as exc:
                st.error(f"Gagal: {exc}")


st.caption(
    "⚠️ Ini alat bantu keputusan (decision support), bukan nasihat keuangan. "
    "Tidak ada sistem yang bisa memprediksi pasar dengan pasti — gunakan manajemen risiko "
    "dan lakukan riset mandiri sebelum bertransaksi."
)
