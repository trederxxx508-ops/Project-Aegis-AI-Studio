"""Test riwayat skor & mesin peringatan."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from services import alerts, history


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "uji.db")


def _analysis(score, signal, macro=20.0, regime="normal", price=4000.0, when=None, completeness=100.0):
    return {
        "analyzed_at": (when or datetime.now(timezone.utc)).isoformat(),
        "signal": signal,
        "total_score": score,
        "scores": {
            "components": {"macro": macro, "technical": 45.0, "sentiment": 50.0},
            "weights": {"macro": 0.5, "technical": 0.3, "sentiment": 0.2},
        },
        "technical": {"indicators": {"last_price": price}},
        "macro_relationship": {"status": regime},
        "macro": {"completeness_pct": completeness},
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Riwayat
# ---------------------------------------------------------------------------

def test_snapshot_is_persisted_and_readable(db):
    history.record_snapshot("GOLD", _analysis(28.5, "SELL"), db_path=db)
    rows = history.get_history("GOLD", db_path=db)

    assert len(rows) == 1
    assert rows[0]["signal"] == "SELL"
    assert rows[0]["total_score"] == 28.5
    assert rows[0]["regime_status"] == "normal"
    assert rows[0]["price"] == 4000.0


def test_history_survives_reconnect(db):
    """Riwayat harus benar-benar tersimpan di disk, bukan hanya di memori."""
    history.record_snapshot("GOLD", _analysis(30.0, "SELL"), db_path=db)
    # Koneksi baru sepenuhnya
    assert len(history.get_history("GOLD", db_path=db)) == 1
    assert history.get_latest("GOLD", db_path=db)["total_score"] == 30.0


def test_asset_is_case_insensitive(db):
    history.record_snapshot("gold", _analysis(30.0, "SELL"), db_path=db)
    assert len(history.get_history("GOLD", db_path=db)) == 1


def test_latest_and_previous_are_ordered(db):
    now = datetime.now(timezone.utc)
    history.record_snapshot("GOLD", _analysis(20.0, "SELL", when=now - timedelta(days=2)), db_path=db)
    history.record_snapshot("GOLD", _analysis(60.0, "BUY", when=now), db_path=db)

    assert history.get_latest("GOLD", db_path=db)["total_score"] == 60.0
    assert history.get_previous("GOLD", db_path=db)["total_score"] == 20.0


def test_trend_reports_direction(db):
    now = datetime.now(timezone.utc)
    for i, score in enumerate([20.0, 35.0, 55.0]):
        history.record_snapshot(
            "GOLD", _analysis(score, "HOLD", when=now - timedelta(days=10 - i * 5)), db_path=db
        )
    trend = history.summarize_trend("GOLD", days=30, db_path=db)

    assert trend["snapshots"] == 3
    assert trend["trend"] == "naik"
    assert trend["change"] == pytest.approx(35.0)
    assert trend["min_score"] == 20.0 and trend["max_score"] == 55.0


def test_trend_admits_when_there_is_not_enough_data(db):
    assert history.summarize_trend("GOLD", db_path=db)["trend"] is None
    history.record_snapshot("GOLD", _analysis(50.0, "HOLD"), db_path=db)
    satu = history.summarize_trend("GOLD", db_path=db)
    assert satu["trend"] is None
    assert "belum bisa disimpulkan" in satu["note"]


def test_assets_are_isolated(db):
    history.record_snapshot("GOLD", _analysis(30.0, "SELL"), db_path=db)
    history.record_snapshot("BBCA.JK", _analysis(70.0, "BUY"), db_path=db)

    assert len(history.get_history("GOLD", db_path=db)) == 1
    assert history.get_latest("BBCA.JK", db_path=db)["total_score"] == 70.0
    assert {a["asset"] for a in history.list_assets(db_path=db)} == {"GOLD", "BBCA.JK"}


def test_purge_removes_only_old_rows(db):
    now = datetime.now(timezone.utc)
    history.record_snapshot("GOLD", _analysis(10.0, "SELL", when=now - timedelta(days=400)), db_path=db)
    history.record_snapshot("GOLD", _analysis(20.0, "SELL", when=now), db_path=db)

    assert history.purge_older_than(days=365, db_path=db) == 1
    assert len(history.get_history("GOLD", days=999, db_path=db)) == 1


# ---------------------------------------------------------------------------
# Peringatan
# ---------------------------------------------------------------------------

def test_first_snapshot_raises_no_alert():
    """Merekam pertama kali bukan perubahan — tidak layak memicu pemberitahuan."""
    assert alerts.evaluate(None, {"asset": "GOLD", "signal": "BUY", "total_score": 70}) == []


def test_signal_change_is_high_severity():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0}
    curr = {"asset": "GOLD", "signal": "BUY", "total_score": 58.0}

    result = alerts.evaluate(prev, curr)
    kinds = [a["kind"] for a in result]
    assert "signal_change" in kinds

    change = next(a for a in result if a["kind"] == "signal_change")
    assert change["severity"] == "tinggi"
    assert change["direction"] == "membaik"
    assert change["previous_value"] == "HOLD" and change["current_value"] == "BUY"


def test_threshold_cross_detected_both_ways():
    naik = alerts.evaluate(
        {"asset": "X", "signal": "HOLD", "total_score": 50.0},
        {"asset": "X", "signal": "HOLD", "total_score": 56.0},
    )
    assert any(a["kind"] == "threshold_cross" for a in naik)

    turun = alerts.evaluate(
        {"asset": "X", "signal": "HOLD", "total_score": 45.0},
        {"asset": "X", "signal": "HOLD", "total_score": 38.0},
    )
    assert any(a["kind"] == "threshold_cross" for a in turun)


def test_no_alert_when_nothing_meaningful_changed():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0, "regime_status": "normal"}
    curr = {"asset": "GOLD", "signal": "HOLD", "total_score": 46.5, "regime_status": "normal"}
    assert alerts.evaluate(prev, curr) == []


def test_sharp_move_flagged_even_without_signal_change():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 41.0}
    curr = {"asset": "GOLD", "signal": "HOLD", "total_score": 53.0}
    result = alerts.evaluate(prev, curr)
    assert any(a["kind"] == "sharp_move" for a in result)


def test_regime_break_is_high_severity():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0, "regime_status": "normal"}
    curr = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0, "regime_status": "putus"}

    result = alerts.evaluate(prev, curr)
    regime_alert = next(a for a in result if a["kind"] == "regime_change")
    assert regime_alert["severity"] == "tinggi"
    assert "TIDAK mengikuti suku bunga riil" in regime_alert["detail"]


def test_falling_data_quality_is_reported():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0,
            "payload": json.dumps({"macro_completeness": 100.0})}
    curr = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0,
            "payload": json.dumps({"macro_completeness": 75.0})}

    result = alerts.evaluate(prev, curr)
    assert any(a["kind"] == "data_quality" for a in result)


def test_alerts_sorted_by_severity():
    prev = {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0, "regime_status": "normal"}
    curr = {"asset": "GOLD", "signal": "SELL", "total_score": 30.0, "regime_status": "putus"}

    result = alerts.evaluate(prev, curr)
    severities = [a["severity"] for a in result]
    assert severities == sorted(severities, key=lambda s: alerts.SEVERITY_ORDER[s])
    assert severities[0] == "tinggi"


def test_message_formatting_is_readable():
    result = alerts.evaluate(
        {"asset": "GOLD", "signal": "HOLD", "total_score": 45.0},
        {"asset": "GOLD", "signal": "BUY", "total_score": 60.0},
    )
    text = alerts.format_for_messaging(result)
    assert "GOLD" in text
    assert "bukan nasihat keuangan" in text
    assert alerts.format_for_messaging([]) == ""


def test_telegram_reports_skip_instead_of_pretending(monkeypatch):
    """Tanpa kredensial, harus mengaku dilewati — bukan berpura-pura terkirim."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    result = alerts.send_telegram("halo")
    assert result["sent"] is False
    assert "belum diisi" in result["reason"]


def test_end_to_end_history_to_alert(db):
    """Alur nyata: rekam, rekam lagi, lalu perubahan terdeteksi dari basis data."""
    now = datetime.now(timezone.utc)
    history.record_snapshot("GOLD", _analysis(45.0, "HOLD", when=now - timedelta(hours=2)), db_path=db)
    history.record_snapshot("GOLD", _analysis(62.0, "BUY", regime="putus", when=now), db_path=db)

    curr = history.get_latest("GOLD", db_path=db)
    prev = history.get_previous("GOLD", db_path=db)
    result = alerts.evaluate(prev, curr)

    kinds = {a["kind"] for a in result}
    assert "signal_change" in kinds
    assert "regime_change" in kinds
    assert all(a["asset"] == "GOLD" for a in result)
