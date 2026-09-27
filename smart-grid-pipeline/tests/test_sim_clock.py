from common import sim_clock
from config import SIMULATED_DAY_SECONDS

EPOCH = 1_000_000.0


def test_day_boundaries():
    assert sim_clock.sim_day_at(EPOCH, EPOCH) == 0
    assert sim_clock.sim_day_at(EPOCH + SIMULATED_DAY_SECONDS - 0.001, EPOCH) == 0
    assert sim_clock.sim_day_at(EPOCH + SIMULATED_DAY_SECONDS, EPOCH) == 1


def test_day_fraction_noon():
    assert sim_clock.day_fraction_at(EPOCH + 3.5 * SIMULATED_DAY_SECONDS, EPOCH) == 0.5


def test_day_start_end_roundtrip():
    for d in range(5):
        assert sim_clock.sim_day_at(sim_clock.day_start(d, EPOCH), EPOCH) == d
        assert sim_clock.day_end(d, EPOCH) == sim_clock.day_start(d + 1, EPOCH)


def test_daylight_window():
    assert sim_clock.is_daylight(0.5, 0.4, 0.6)
    assert not sim_clock.is_daylight(0.1, 0.4, 0.6)


def test_epoch_can_be_pinned_by_env():
    assert sim_clock.get_sim_epoch() == 1767225600.0  # from conftest, no Postgres needed
