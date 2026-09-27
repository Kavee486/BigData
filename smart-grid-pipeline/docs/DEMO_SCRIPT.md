# Demo script (5–10 minutes)

Start the stack **~8 minutes before recording** (`docker compose up --build -d`)
so that at least one simulated day has been billed. Have these tabs open:
dashboard (http://localhost:8000), Airflow (http://localhost:8080, admin/admin),
Prometheus (http://localhost:9090/alerts), Spark UI (http://localhost:4040),
a terminal in the repo root, and the architecture diagram.

| Time | Show | Say |
|---|---|---|
| 0:00–1:00 | `report/architecture_diagram.png` | Use case 3, business question. Lambda: speed layer for live grid view, batch layer for exact daily bills, merged in the API. Why not Kappa: daily tariff is a snapshot, bills must be exact and cheaply re-runnable per day. |
| 1:00–2:00 | Terminal: `docker compose ps`, then `docker compose logs --tail 5 meter-producer` | 9 services, one command. Producer JSON logs: topic created with 3 partitions, events keyed by household, ~1% dirty events injected. |
| 2:00–3:30 | Dashboard (top half) + Spark UI | Live load/solar/renewable % per zone from 30 s windows; sim clock (day, time, day/night); a LOW_RENEWABLE alert on the overcast zone during daylight. Spark UI: two streaming queries. |
| 3:30–5:00 | Airflow grid + graph; `reports/daily_report_simdayN.html` | DAG polls every minute, short-circuits until a day ends, waits for the `_SUCCESS` marker, runs the Spark batch job, publishes the report, re-checks alerts. Open the HTML report: bills, solar contribution, reconciliation. |
| 5:00–6:00 | Dashboard lower half; `curl localhost:8000/api/billing/projection?household_id=H-001` | Lambda merge: provisional bill = speed-layer consumption × batch-validated tariff, next to the last final bill. Reconciliation panel: speed vs batch drift, duplicates removed, invalid tariff rows + fallback. |
| 6:00–8:00 | Terminal: `docker compose stop meter-producer`; wait ~2 min on dashboard; Prometheus alerts page | Failure detection: NO_DATA alerts for producer and speed layer, /health DEGRADED, Prometheus PipelineComponentStale firing. `docker compose start meter-producer` → alerts auto-resolve. |
| 8:00–9:00 | Terminal: `python scripts/smoke_test.py` and `pytest tests -q` | Automated verification: 11 end-to-end checks incl. every bill equals the unit-tested formula; 44 unit tests. |
| 9:00–9:30 | README | Reproducibility, limitations, what changes at production scale. |
