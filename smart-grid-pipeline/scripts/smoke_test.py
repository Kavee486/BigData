"""End-to-end smoke test against the RUNNING stack (docker compose up).

    python scripts/smoke_test.py                 # checks what exists right now
    python scripts/smoke_test.py --wait-billing  # also waits (up to ~2 sim days) for the first bill

Checks, layer by layer:
  ingestion   producer metrics show events delivered to Kafka
  speed       /api/grid/live has a recent window for every zone
  quality     the speed layer is quarantining the injected dirty events
  batch       every bill in /api/billing/daily equals billing_rules.compute_bill(...)
              and the reconciliation row for that day exists
  merge       /api/billing/projection returns provisional bills
  observ.     /health, /metrics and Prometheus (rules loaded, targets up)
Exit code 0 = all checks passed. Standard library only (no extra installs).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from processing.billing_rules import compute_bill  # noqa: E402

API = os.getenv("API_URL", "http://localhost:8000")
PRODUCER = os.getenv("PRODUCER_METRICS_URL", "http://localhost:8001")
PROM = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

failures = []


def get(url, as_json=True):
    with urllib.request.urlopen(url, timeout=10) as r:
        body = r.read().decode()
    return json.loads(body) if as_json else body


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-billing", action="store_true")
    args = parser.parse_args()

    delivered = [l for l in get(PRODUCER, False).splitlines() if l.startswith("meter_events_delivered_total")]
    count = float(delivered[0].split()[-1]) if delivered else 0
    check("ingestion: producer delivered events to Kafka", count > 0, f"{count:.0f} delivered")

    live = get(f"{API}/api/grid/live")
    zones = {z["grid_zone"] for z in live["zones"]}
    check("speed layer: live window for all 4 zones", zones == {"North", "South", "East", "West"}, str(sorted(zones)))

    status = get(f"{API}/api/pipeline/status")
    q = status["stream_quality_last_5m"]
    check("speed layer: events processed in last 5 min", q["total_events"] > 0, f"{q['total_events']} events")
    check("processing: dirty events are quarantined", q["invalid_events"] > 0, json.dumps(q["invalid_by_reason"]))

    health = get(f"{API}/health")
    check("observability: /health reports every component OK", health["status"] == "OK",
          ", ".join(f"{k}={v['status']}" for k, v in health["components"].items()))

    metrics = get(f"{API}/metrics", False)
    check("observability: /metrics exports pipeline gauges", "pipeline_component_staleness_seconds" in metrics)

    rules = get(f"{PROM}/api/v1/rules")
    n_rules = sum(len(g["rules"]) for g in rules["data"]["groups"])
    check("observability: Prometheus alert rules loaded", n_rules >= 5, f"{n_rules} rules")
    targets = get(f"{PROM}/api/v1/targets")["data"]["activeTargets"]
    check("observability: Prometheus scrape targets up", all(t["health"] == "up" for t in targets),
          ", ".join(f"{t['labels']['job']}={t['health']}" for t in targets))

    deadline = time.time() + (2 * int(os.getenv("SIMULATED_DAY_SECONDS", "300")) + 180 if args.wait_billing else 0)
    billing = get(f"{API}/api/billing/daily")
    while not billing["rows"] and time.time() < deadline:
        print("  ... waiting for the first batch-layer billing run")
        time.sleep(20)
        billing = get(f"{API}/api/billing/daily")
    if billing["rows"]:
        wrong = [r["household_id"] for r in billing["rows"]
                 if abs(compute_bill(r["net_consumption_kwh"], r["tariff_rate"], r["subsidy_flag"]) - r["bill_amount"]) > 0.011]
        check("batch layer: every bill matches billing_rules.compute_bill", not wrong,
              f"{billing['count']} bills for sim_day {billing['sim_day']}, mismatches={wrong}")
        recon = get(f"{API}/api/reconciliation?limit=1")["rows"]
        check("batch layer: speed/batch reconciliation recorded", bool(recon),
              f"drift={recon[0]['drift_pct']:.2f}%" if recon and recon[0]["drift_pct"] is not None else "")
    else:
        check("batch layer: billing report produced", False, "no billing rows yet (use --wait-billing)")

    proj = get(f"{API}/api/billing/projection")
    check("lambda merge: provisional bills for the running day", proj["count"] > 0,
          f"{proj['count']} households, total {proj['total_provisional']}")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
