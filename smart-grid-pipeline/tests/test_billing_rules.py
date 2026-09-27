from processing.billing_rules import (
    compute_bill, net_consumption_kwh, solar_contribution_pct, solar_export_kwh,
)


def test_net_consumption_never_negative():
    assert net_consumption_kwh(5.0, 8.0) == 0.0  # exported more solar than consumed
    assert net_consumption_kwh(10.0, 3.0) == 7.0


def test_solar_export_is_the_surplus_only():
    assert solar_export_kwh(5.0, 8.0) == 3.0
    assert solar_export_kwh(10.0, 3.0) == 0.0


def test_solar_contribution_pct():
    assert solar_contribution_pct(10.0, 2.5) == 25.0
    assert solar_contribution_pct(10.0, 40.0) == 100.0  # capped at 100% of demand
    assert solar_contribution_pct(0.0, 5.0) == 0.0


def test_bill_without_subsidy():
    assert compute_bill(net_kwh=10.0, tariff_rate=25.0, subsidy_flag=False) == 250.0


def test_bill_with_subsidy_applies_15pct_discount():
    assert compute_bill(net_kwh=10.0, tariff_rate=25.0, subsidy_flag=True) == 212.5  # 250 * 0.85


def test_zero_consumption_bills_zero():
    assert compute_bill(net_kwh=0.0, tariff_rate=30.0, subsidy_flag=False) == 0.0


def test_bill_is_rounded_to_cents():
    assert compute_bill(net_kwh=1.2345, tariff_rate=18.37, subsidy_flag=False) == 22.68
