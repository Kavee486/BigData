from config import LOW_RENEWABLE_PCT_THRESHOLD, stale_after_seconds
from observability import alerts


def test_low_renewable_only_judged_in_daylight():
    assert alerts.low_renewable_breached(LOW_RENEWABLE_PCT_THRESHOLD - 1, 0.5) is True
    assert alerts.low_renewable_breached(LOW_RENEWABLE_PCT_THRESHOLD + 1, 0.5) is False
    assert alerts.low_renewable_breached(0.0, 0.05) is None  # night: 0% solar is expected


def test_staleness_budget_is_per_component():
    # The batch layer legitimately stays silent for a whole simulated day.
    assert alerts.is_stale("speed_layer", 10 * 60)
    assert not alerts.is_stale("batch_layer", 6 * 60)
    assert stale_after_seconds("batch_layer") > stale_after_seconds("speed_layer")


def test_invalid_rate_pct():
    assert alerts.invalid_rate_pct(5, 100) == 5.0
    assert alerts.invalid_rate_pct(0, 0) == 0.0


def test_drift_breached_is_symmetric():
    assert alerts.drift_breached(15.0)
    assert alerts.drift_breached(-15.0)
    assert not alerts.drift_breached(2.0)
    assert not alerts.drift_breached(None)
