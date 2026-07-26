"""Pemantau berkala — merekam skor dan memberi tahu saat ada perubahan penting.

Jalankan di jendela terpisah dan biarkan berjalan:

    python scripts/watch.py                       # emas, tiap 60 menit
    python scripts/watch.py --interval 30         # tiap 30 menit
    python scripts/watch.py --stocks BBCA.JK TLKM.JK
    python scripts/watch.py --once                # sekali jalan lalu berhenti

Inilah bagian yang membuat "tidak ketinggalan" menjadi nyata: Anda tidak perlu
membuka aplikasi untuk tahu ada perubahan. Skrip merekam hasil analisis secara
berkala, membandingkannya dengan rekaman sebelumnya, dan hanya berbicara ketika
memang ada yang berubah.

Pemberitahuan ke Telegram bersifat opsional. Isi ``TELEGRAM_BOT_TOKEN`` dan
``TELEGRAM_CHAT_ID`` pada berkas ``.env`` bila ingin menerimanya di ponsel;
tanpa itu peringatan tetap tercatat di layar dan tersimpan di riwayat.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from services import alerts, history  # noqa: E402

load_dotenv()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def check_asset(asset: str, analyse) -> list[dict]:
    """Analisis satu aset, rekam hasilnya, kembalikan peringatan yang muncul."""
    try:
        analysis = analyse()
    except Exception as exc:
        print(f"[{_timestamp()}] {asset}: GAGAL dianalisis — {exc}")
        return []

    previous = history.get_latest(asset)
    history.record_snapshot(asset, analysis)
    current = history.get_latest(asset)

    found = alerts.evaluate(previous, current)
    score = analysis.get("total_score")
    signal = analysis.get("signal")
    if found:
        print(f"[{_timestamp()}] {asset}: {signal} ({score}) — {len(found)} perubahan:")
        for a in found:
            print(f"    {a['severity'].upper():7} {a['title']}")
    else:
        print(f"[{_timestamp()}] {asset}: {signal} ({score}) — tidak ada perubahan berarti.")
    return found


def run_once(watch_gold: bool, stocks: list[str]) -> list[dict]:
    from services.analysis import analyze_ticker
    from services.gold import analyze_gold

    all_alerts: list[dict] = []
    if watch_gold:
        all_alerts += check_asset("GOLD", lambda: analyze_gold())
    for ticker in stocks:
        all_alerts += check_asset(ticker.upper(), lambda t=ticker: analyze_ticker(t))
    return all_alerts


def main() -> None:
    parser = argparse.ArgumentParser(description="Pemantau berkala Project Aegis")
    parser.add_argument("--interval", type=int, default=60, help="Jeda dalam menit (bawaan 60)")
    parser.add_argument("--stocks", nargs="*", default=[], help="Ticker saham yang ikut dipantau")
    parser.add_argument("--no-gold", action="store_true", help="Jangan pantau emas")
    parser.add_argument("--once", action="store_true", help="Jalankan sekali lalu berhenti")
    args = parser.parse_args()

    watch_gold = not args.no_gold
    targets = (["GOLD"] if watch_gold else []) + [s.upper() for s in args.stocks]
    if not targets:
        print("Tidak ada yang dipantau. Pakai --stocks atau jangan sertakan --no-gold.")
        return

    print("=" * 68)
    print("  PEMANTAU AEGIS")
    print(f"  Memantau : {', '.join(targets)}")
    print(f"  Jeda     : {args.interval} menit" if not args.once else "  Mode     : sekali jalan")
    print(f"  Riwayat  : {history.DB_PATH}")
    telegram = alerts.send_telegram("")  # cek ketersediaan kredensial saja
    print(f"  Telegram : {'aktif' if telegram.get('sent') is not False or 'Tidak ada' in telegram.get('reason', '') else 'nonaktif — ' + telegram['reason'][:52]}")
    print("  Tekan Ctrl+C untuk berhenti.")
    print("=" * 68)

    try:
        while True:
            found = run_once(watch_gold, args.stocks)
            if found:
                pesan = alerts.format_for_messaging(found)
                hasil = alerts.send_telegram(pesan)
                if hasil["sent"]:
                    print(f"    -> pemberitahuan Telegram terkirim ({len(found)} peringatan)")
            if args.once:
                break
            time.sleep(max(60, args.interval * 60))
    except KeyboardInterrupt:
        print("\nPemantau dihentikan.")


if __name__ == "__main__":
    main()
