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

tab_scan, tab_single, tab_gold, tab_test, tab_upload, tab_qa = st.tabs(
    ["🔎 Pemindai Otomatis", "📈 Analisis 1 Saham", "🥇 Emas & Makro",
     "🧪 Uji Mundur", "📄 Upload Laporan", "💬 Tanya Laporan"]
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
                "lots", "allocation", "max_loss", "exposure_pct",
            ]].rename(columns={
                "rank": "#", "ticker": "Saham", "signal": "Sinyal", "total_score": "Skor",
                "fundamental": "Fund", "technical": "Tek", "sentiment": "Sent",
                "price": "Harga", "rsi_14": "RSI", "stop_loss": "Stop Loss",
                "take_profit": "Take Profit", "lots": "Lot", "allocation": "Alokasi (Rp)",
                "max_loss": "Maks Rugi (Rp)", "exposure_pct": "Eksposur %",
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
                f"ukuran {best['lots']} lot — risiko maksimal Rp {best['max_loss']:,.0f}."
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
                              f"Rp {rp['total_allocation']:,.0f}",
                              f"Rp {rp['max_potential_loss']:,.0f}",
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
# TAB 3 — Emas & makro ekonomi
# ---------------------------------------------------------------------------
with tab_gold:
    st.subheader("Emas (XAU) — digerakkan makro ekonomi, bukan laporan keuangan")
    st.caption(
        "Emas tidak punya laba atau utang, sehingga mesin fundamental diganti "
        "**Skor Makro**: suku bunga riil, kekuatan dolar, ekspektasi inflasi, dan imbal hasil obligasi."
    )

    gcol1, gcol2 = st.columns([2, 1])
    with gcol1:
        gold_capital = st.number_input(
            "Modal untuk emas (USD)", min_value=100.0, value=10_000.0, step=500.0,
            help="Harga emas dihitung dalam dolar AS, jadi modalnya juga dalam USD.",
        )
    with gcol2:
        st.write("")
        st.write("")
        run_gold = st.button("🥇 Analisis Emas", type="primary",
                             use_container_width=True, disabled=not api_ok)

    gold_news = st.text_area(
        "Berita emas tambahan (opsional, satu judul per baris)",
        placeholder="Contoh: Bank sentral China kembali menambah cadangan emas",
        help="Untuk emas, berita krisis/perang justru mendorong harga NAIK.",
    )

    if run_gold:
        with st.spinner("Mengambil harga emas dan data makro…"):
            try:
                extra = [h.strip() for h in gold_news.split("\n") if h.strip()]
                resp = requests.post(
                    f"{api_url}/analyze-gold",
                    json={
                        "total_capital": gold_capital,
                        "max_risk_pct": max_risk_pct,
                        "atr_multiplier": atr_multiplier,
                        "win_rate": win_rate,
                        "reward_risk_ratio": reward_risk,
                        "extra_headlines": extra or None,
                    },
                    timeout=300,
                )
                if resp.ok:
                    st.session_state["gold"] = resp.json()
                elif resp.status_code == 429:
                    st.warning("⏳ Penyedia data membatasi permintaan. Tunggu sebentar lalu ulangi.")
                else:
                    st.error(_detail(resp))
            except requests.Timeout:
                st.error("Waktu tunggu habis saat mengambil data emas.")
            except Exception as exc:
                st.error(f"Gagal menghubungi backend: {exc}")

    g = st.session_state.get("gold")
    if g:
        ind = g["technical"]["indicators"]
        comps = g["scores"]["components"]
        status = g["market_status"]

        st.markdown(
            f"## {SIGNAL_ICON.get(g['signal'], '⚪')} {g['signal']} — "
            f"skor **{g['total_score']:.1f} / 100**"
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"Harga ({g['quote_unit']})", f"${ind['last_price']:,.2f}")
        m2.metric("Makro (50%)", f"{comps['macro']:.1f}")
        m3.metric("Teknikal (30%)", f"{comps['technical']:.1f}")
        m4.metric("Sentimen (20%)", f"{comps['sentiment']:.1f}",
                  g["sentiment"].get("label", ""))

        buka = "🟢 BUKA" if status["is_open"] else "🔴 TUTUP"
        st.info(
            f"**Pasar {buka}** — {status['reason']}  \n"
            f"Sumber harga: {g['price_source']['label']} · {g['price_freshness']['description']}  \n"
            f"Waktu setempat: {status['local_time_jakarta']}"
        )

        for w in g.get("warnings", []):
            st.warning(f"⚠️ {w}")

        # --- Rincian skor makro ---
        macro = g["macro"]
        st.markdown(
            f"### 🌍 Skor Makro {macro['score']:.1f}/100 "
            f"· kelengkapan data {macro['completeness_pct']}%"
        )
        if macro.get("breakdown"):
            macro_rows = [
                {
                    "Faktor": v["label"],
                    "Angka": v["reading"],
                    "Poin": f"{v['points']}/{v['max_points']}",
                    "Tafsiran": v["interpretation"],
                    "Per tanggal": v["as_of"],
                    "Sumber": v["source"],
                }
                for v in macro["breakdown"].values()
            ]
            st.dataframe(pd.DataFrame(macro_rows), hide_index=True, use_container_width=True)

        ctx = macro.get("context", {})
        if ctx:
            c1, c2 = st.columns(2)
            fed = ctx.get("fed_funds_rate", {})
            cpi = ctx.get("cpi", {})
            if fed.get("value") is not None:
                c1.metric("Suku bunga The Fed", f"{fed['value']:.2f}%",
                          help=f"Per {fed.get('as_of')} · {fed.get('source')}")
            if cpi.get("yoy_pct") is not None:
                c2.metric("Inflasi AS (tahunan)", f"{cpi['yoy_pct']:.2f}%",
                          help=f"Per {cpi.get('as_of')} · {cpi.get('source')}")

        # --- Rencana posisi ---
        st.markdown("### 🛡️ Rencana Posisi")
        rp = g["risk_plan"]
        st.dataframe(
            pd.DataFrame({
                "Parameter": ["Harga masuk", "Stop loss", "Take profit",
                              f"Ukuran ({rp['unit_name']})", "Total alokasi",
                              "Maks. rugi", "Eksposur portofolio"],
                "Nilai": [f"${rp['entry_price']:,.2f}", f"${rp['stop_loss_price']:,.2f}",
                          f"${rp['take_profit_price']:,.2f}", f"{rp['recommended_units']}",
                          f"${rp['total_allocation']:,.2f}",
                          f"${rp['max_potential_loss']:,.2f}",
                          f"{rp['portfolio_exposure_pct']:.2f}%"],
            }),
            hide_index=True, use_container_width=True,
        )
        for w in rp.get("warnings", []):
            st.warning(w)

        if g["sentiment"].get("details"):
            with st.expander("📰 Berita yang dinilai (untuk emas, krisis = positif)"):
                st.dataframe(pd.DataFrame(g["sentiment"]["details"]),
                             hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# TAB 4 — Uji mundur (backtest)
# ---------------------------------------------------------------------------
with tab_test:
    st.subheader("Apakah sinyal ini benar-benar terbukti?")
    st.caption(
        "Menguji aturan sinyal pada data bertahun-tahun ke belakang — "
        "**tanpa mengintip data masa depan**. Hasilnya juga mengukur win rate "
        "sesungguhnya, menggantikan angka yang selama ini Anda isi manual."
    )

    bcol1, bcol2, bcol3 = st.columns([2, 1, 1])
    bt_ticker = bcol1.text_input("Simbol yang diuji", value="BBCA.JK",
                                 help="Saham IDX pakai .JK · emas: GC=F · S&P 500: SPY")
    bt_period = bcol2.selectbox("Panjang riwayat", ["5y", "10y", "max"], index=1)
    bt_threshold = bcol3.slider("Ambang masuk", 40, 90, 55, 5)
    run_bt = st.button("🧪 Jalankan Uji Mundur", type="primary",
                       use_container_width=True, disabled=not api_ok)

    if run_bt and bt_ticker.strip():
        with st.spinner("Menguji ribuan bar data… ini bisa memakan waktu"):
            try:
                resp = requests.post(
                    f"{api_url}/backtest",
                    json={
                        "ticker": bt_ticker,
                        "period": bt_period,
                        "entry_threshold": float(bt_threshold),
                        "atr_multiplier": atr_multiplier,
                        "reward_risk_ratio": reward_risk,
                        "include_trades": True,
                    },
                    timeout=600,
                )
                if resp.ok:
                    st.session_state["backtest"] = resp.json()
                elif resp.status_code == 422:
                    st.error(_detail(resp))
                else:
                    st.error(_detail(resp))
            except requests.Timeout:
                st.error("Waktu tunggu habis. Coba periode yang lebih pendek.")
            except Exception as exc:
                st.error(f"Gagal menghubungi backend: {exc}")

    bt = st.session_state.get("backtest")
    if bt:
        s = bt["stats"]
        if not s.get("trades"):
            st.warning(s.get("verdict", "Tidak ada transaksi pada periode ini."))
        else:
            st.markdown(
                f"### {bt.get('ticker')} · {bt['period']['from']} → {bt['period']['to']} "
                f"({bt['period']['bars_tested']:,} hari diuji)"
            )

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Transaksi", s["trades"])
            base = s.get("random_baseline_win_rate")
            k2.metric(
                "Win rate nyata", f"{s['win_rate']*100:.1f}%",
                delta=f"{s['edge_vs_random_pp']:+.1f} pp vs acak" if s.get("edge_vs_random_pp") is not None else None,
                help="Bandingkan dengan garis acak, bukan dengan 100%.",
            )
            k3.metric("Faktor profit", s["profit_factor"] or "—",
                      help="Di atas 1 berarti untung; di atas 1,5 tergolong baik.")
            k4.metric("Ekspektansi", f"{s['expectancy_pct']}%",
                      help="Rata-rata hasil per transaksi.")

            # Win rate rendah itu wajar — yang menentukan adalah selisih
            # terhadap titik masuk acak pada aturan keluar yang sama.
            if base is not None:
                noise = s.get("random_baseline_noise_pp") or 0
                if s.get("edge_is_significant"):
                    st.success(
                        f"✅ **Win rate {s['win_rate']*100:.1f}% itu wajar** — masuk acak "
                        f"pun hanya menghasilkan {base*100:.1f}% pada aturan keluar yang sama. "
                        f"Sinyal ini unggul **{s['edge_vs_random_pp']:+.1f} poin persen**, "
                        f"di luar rentang kebetulan (±{noise:.1f}) — pemilihan waktu masuk memang menambah nilai."
                    )
                else:
                    st.warning(
                        f"⚠️ **Win rate {s['win_rate']*100:.1f}% itu wajar secara matematis** — "
                        f"masuk acak pun menghasilkan {base*100:.1f}% pada aturan keluar yang sama. "
                        f"Tetapi selisihnya hanya **{s['edge_vs_random_pp']:+.1f} poin persen**, masih di "
                        f"dalam rentang kebetulan (±{noise:.1f}). Artinya keuntungan yang ada "
                        "terutama berasal dari **manajemen risiko**, bukan dari ketepatan sinyal."
                    )

            st.markdown("#### Perbandingan jujur terhadap sekadar beli lalu tahan")
            banding = pd.DataFrame({
                "Ukuran": ["Total hasil", "Penurunan terdalam",
                           "Hasil per satuan risiko", "Waktu terpapar pasar"],
                "Strategi ini": [
                    f"{s['total_return_pct']}%", f"{s['max_drawdown_pct']}%",
                    s["return_per_drawdown"] or "—", f"{s['market_exposure_pct']}%",
                ],
                "Beli & tahan": [
                    f"{s['buy_and_hold_pct']}%", f"{s['buy_and_hold_max_drawdown_pct']}%",
                    s["buy_and_hold_return_per_drawdown"] or "—", "100%",
                ],
            })
            st.dataframe(banding, hide_index=True, use_container_width=True)

            if s["beats_buy_and_hold"]:
                st.success(s["verdict"])
            else:
                st.warning(s["verdict"])

            o = s["outcomes"]
            st.caption(
                f"Rincian penutupan posisi: {o['take_profit']} kena target · "
                f"{o['stop_loss']} kena stop loss · {o['timeout']} habis waktu · "
                f"rata-rata ditahan {s['avg_holding_days']} hari."
            )

            # --- Kalibrasi risiko ---
            calib = bt.get("calibration", {})
            st.markdown("#### 🎯 Kalibrasi ukuran posisi")
            if calib.get("usable"):
                st.success(
                    f"**Win rate terukur {calib['win_rate']*100:.1f}%** "
                    f"(dari {calib['sample_size']} transaksi) · "
                    f"Reward:Risk nyata {calib['reward_risk_ratio']}.  \n"
                    "Isikan angka ini ke panel kiri agar ukuran posisi memakai "
                    "hasil pengujian, bukan tebakan."
                )
                if abs(calib["win_rate"] - win_rate) > 0.03:
                    arah = "lebih rendah" if calib["win_rate"] < win_rate else "lebih tinggi"
                    st.warning(
                        f"⚠️ Win rate yang Anda pakai sekarang ({win_rate*100:.0f}%) "
                        f"{arah} dari hasil uji ({calib['win_rate']*100:.1f}%). "
                        + ("Ukuran posisi Anda kemungkinan terlalu besar."
                           if calib["win_rate"] < win_rate else
                           "Ukuran posisi Anda kemungkinan terlalu kecil.")
                    )
            else:
                st.info(f"Belum bisa dipakai untuk kalibrasi: {calib.get('reason')}")

            with st.expander("📋 Asumsi & keterbatasan uji ini"):
                for a in bt["assumptions"]:
                    st.markdown(f"- {a}")

            if bt.get("trades"):
                with st.expander(f"📜 Rincian {len(bt['trades'])} transaksi"):
                    st.dataframe(pd.DataFrame(bt["trades"]), hide_index=True,
                                 use_container_width=True)
                    st.download_button(
                        "⬇️ Unduh transaksi (CSV)",
                        data=pd.DataFrame(bt["trades"]).to_csv(index=False).encode("utf-8"),
                        file_name=f"backtest-{bt.get('ticker','hasil')}.csv",
                        mime="text/csv",
                    )


# ---------------------------------------------------------------------------
# TAB 5 — Upload laporan keuangan
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
# TAB 5 — Tanya jawab RAG
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
