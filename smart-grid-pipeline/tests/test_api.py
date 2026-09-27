"""Serving-layer tests with the Postgres access function stubbed out."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from processing.billing_rules import compute_bill, net_consumption_kwh
from serving.api import main


def fake_query_factory(tables):
    def fake_query(sql, params=()):
        for marker, rows in tables.items():
            if marker in sql:
                return [dict(r) for r in rows]
        return []
    return fake_query


@pytest.fixture
def client():
    return TestClient(main.app)


def test_projection_merges_speed_consumption_with_batch_tariff(client, monkeypatch):
    live = {"household_id": "H-001", "grid_zone": "South", "consumption_kwh": 12.0, "solar_kwh": 2.0,
            "reading_count": 100, "tariff_rate": 25.0, "billing_tier": "residential_standard",
            "subsidy_flag": True, "tariff_sim_day": 2, "last_final_bill": 180.0, "last_final_sim_day": 2}
    monkeypatch.setattr(main, "query", fake_query_factory({"FROM live_household_consumption l": [live]}))
    body = client.get("/api/billing/projection").json()
    row = body["rows"][0]
    assert row["provisional_bill_so_far"] == compute_bill(net_consumption_kwh(12.0, 2.0), 25.0, True)
    assert row["status"] == "provisional"
    assert body["total_provisional"] == row["provisional_bill_so_far"]


def test_projection_without_any_tariff_yet(client, monkeypatch):
    live = {"household_id": "H-002", "grid_zone": "North", "consumption_kwh": 3.0, "solar_kwh": 1.0,
            "reading_count": 10, "tariff_rate": None, "billing_tier": None, "subsidy_flag": None,
            "tariff_sim_day": None, "last_final_bill": None, "last_final_sim_day": None}
    monkeypatch.setattr(main, "query", fake_query_factory({"FROM live_household_consumption l": [live]}))
    row = client.get("/api/billing/projection").json()["rows"][0]
    assert row["provisional_bill_so_far"] is None
    assert row["status"] == "awaiting_first_tariff"


def test_grid_live_totals_and_low_renewable_flag(client, monkeypatch):
    now = datetime.now(timezone.utc)
    zones = [
        {"grid_zone": "North", "total_consumption_kwh": 10.0, "total_solar_kwh": 6.0, "renewable_pct": 60.0,
         "window_start": now, "window_end": now},
        {"grid_zone": "South", "total_consumption_kwh": 10.0, "total_solar_kwh": 0.5, "renewable_pct": 5.0,
         "window_start": now, "window_end": now},
    ]
    monkeypatch.setattr(main, "query", fake_query_factory({"FROM live_zone_metrics": zones}))
    body = client.get("/api/grid/live").json()
    assert body["grid_total_consumption_kwh"] == 20.0
    assert body["grid_renewable_pct"] == 32.5
    assert [z["below_threshold"] for z in body["zones"]] == [False, True]
    assert all(z["low_renewable"] == (z["below_threshold"] and body["clock"]["daylight"]) for z in body["zones"])


def test_health_flags_stale_component(client, monkeypatch):
    rows = [
        {"component": "speed_layer", "status": "OK", "detail": "", "last_heartbeat": None, "age_seconds": 5},
        {"component": "meter_producer", "status": "OK", "detail": "", "last_heartbeat": None, "age_seconds": 900},
    ]
    monkeypatch.setattr(main, "query", fake_query_factory({"FROM pipeline_health": rows}))
    body = client.get("/health").json()
    assert body["status"] == "DEGRADED"
    assert body["components"]["meter_producer"]["status"] == "STALE"
    assert body["components"]["speed_layer"]["status"] == "OK"


def test_database_outage_returns_503_not_crash(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise ConnectionError("postgres down")
    monkeypatch.setattr(main, "query", boom)
    assert client.get("/api/grid/live").status_code == 503


def test_metrics_endpoint_serves_prometheus_text(client, monkeypatch):
    monkeypatch.setattr(main, "query", fake_query_factory({}))
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "api_requests_total" in resp.text
