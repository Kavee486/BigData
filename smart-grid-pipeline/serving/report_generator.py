"""Scheduled daily report files (the "consolidated daily report" deliverable).

Called by the Airflow DAG after the batch layer has billed a simulated day
(task publish_report) -- or manually:  python serving/report_generator.py --sim-day 3

Writes to REPORTS_DIR (bind-mounted to ./reports on the host):
  daily_billing_report_simday<N>.csv   per-household bill + solar contribution
  daily_report_simday<N>.html          human-readable consolidated report:
                                       zone summary, reconciliation / data
                                       quality, top bills, full bill table
"""
import argparse
import csv
import html
import os
import sys
from datetime import datetime, timezone

sys.path.append("/app")
import psycopg2
import psycopg2.extras

from config import REPORTS_DIR, pg_dsn

CSV_COLUMNS = ["household_id", "grid_zone", "billing_tier", "total_consumption_kwh", "total_solar_kwh",
               "net_consumption_kwh", "solar_export_kwh", "solar_contribution_pct", "tariff_rate",
               "tariff_source", "subsidy_flag", "subsidy_discount_pct", "bill_amount"]

STYLE = """body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1f2937}h1{color:#1f3b57}
table{border-collapse:collapse;margin:8px 0 24px;font-size:13px}
th,td{border:1px solid #d1d5db;padding:4px 10px;text-align:right}
th{background:#1f3b57;color:#fff}td:first-child,th:first-child{text-align:left}
.kpi{display:inline-block;margin-right:28px}.kpi b{display:block;font-size:22px}"""


def _fetch(sim_day: int):
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM daily_billing_report WHERE sim_day = %s ORDER BY household_id;", (sim_day,))
            bills = cur.fetchall()
            cur.execute(
                """
                SELECT grid_zone, COUNT(*) AS households, SUM(total_consumption_kwh) AS consumption,
                       SUM(total_solar_kwh) AS solar, AVG(solar_contribution_pct) AS solar_pct,
                       SUM(bill_amount) AS billed
                FROM daily_billing_report WHERE sim_day = %s GROUP BY grid_zone ORDER BY grid_zone;
                """,
                (sim_day,),
            )
            zones = cur.fetchall()
            cur.execute("SELECT * FROM batch_reconciliation WHERE sim_day = %s;", (sim_day,))
            rec = cur.fetchone()
    finally:
        conn.close()
    return bills, zones, rec or {}


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(sim_day, bills, zones, rec) -> str:
    total = sum(b["bill_amount"] for b in bills)
    top = sorted(bills, key=lambda b: b["bill_amount"], reverse=True)[:5]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    zone_rows = [(z["grid_zone"], z["households"], f"{z['consumption']:.2f}", f"{z['solar']:.2f}",
                  f"{z['solar_pct']:.1f}", f"{z['billed']:,.2f}") for z in zones]
    rec_rows = [(rec.get("raw_events"), rec.get("duplicates_removed"),
                 f"{rec.get('speed_consumption_kwh') or 0:.2f}", f"{rec.get('batch_consumption_kwh') or 0:.2f}",
                 f"{rec.get('drift_pct') or 0:+.2f}", rec.get("tariff_rows"), rec.get("invalid_tariff_rows"),
                 rec.get("fallback_tariffs"), rec.get("households_unbilled"))]
    top_rows = [(b["household_id"], b["grid_zone"], f"{b['net_consumption_kwh']:.2f}", f"{b['tariff_rate']:.2f}",
                 f"{b['bill_amount']:,.2f}") for b in top]
    all_rows = [(b["household_id"], b["grid_zone"], b["billing_tier"], f"{b['total_consumption_kwh']:.2f}",
                 f"{b['total_solar_kwh']:.2f}", f"{b['net_consumption_kwh']:.2f}",
                 f"{b['solar_contribution_pct']:.1f}", f"{b['tariff_rate']:.2f}", b["tariff_source"],
                 "yes" if b["subsidy_flag"] else "no", f"{b['bill_amount']:,.2f}") for b in bills]
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>Daily Billing Report - sim day {sim_day}</title><style>{STYLE}</style></head><body>",
        "<h1>Smart Grid - Consolidated Daily Billing &amp; Solar Report</h1>",
        f"<p>Simulated day <b>{sim_day}</b> &middot; generated {generated} &middot; "
        f"batch run <code>{html.escape(str(rec.get('run_id', '')))}</code></p>",
        f"<div class='kpi'>Households billed<b>{len(bills)}</b></div>",
        f"<div class='kpi'>Total billed (LKR)<b>{total:,.2f}</b></div>",
        f"<div class='kpi'>Consumption (kWh)<b>{sum(b['total_consumption_kwh'] for b in bills):,.2f}</b></div>",
        f"<div class='kpi'>Solar generated (kWh)<b>{sum(b['total_solar_kwh'] for b in bills):,.2f}</b></div>",
        "<h2>By zone</h2>",
        _table(["Zone", "Households", "Consumption kWh", "Solar kWh", "Avg solar contribution %", "Billed LKR"],
               zone_rows),
        "<h2>Data quality &amp; speed/batch reconciliation</h2>",
        _table(["Raw events", "Duplicates removed", "Speed-layer kWh", "Batch kWh", "Drift %", "Tariff rows",
                "Invalid tariff rows", "Fallback tariffs", "Unbilled households"], rec_rows),
        "<h2>Top 5 bills</h2>",
        _table(["Household", "Zone", "Net kWh", "Tariff", "Bill LKR"], top_rows),
        "<h2>All households</h2>",
        _table(["Household", "Zone", "Tier", "Consumption", "Solar", "Net", "Solar %", "Tariff", "Tariff source",
                "Subsidy", "Bill LKR"], all_rows),
        "</body></html>",
    ]
    return "\n".join(parts)


def write_report(sim_day: int, out_dir: str = REPORTS_DIR) -> dict:
    bills, zones, rec = _fetch(sim_day)
    if not bills:
        raise RuntimeError(f"no billing rows for sim_day={sim_day}")
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, f"daily_billing_report_simday{sim_day}.csv")
    with open(csv_path + ".tmp", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(bills)
    os.replace(csv_path + ".tmp", csv_path)

    html_path = os.path.join(out_dir, f"daily_report_simday{sim_day}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(sim_day, bills, zones, rec))
    return {"csv": csv_path, "html": html_path, "households": len(bills),
            "total_billed": round(sum(b["bill_amount"] for b in bills), 2)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-day", type=int, required=True)
    print(write_report(parser.parse_args().sim_day))
