import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sources.smart_meter_producer import simulate_reading
from config import GRID_ZONES


def test_reading_has_required_fields():
    r = simulate_reading(0, 0.5)
    for field in ["meter_id", "household_id", "power_consumption_kwh", "solar_generation_kwh", "grid_zone", "timestamp"]:
        assert field in r


def test_reading_values_non_negative():
    for h in range(10):
        for tod in (0.0, 0.3, 0.5, 0.75, 0.99):
            r = simulate_reading(h, tod)
            assert r["power_consumption_kwh"] >= 0
            assert r["solar_generation_kwh"] >= 0


def test_zone_assignment_is_deterministic_and_valid():
    r1 = simulate_reading(2, 0.5)
    r2 = simulate_reading(2, 0.9)
    assert r1["grid_zone"] == r2["grid_zone"]
    assert r1["grid_zone"] in GRID_ZONES


def test_solar_is_near_zero_at_night():
    night_readings = [simulate_reading(h, 0.02) for h in range(20)]
    avg_solar = sum(r["solar_generation_kwh"] for r in night_readings) / len(night_readings)
    assert avg_solar < 0.15
