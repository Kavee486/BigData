"""Capture report evidence from the RUNNING stack.

    pip install playwright            # uses the locally installed Edge/Chrome
    python report/capture_results.py [--only dashboard,api,...]

Writes report/screenshots/*.png and report/results/*.json, which
report/gen_report.js embeds, so every figure and number in the report comes
from an actual run.
"""
import argparse
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")
RESULTS = os.path.join(HERE, "results")
API = "http://localhost:8000"

API_DUMPS = {
    "grid_live": "/api/grid/live",
    "billing_daily": "/api/billing/daily",
    "billing_summary": "/api/billing/summary",
    "billing_projection": "/api/billing/projection",
    "reconciliation": "/api/reconciliation?limit=20",
    "alerts_open": "/api/alerts",
    "alerts_resolved": "/api/alerts?resolved=true&limit=100",
    "pipeline_status": "/api/pipeline/status",
    "health": "/health",
}


def dump_api():
    os.makedirs(RESULTS, exist_ok=True)
    for name, path in API_DUMPS.items():
        with urllib.request.urlopen(API + path, timeout=15) as r:
            data = json.loads(r.read())
        with open(os.path.join(RESULTS, f"{name}.json"), "w") as f:
            json.dump(data, f, indent=2, default=str)
    with urllib.request.urlopen(API + "/metrics", timeout=15) as r:
        open(os.path.join(RESULTS, "metrics.txt"), "w").write(r.read().decode())
    print("api dumps written")


def shot(page, url, name, wait_ms=4000, full=True, selector=None, width=1400, height=900):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)
    target = page.locator(selector) if selector else page
    path = os.path.join(SHOTS, f"{name}.png")
    if selector:
        target.screenshot(path=path)
    else:
        page.screenshot(path=path, full_page=full)
    print("saved", path)


def json_page(page, url, name, height=700):
    """Render an API response as pretty JSON in a page and screenshot it."""
    with urllib.request.urlopen(url, timeout=15) as r:
        text = json.dumps(json.loads(r.read()), indent=2)
    lines = text.splitlines()
    if len(lines) > 60:
        text = "\n".join(lines[:60]) + "\n  ... (truncated)"
    html = ("<html><body style='margin:0;background:#0f172a;color:#e2e8f0;font:13px Consolas,monospace'>"
            f"<div style='padding:8px 14px;background:#1e293b;color:#93c5fd'>GET {url}</div>"
            f"<pre style='margin:0;padding:12px 14px'>{text.replace('&', '&amp;').replace('<', '&lt;')}</pre></body></html>")
    page.set_viewport_size({"width": 900, "height": height})
    page.set_content(html)
    page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)
    print("saved", name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    only = set(filter(None, parser.parse_args().only.split(",")))
    want = lambda k: not only or k in only  # noqa: E731
    os.makedirs(SHOTS, exist_ok=True)

    if want("api"):
        dump_api()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(device_scale_factor=1.5)
        if want("dashboard"):
            shot(page, API + "/", "dashboard_full", wait_ms=6000)
            shot(page, API + "/", "dashboard_top", wait_ms=6000, full=False, height=1000)
        if want("api"):
            json_page(page, API + "/api/grid/live", "api_grid_live")
            json_page(page, API + "/api/billing/projection?household_id=H-001", "api_projection")
            json_page(page, API + "/health", "api_health")
        if want("docs"):
            shot(page, API + "/docs", "api_docs", wait_ms=3000, full=False, height=1100)
        if want("report_file"):
            files = sorted(f for f in os.listdir(os.path.join(HERE, "..", "reports")) if f.endswith(".html"))
            if files:
                shot(page, "file:///" + os.path.abspath(os.path.join(HERE, "..", "reports", files[-1])).replace("\\", "/"),
                     "report_file", wait_ms=500, height=1000)
        if want("prometheus"):
            shot(page, "http://localhost:9090/alerts?search=", "prometheus_alerts", wait_ms=3000, full=False, height=1000)
            shot(page, "http://localhost:9090/targets", "prometheus_targets", wait_ms=3000, full=False, height=600)
        if want("spark"):
            shot(page, "http://localhost:4040/StreamingQuery/", "spark_streaming", wait_ms=2000, full=False, height=700)
        if want("airflow"):
            page.set_viewport_size({"width": 1500, "height": 900})
            page.goto("http://localhost:8080/login/")
            page.fill("input[name=username]", "admin")  # local demo credentials from docker-compose.yml
            page.fill("input[name=password]", "admin")
            page.click("input[type=submit]")
            page.wait_for_timeout(2000)
            shot(page, "http://localhost:8080/dags/daily_batch_pipeline/grid", "airflow_grid", wait_ms=4000,
                 full=False, width=1500, height=900)
            shot(page, "http://localhost:8080/dags/daily_batch_pipeline/graph", "airflow_graph", wait_ms=4000,
                 full=False, width=1500, height=750)
        browser.close()


if __name__ == "__main__":
    main()
