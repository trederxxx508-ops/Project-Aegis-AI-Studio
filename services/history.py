"""Riwayat skor — menyimpan hasil analisis agar arah pergerakannya terlihat.

Tanpa riwayat, setiap analisis berdiri sendiri: pengguna tahu skor emas hari
ini 28, tetapi tidak tahu apakah itu turun dari 60 minggu lalu atau naik dari
15. **Arah pergerakan skor sering lebih berguna daripada angkanya hari ini**,
dan itu hanya bisa diketahui bila hasilnya disimpan.

Penyimpanan memakai SQLite: satu berkas, tanpa server, ikut berpindah bersama
folder proyek. Ini sengaja dipilih agar pengguna yang menjalankan aplikasi
lewat satu klik tidak perlu memasang basis data apa pun.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

DB_PATH = os.getenv("AEGIS_DB_PATH", "./aegis_history.db")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset         TEXT    NOT NULL,
    recorded_at   TEXT    NOT NULL,
    signal        TEXT,
    total_score   REAL,
    macro         REAL,
    fundamental   REAL,
    technical     REAL,
    sentiment     REAL,
    price         REAL,
    regime_status TEXT,
    payload       TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_asset_time
    ON snapshots (asset, recorded_at DESC);
"""


@contextmanager
def _connect(db_path: Optional[str] = None):
    path = db_path or DB_PATH
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_snapshot(asset: str, analysis: dict, db_path: Optional[str] = None) -> dict:
    """Simpan satu hasil analisis. ``analysis`` adalah keluaran analyze_* apa adanya."""
    components = (analysis.get("scores") or {}).get("components") or {}
    indicators = (analysis.get("technical") or {}).get("indicators") or {}
    regime_status = (analysis.get("macro_relationship") or {}).get("status")

    row = {
        "asset": asset.upper(),
        "recorded_at": analysis.get("analyzed_at") or datetime.now(timezone.utc).isoformat(),
        "signal": analysis.get("signal"),
        "total_score": analysis.get("total_score"),
        "macro": components.get("macro"),
        "fundamental": components.get("fundamental"),
        "technical": components.get("technical"),
        "sentiment": components.get("sentiment"),
        "price": indicators.get("last_price"),
        "regime_status": regime_status,
        "payload": json.dumps(
            {
                "weights": (analysis.get("scores") or {}).get("weights"),
                "warnings": analysis.get("warnings"),
                "macro_completeness": (analysis.get("macro") or {}).get("completeness_pct"),
            },
            ensure_ascii=False,
        ),
    }

    with _lock, _connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO snapshots
               (asset, recorded_at, signal, total_score, macro, fundamental,
                technical, sentiment, price, regime_status, payload)
               VALUES (:asset, :recorded_at, :signal, :total_score, :macro,
                       :fundamental, :technical, :sentiment, :price,
                       :regime_status, :payload)""",
            row,
        )
        row_id = cursor.lastrowid
    return {**row, "id": row_id}


def get_history(
    asset: str, days: int = 90, limit: int = 500, db_path: Optional[str] = None
) -> list[dict]:
    """Ambil riwayat satu aset, terbaru lebih dulu."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM snapshots
               WHERE asset = ? AND recorded_at >= ?
               ORDER BY recorded_at DESC LIMIT ?""",
            (asset.upper(), since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest(asset: str, db_path: Optional[str] = None) -> Optional[dict]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE asset = ? ORDER BY recorded_at DESC LIMIT 1",
            (asset.upper(),),
        ).fetchone()
    return dict(row) if row else None


def get_previous(asset: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Snapshot sebelum yang terakhir — pembanding untuk mendeteksi perubahan."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE asset = ? ORDER BY recorded_at DESC LIMIT 2",
            (asset.upper(),),
        ).fetchall()
    return dict(rows[1]) if len(rows) > 1 else None


def list_assets(db_path: Optional[str] = None) -> list[dict]:
    """Daftar aset yang punya riwayat, beserta jumlah dan waktu terakhirnya."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT asset, COUNT(*) AS snapshots, MAX(recorded_at) AS last_recorded
               FROM snapshots GROUP BY asset ORDER BY last_recorded DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def summarize_trend(asset: str, days: int = 30, db_path: Optional[str] = None) -> dict:
    """Arah pergerakan skor — inilah yang sering lebih berguna daripada angkanya."""
    rows = get_history(asset, days=days, db_path=db_path)
    if not rows:
        return {"asset": asset.upper(), "snapshots": 0, "trend": None,
                "note": "Belum ada riwayat. Jalankan analisis untuk mulai merekam."}
    if len(rows) == 1:
        return {"asset": asset.upper(), "snapshots": 1, "trend": None,
                "current_score": rows[0]["total_score"],
                "note": "Baru satu rekaman — arah belum bisa disimpulkan."}

    newest, oldest = rows[0], rows[-1]
    scores = [r["total_score"] for r in rows if r["total_score"] is not None]
    change = (newest["total_score"] or 0) - (oldest["total_score"] or 0)
    if change > 3:
        trend = "naik"
    elif change < -3:
        trend = "turun"
    else:
        trend = "datar"

    return {
        "asset": asset.upper(),
        "snapshots": len(rows),
        "period_days": days,
        "current_score": newest["total_score"],
        "oldest_score": oldest["total_score"],
        "change": round(change, 2),
        "trend": trend,
        "min_score": round(min(scores), 2) if scores else None,
        "max_score": round(max(scores), 2) if scores else None,
        "current_signal": newest["signal"],
        "first_recorded": oldest["recorded_at"],
        "last_recorded": newest["recorded_at"],
    }


def purge_older_than(days: int = 365, db_path: Optional[str] = None) -> int:
    """Hapus rekaman lama agar berkas tidak tumbuh tanpa batas."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _lock, _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM snapshots WHERE recorded_at < ?", (cutoff,))
        return cursor.rowcount


def stats(db_path: Optional[str] = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"]
    return {"total_snapshots": total, "assets": list_assets(db_path), "db_path": db_path or DB_PATH}
