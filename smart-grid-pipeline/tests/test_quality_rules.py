from processing import quality_rules as Q

GOOD = {
    "event_id": "e1", "meter_id": "M-001", "household_id": "H-001", "grid_zone": "North",
    "power_consumption_kwh": 0.5, "solar_generation_kwh": 0.1,
    "timestamp": "2026-08-11T10:15:00.123456+00:00",
}


def test_clean_event_passes():
    assert Q.validate_event(GOOD) is None


def test_missing_household_is_rejected():
    assert Q.validate_event(dict(GOOD, household_id=None)) == Q.MISSING_FIELD
    assert Q.validate_event(dict(GOOD, household_id="")) == Q.MISSING_FIELD


def test_missing_measurement_is_rejected():
    assert Q.validate_event(dict(GOOD, solar_generation_kwh=None)) == Q.MISSING_FIELD


def test_unparsable_timestamp_is_rejected():
    assert Q.validate_event(dict(GOOD, timestamp="not-a-timestamp")) == Q.BAD_TIMESTAMP


def test_unknown_zone_is_rejected():
    assert Q.validate_event(dict(GOOD, grid_zone="Atlantis")) == Q.UNKNOWN_ZONE


def test_negative_reading_is_rejected():
    assert Q.validate_event(dict(GOOD, power_consumption_kwh=-0.2)) == Q.NEGATIVE_VALUE


def test_physically_impossible_reading_is_rejected():
    assert Q.validate_event(dict(GOOD, power_consumption_kwh=999.0)) == Q.OUT_OF_RANGE


def test_legit_spike_below_cap_is_kept():
    assert Q.validate_event(dict(GOOD, power_consumption_kwh=6.0)) is None
