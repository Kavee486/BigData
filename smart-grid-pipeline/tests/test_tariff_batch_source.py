import csv
import os

from sources import tariff_batch_source as src


def test_tariff_row_fields_and_ranges():
    for h in range(30):
        row = src.generate_tariff_row(h, sim_day=0)
        assert row["household_id"] == f"H-{h:03d}"
        assert row["billing_tier"] in src.TIERS
        assert row["tariff_rate"] > 0
        assert isinstance(row["subsidy_flag"], bool)
        assert row["sim_day"] == 0


def test_household_profile_is_stable_across_days():
    assert src.generate_tariff_row(5, 1)["billing_tier"] == src.generate_tariff_row(5, 9)["billing_tier"]
    assert src.generate_tariff_row(5, 1)["subsidy_flag"] == src.generate_tariff_row(5, 9)["subsidy_flag"]


def test_daily_file_is_deterministic_for_replay():
    assert src.generate_daily_rows(3) == src.generate_daily_rows(3)


def test_some_days_contain_defects_for_the_batch_layer_to_handle():
    days = range(40)
    defect_days = [d for d in days
                   if any(str(r["tariff_rate"]) in ("", "-1", "0") for r in src.generate_daily_rows(d))]
    dup_days = [d for d in days if len(src.generate_daily_rows(d)) > src.NUM_HOUSEHOLDS]
    assert 0 < len(defect_days) < 40
    assert dup_days


def test_write_daily_file_is_atomic_with_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(src, "BATCH_DROP_DIR", str(tmp_path))
    path = src.write_daily_file(2)
    assert os.path.basename(path) == "tariff_simday2.csv"
    assert not os.path.exists(path + ".tmp")
    assert (tmp_path / "_SUCCESS_simday2").read_text() == "tariff_simday2.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert set(rows[0]) == set(src.FIELDNAMES)
    assert len(rows) >= src.NUM_HOUSEHOLDS
