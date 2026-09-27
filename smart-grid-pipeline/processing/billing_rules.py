"""Pure billing arithmetic -- the single source of truth for the numbers.

batch_layer_spark.compute_billing_report() implements the identical formula
as Spark column expressions (it imports SUBSIDY_DISCOUNT_PCT from here), and
the API's provisional-bill projection calls compute_bill() directly. The
end-to-end smoke test (scripts/smoke_test.py) re-checks every bill the batch
layer produced against compute_bill(), so the two cannot silently drift.

    net_kwh    = max(consumption - solar, 0)          # net metering, no export credit
    bill       = net_kwh * tariff_rate * (1 - discount/100)
    discount   = SUBSIDY_DISCOUNT_PCT if subsidy_flag else 0
"""

SUBSIDY_DISCOUNT_PCT = 15.0


def net_consumption_kwh(total_consumption_kwh: float, total_solar_kwh: float) -> float:
    return max(total_consumption_kwh - total_solar_kwh, 0.0)


def solar_export_kwh(total_consumption_kwh: float, total_solar_kwh: float) -> float:
    return max(total_solar_kwh - total_consumption_kwh, 0.0)


def solar_contribution_pct(total_consumption_kwh: float, total_solar_kwh: float) -> float:
    """Share of the household's own consumption covered by its own solar."""
    if total_consumption_kwh <= 0:
        return 0.0
    return round(100.0 * min(total_solar_kwh, total_consumption_kwh) / total_consumption_kwh, 2)


def compute_bill(net_kwh: float, tariff_rate: float, subsidy_flag: bool) -> float:
    discount_pct = SUBSIDY_DISCOUNT_PCT if subsidy_flag else 0.0
    return round(net_kwh * tariff_rate * (1 - discount_pct / 100.0), 2)
