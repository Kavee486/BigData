import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing.billing_rules import net_consumption_kwh, compute_bill


def test_net_consumption_never_negative():
    assert net_consumption_kwh(5.0, 8.0) == 0.0  # exported more solar than consumed
    assert net_consumption_kwh(10.0, 3.0) == 7.0


def test_bill_without_subsidy():
    assert compute_bill(net_kwh=10.0, tariff_rate=25.0, subsidy_flag=False) == 250.0


def test_bill_with_subsidy_applies_15pct_discount():
    bill = compute_bill(net_kwh=10.0, tariff_rate=25.0, subsidy_flag=True)
    assert bill == 212.5  # 250 * 0.85


def test_zero_consumption_bills_zero():
    assert compute_bill(net_kwh=0.0, tariff_rate=30.0, subsidy_flag=False) == 0.0
