import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sources.tariff_batch_source import generate_tariff_row, TIERS


def test_tariff_row_fields_and_ranges():
    for h in range(30):
        row = generate_tariff_row(h, sim_day=0)
        assert row["household_id"] == f"H-{h:03d}"
        assert row["billing_tier"] in TIERS
        assert row["tariff_rate"] > 0
        assert isinstance(row["subsidy_flag"], bool)
        assert row["day"] == 0
