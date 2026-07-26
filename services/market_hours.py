"""Jam perdagangan — agar harga tidak disajikan seolah selalu terkini.

Emas berjangka COMEX berdagang hampir sepanjang pekan (Minggu sore sampai
Jumat sore waktu New York), sementara Bursa Efek Indonesia hanya buka pada
jam kerja. Bila pasar sedang tutup, harga terakhir adalah harga penutupan —
dan itu harus dinyatakan terang-terangan, bukan ditampilkan seakan harga
sedang berjalan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
JAKARTA = ZoneInfo("Asia/Jakarta")

# COMEX (emas): Minggu 18:00 ET sampai Jumat 17:00 ET,
# dengan jeda harian pukul 17:00-18:00 ET.
GOLD_BREAK_START_HOUR = 17
GOLD_BREAK_END_HOUR = 18


def gold_market_status(now: datetime | None = None) -> dict:
    """Status pasar emas berjangka COMEX pada waktu tertentu."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ny_now = now.astimezone(NY)
    weekday = ny_now.weekday()  # Senin=0 ... Minggu=6
    hour = ny_now.hour

    if weekday == 5:  # Sabtu: tutup penuh
        is_open, reason = False, "Akhir pekan — pasar emas tutup (Sabtu)."
    elif weekday == 6:  # Minggu: buka mulai 18:00 ET
        is_open = hour >= GOLD_BREAK_END_HOUR
        reason = ("Sesi pekan baru sudah dibuka." if is_open
                  else "Akhir pekan — pasar buka kembali Minggu 18:00 waktu New York.")
    elif weekday == 4 and hour >= GOLD_BREAK_START_HOUR:  # Jumat sore
        is_open, reason = False, "Pekan perdagangan berakhir Jumat 17:00 waktu New York."
    elif GOLD_BREAK_START_HOUR <= hour < GOLD_BREAK_END_HOUR:
        is_open, reason = False, "Jeda harian pukul 17:00-18:00 waktu New York."
    else:
        is_open, reason = True, "Pasar sedang berjalan."

    return {
        "market": "COMEX Gold Futures",
        "is_open": is_open,
        "reason": reason,
        "local_time_ny": ny_now.strftime("%Y-%m-%d %H:%M %Z"),
        "local_time_jakarta": now.astimezone(JAKARTA).strftime("%Y-%m-%d %H:%M WIB"),
    }


def describe_price_freshness(last_bar_time: datetime, now: datetime | None = None) -> dict:
    """Jelaskan seberapa segar harga terakhir, dalam bahasa yang jelas."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if last_bar_time.tzinfo is None:
        last_bar_time = last_bar_time.replace(tzinfo=timezone.utc)
    last_bar_time = last_bar_time.astimezone(timezone.utc)

    delta = now - last_bar_time
    minutes = delta.total_seconds() / 60

    if minutes < 0:
        text = "Waktu data berada di masa depan — periksa jam sistem."
    elif minutes < 30:
        text = "Harga sangat baru (kurang dari 30 menit lalu)."
    elif minutes < 120:
        text = f"Harga berumur sekitar {int(minutes)} menit."
    elif delta < timedelta(days=1):
        text = f"Harga berumur sekitar {int(minutes // 60)} jam."
    else:
        text = f"Harga berumur {delta.days} hari — kemungkinan harga penutupan terakhir."

    return {
        "last_bar_utc": last_bar_time.isoformat(),
        "age_minutes": round(minutes, 1),
        "description": text,
        "is_intraday_fresh": minutes < 120,
    }
