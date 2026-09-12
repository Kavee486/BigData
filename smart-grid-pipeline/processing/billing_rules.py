"""Pure billing arithmetic, factored out of batch_layer_spark.py so it can be
unit-tested without a SparkSession. The Spark job's withColumn expressions in
compute_billing_report() implement the identical formula (documented there);
this module is the single source of truth for the numbers.
"""

SUBSIDY_DISCOUNT_PCT = 15.0


def net_consumption_kwh(total_consumption_kwh: float, total_solar_kwh: float) -> float:
    return max(total_consumption_kwh - total_solar_kwh, 0.0)


def compute_bill(net_kwh: float, tariff_rate: float, subsidy_flag: bool) -> float:
    discount_pct = SUBSIDY_DISCOUNT_PCT if subsidy_flag else 0.0
    return round(net_kwh * tariff_rate * (1 - discount_pct / 100.0), 2)
