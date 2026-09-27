import random
from datetime import datetime

from config import GRID_ZONES
from processing.quality_rules import validate_event
from sources.smart_meter_producer import DIRTY_KINDS, daily_weather, make_dirty, simulate_reading

FIELDS = ["event_id", "meter_id", "household_id", "power_consumption_kwh", "solar_generation_kwh",
          "grid_zone", "timestamp"]


def test_reading_has_required_fields_and_is_valid():
    r = simulate_reading(0, 0.5)
    for field in FIELDS:
        assert field in r
    assert validate_event(r) is None
    datetime.fromisoformat(r["timestamp"])


def test_event_ids_are_unique():
    assert len({simulate_reading(1, 0.5)["event_id"] for _ in range(200)}) == 200


def test_reading_values_non_negative_and_valid():
    for h in range(12):
        for tod in (0.0, 0.3, 0.5, 0.75, 0.99):
            r = simulate_reading(h, tod, sim_day=3)
            assert r["power_consumption_kwh"] >= 0
            assert r["solar_generation_kwh"] >= 0
            assert validate_event(r) is None


def test_zone_assignment_is_deterministic_and_valid():
    assert simulate_reading(2, 0.5)["grid_zone"] == simulate_reading(2, 0.9)["grid_zone"]
    assert simulate_reading(2, 0.5)["grid_zone"] in GRID_ZONES


def test_solar_is_near_zero_at_night_and_peaks_at_noon():
    night = sum(simulate_reading(h, 0.02)["solar_generation_kwh"] for h in range(20)) / 20
    noon = sum(simulate_reading(h, 0.5)["solar_generation_kwh"] for h in range(20)) / 20
    assert night < 0.01
    assert noon > 0.1


def test_weather_is_deterministic_per_day():
    assert daily_weather(7) == daily_weather(7)
    assert daily_weather(7)["spell_zone"] in GRID_ZONES


def test_overcast_spell_cuts_solar_in_that_zone():
    w = daily_weather(4)
    mid_spell = (w["spell_start"] + w["spell_end"]) / 2
    zone_idx = GRID_ZONES.index(w["spell_zone"])  # household idx -> zone is idx % len(zones)
    overcast = simulate_reading(zone_idx, mid_spell, sim_day=4, rng=random.Random(1))
    other_day = next(d for d in range(100) if daily_weather(d)["spell_zone"] != w["spell_zone"])
    sunny = simulate_reading(zone_idx, mid_spell, sim_day=other_day, rng=random.Random(1))
    assert overcast["solar_generation_kwh"] < 0.3 * sunny["solar_generation_kwh"]


def test_every_dirty_kind_except_duplicate_fails_validation():
    clean = simulate_reading(3, 0.5)
    for kind in DIRTY_KINDS:
        bad = make_dirty(clean, kind)
        if kind == "duplicate":
            assert bad == clean  # a duplicate is valid; it is removed by dedup, not validation
        else:
            assert validate_event(bad) is not None, kind
