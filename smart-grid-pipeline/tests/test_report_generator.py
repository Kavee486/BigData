from serving.report_generator import render_html

BILL = {"household_id": "H-001", "grid_zone": "North", "billing_tier": "residential_low",
        "total_consumption_kwh": 40.0, "total_solar_kwh": 10.0, "net_consumption_kwh": 30.0,
        "solar_export_kwh": 0.0, "solar_contribution_pct": 25.0, "tariff_rate": 18.0,
        "tariff_source": "current_day", "subsidy_flag": False, "subsidy_discount_pct": 0.0, "bill_amount": 540.0}
ZONE = {"grid_zone": "North", "households": 1, "consumption": 40.0, "solar": 10.0, "solar_pct": 25.0,
        "billed": 540.0}


def test_report_contains_kpis_and_escapes_values():
    page = render_html(3, [BILL], [ZONE], {"run_id": "<abc>", "raw_events": 100, "drift_pct": 1.5})
    assert "Simulated day <b>3</b>" in page
    assert "540.00" in page
    assert "&lt;abc&gt;" in page and "<abc>" not in page
