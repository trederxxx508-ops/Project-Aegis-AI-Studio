"""Alert Engine — memberi tahu hanya saat ada yang benar-benar berubah.

Pemberitahuan yang terlalu sering justru membuat orang berhenti membacanya,
dan pemberitahuan yang terlambat tidak ada gunanya. Modul ini membandingkan
rekaman terbaru dengan rekaman sebelumnya, lalu hanya melaporkan perubahan
yang layak mengganggu perhatian:

- Sinyal berpindah (mis. HOLD -> BUY)
- Skor melewati ambang keputusan (55 = zona beli, 40 = zona jual)
- Kesehatan hubungan makro berubah — terutama saat PUTUS
- Skor bergerak tajam walau sinyalnya belum berpindah
- Kelengkapan data makro turun (skor jadi kurang bisa dipercaya)

Setiap peringatan membawa nilai sebelum dan sesudah, sehingga bisa diperiksa,
bukan sekadar klaim "ada perubahan".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Ambang keputusan mengikuti scoring_engine
BUY_THRESHOLD = 55.0
SELL_THRESHOLD = 40.0
SHARP_MOVE_POINTS = 10.0

BULLISH_SIGNALS = ("STRONG BUY", "BUY")
BEARISH_SIGNALS = ("SELL", "STRONG SELL")

SEVERITY_ORDER = {"tinggi": 0, "sedang": 1, "rendah": 2}


def _alert(kind: str, severity: str, title: str, detail: str, **extra) -> dict:
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        **extra,
    }


def _signal_direction(previous: Optional[str], current: Optional[str]) -> str:
    """Apakah perpindahan sinyal menuju beli, menuju jual, atau netral."""
    if current in BULLISH_SIGNALS and previous not in BULLISH_SIGNALS:
        return "membaik"
    if current in BEARISH_SIGNALS and previous not in BEARISH_SIGNALS:
        return "memburuk"
    return "berubah"


def evaluate(previous: Optional[dict], current: dict) -> list[dict]:
    """Bandingkan dua rekaman, kembalikan daftar peringatan terurut kepentingan.

    ``previous`` boleh None (rekaman pertama) — tidak ada perubahan yang bisa
    dilaporkan, jadi hasilnya kosong. Merekam untuk pertama kali bukan kejadian
    yang layak memicu pemberitahuan.
    """
    if not previous:
        return []

    alerts: list[dict] = []
    asset = current.get("asset", "?")

    prev_signal, curr_signal = previous.get("signal"), current.get("signal")
    prev_score = previous.get("total_score")
    curr_score = current.get("total_score")

    # 1. Perpindahan sinyal — kejadian paling penting
    if prev_signal and curr_signal and prev_signal != curr_signal:
        arah = _signal_direction(prev_signal, curr_signal)
        alerts.append(_alert(
            "signal_change",
            "tinggi" if arah in ("membaik", "memburuk") else "sedang",
            f"{asset}: sinyal berubah {prev_signal} → {curr_signal}",
            f"Kondisi {arah}. Skor {prev_score} → {curr_score}.",
            previous_value=prev_signal, current_value=curr_signal, direction=arah,
        ))

    # 2. Melewati ambang keputusan
    if prev_score is not None and curr_score is not None:
        for threshold, nama in ((BUY_THRESHOLD, "zona beli"), (SELL_THRESHOLD, "zona jual")):
            if prev_score < threshold <= curr_score:
                alerts.append(_alert(
                    "threshold_cross", "sedang",
                    f"{asset}: skor naik melewati {threshold:.0f} ({nama})",
                    f"Skor {prev_score} → {curr_score}.",
                    previous_value=prev_score, current_value=curr_score,
                ))
            elif curr_score < threshold <= prev_score:
                alerts.append(_alert(
                    "threshold_cross", "sedang",
                    f"{asset}: skor turun melewati {threshold:.0f} ({nama})",
                    f"Skor {prev_score} → {curr_score}.",
                    previous_value=prev_score, current_value=curr_score,
                ))

        # 3. Pergerakan tajam walau sinyal belum berpindah
        move = curr_score - prev_score
        if abs(move) >= SHARP_MOVE_POINTS and prev_signal == curr_signal:
            alerts.append(_alert(
                "sharp_move", "sedang",
                f"{asset}: skor bergerak {move:+.1f} poin",
                f"Dari {prev_score} ke {curr_score} tanpa berpindah sinyal — "
                "perubahan sedang berlangsung.",
                previous_value=prev_score, current_value=curr_score,
            ))

    # 4. Kesehatan hubungan makro berubah
    prev_regime, curr_regime = previous.get("regime_status"), current.get("regime_status")
    if prev_regime and curr_regime and prev_regime != curr_regime:
        putus = curr_regime == "putus"
        alerts.append(_alert(
            "regime_change",
            "tinggi" if putus else "sedang",
            f"{asset}: hubungan makro {prev_regime} → {curr_regime}",
            (
                "Emas sedang TIDAK mengikuti suku bunga riil — skor makro kurang "
                "bisa diandalkan, bobotnya diturunkan otomatis."
                if putus else
                "Kesehatan hubungan makro berubah; bobot skor menyesuaikan."
            ),
            previous_value=prev_regime, current_value=curr_regime,
        ))

    # 5. Kelengkapan data makro menurun
    prev_complete = _completeness(previous)
    curr_complete = _completeness(current)
    if prev_complete is not None and curr_complete is not None and curr_complete < prev_complete:
        alerts.append(_alert(
            "data_quality", "rendah",
            f"{asset}: kelengkapan data makro turun {prev_complete}% → {curr_complete}%",
            "Sebagian indikator tidak berhasil diambil, sehingga skor kurang utuh.",
            previous_value=prev_complete, current_value=curr_complete,
        ))

    alerts.sort(key=lambda a: SEVERITY_ORDER.get(a["severity"], 9))
    for a in alerts:
        a["asset"] = asset
        a["detected_at"] = datetime.now(timezone.utc).isoformat()
    return alerts


def _completeness(row: dict) -> Optional[float]:
    payload = row.get("payload")
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if isinstance(payload, dict):
        return payload.get("macro_completeness")
    return None


def format_for_messaging(alerts: list[dict]) -> str:
    """Susun peringatan menjadi teks siap kirim (Telegram, email, catatan)."""
    if not alerts:
        return ""
    ikon = {"tinggi": "🚨", "sedang": "⚠️", "rendah": "ℹ️"}
    baris = ["*Aegis — perubahan terdeteksi*", ""]
    for a in alerts:
        baris.append(f"{ikon.get(a['severity'], '•')} {a['title']}")
        baris.append(f"   {a['detail']}")
    baris.append("")
    baris.append("_Alat bantu keputusan, bukan nasihat keuangan._")
    return "\n".join(baris)


def send_telegram(text: str, token: Optional[str] = None, chat_id: Optional[str] = None) -> dict:
    """Kirim peringatan ke Telegram bila kredensialnya tersedia.

    Sengaja opsional: tanpa kredensial, fungsi ini melaporkan bahwa pengiriman
    dilewati — bukan berpura-pura berhasil.
    """
    import os

    import requests

    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return {
            "sent": False,
            "reason": (
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi di .env — "
                "pengiriman dilewati."
            ),
        }
    if not text.strip():
        return {"sent": False, "reason": "Tidak ada peringatan untuk dikirim."}

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return {"sent": True, "reason": "Terkirim."}
    except Exception as exc:
        return {"sent": False, "reason": f"Gagal mengirim: {exc}"}
