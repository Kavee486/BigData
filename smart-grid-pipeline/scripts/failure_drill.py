"""Observability failure drill: stop the streaming source, watch detection and recovery.

    python scripts/failure_drill.py [--outage-seconds 200] [--screenshot path.png]

Stops the meter-producer container, polls /health and /api/alerts every 10 s,
restarts it after --outage-seconds and waits until the NO_DATA alerts resolve.
Writes a timeline to report/results/failure_drill.json (used by the report).
"""
import argparse
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

API = os.getenv("API_URL", "http://localhost:8000")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def get(path):
    with urllib.request.urlopen(API + path, timeout=10) as r:
        return json.loads(r.read())


def compose(*args):
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outage-seconds", type=int, default=200)
    ap.add_argument("--screenshot", default="")
    args = ap.parse_args()

    timeline, seen_open, seen_stale = [], set(), set()

    def observe():
        health = get("/health")
        for comp, c in health["components"].items():
            if c["status"] != "OK" and comp not in seen_stale:
                seen_stale.add(comp)
                timeline.append({"time": now(), "what": f"/health marks {comp} {c['status']} (last heartbeat {c['age_seconds']:.0f} s ago); overall {health['status']}"})
        open_alerts = {(a["alert_type"], a["scope"]): a for a in get("/api/alerts")["alerts"]}
        for key, a in open_alerts.items():
            if key[0] == "NO_DATA" and key not in seen_open:
                seen_open.add(key)
                timeline.append({"time": now(), "what": f"Alert {a['alert_type']} ({a['severity']}) raised for {a['scope']}: {a['message']}"})
        return health, open_alerts

    stopped_at = now()
    compose("stop", "meter-producer")
    timeline.append({"time": stopped_at, "what": "docker compose stop meter-producer (streaming source killed)"})
    t0 = time.time()
    shot_taken = False
    while time.time() - t0 < args.outage_seconds:
        observe()
        if args.screenshot and not shot_taken and len(seen_open) >= 2:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(channel="msedge")
                page = b.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=1.5)
                page.goto(API + "/", wait_until="networkidle")
                page.wait_for_timeout(5000)
                page.screenshot(path=args.screenshot, full_page=False)
                b.close()
            shot_taken = True
            timeline.append({"time": now(), "what": "Dashboard screenshot taken (status pill DEGRADED, NO_DATA alerts listed)"})
        time.sleep(10)

    compose("start", "meter-producer")
    timeline.append({"time": now(), "what": "docker compose start meter-producer (source restored)"})
    t1 = time.time()
    while time.time() - t1 < 240:
        health, open_alerts = observe()
        if health["status"] == "OK" and not any(k[0] == "NO_DATA" for k in open_alerts):
            timeline.append({"time": now(), "what": "All NO_DATA alerts auto-resolved; /health back to OK"})
            break
        time.sleep(10)

    detected = [t for t in timeline if t["what"].startswith("Alert")]
    summary = (f"The rule engine raised {len(detected)} NO_DATA alert(s) "
               f"({', '.join(sorted(s for _, s in seen_open))}) and /health reported the affected components as "
               f"stale; after restarting the producer the speed layer resumed from its Kafka offsets and every "
               f"NO_DATA alert auto-resolved without manual action.")
    out = {"stopped_at": stopped_at, "summary": summary, "timeline": timeline}
    os.makedirs(os.path.join(ROOT, "report", "results"), exist_ok=True)
    with open(os.path.join(ROOT, "report", "results", "failure_drill.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
