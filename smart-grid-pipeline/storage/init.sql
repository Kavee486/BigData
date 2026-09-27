-- Smart Grid Lambda Pipeline: serving-layer schema (PostgreSQL).
--
--   Speed layer  -> live_zone_metrics, live_household_consumption, stream_quality_metrics
--   Batch layer  -> household_daily_consumption, tariff_reference, daily_billing_report,
--                   batch_reconciliation
--   Observability-> alerts, pipeline_health
--   Shared       -> sim_clock (the single epoch every component derives sim_day from)
--
-- The FastAPI serving layer reads all of them and merges the speed and batch
-- views at query time.

-- ---- Shared simulated clock ----------------------------------------------
CREATE TABLE IF NOT EXISTS sim_clock (
    id     INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    epoch  TIMESTAMPTZ NOT NULL
);
INSERT INTO sim_clock (id, epoch) VALUES (1, now()) ON CONFLICT (id) DO NOTHING;

-- ---- Speed layer tables -------------------------------------------------
CREATE TABLE IF NOT EXISTS live_zone_metrics (
    grid_zone             TEXT NOT NULL,
    window_start          TIMESTAMPTZ NOT NULL,
    window_end            TIMESTAMPTZ NOT NULL,
    avg_consumption_kwh   DOUBLE PRECISION NOT NULL,
    avg_solar_kwh         DOUBLE PRECISION NOT NULL,
    total_consumption_kwh DOUBLE PRECISION NOT NULL,
    total_solar_kwh       DOUBLE PRECISION NOT NULL,
    renewable_pct         DOUBLE PRECISION NOT NULL,
    event_count           INTEGER NOT NULL,
    household_count       INTEGER NOT NULL DEFAULT 0,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (grid_zone, window_start)
);
CREATE INDEX IF NOT EXISTS idx_live_zone_metrics_window ON live_zone_metrics (window_start DESC);

-- Running (approximate, additive) per-household totals for the current day.
CREATE TABLE IF NOT EXISTS live_household_consumption (
    household_id     TEXT NOT NULL,
    sim_day          INTEGER NOT NULL,
    grid_zone        TEXT NOT NULL,
    consumption_kwh  DOUBLE PRECISION NOT NULL,
    solar_kwh        DOUBLE PRECISION NOT NULL,
    reading_count    INTEGER NOT NULL,
    last_event_time  TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

-- One row per speed-layer micro-batch: volume, data quality and latency.
CREATE TABLE IF NOT EXISTS stream_quality_metrics (
    id                 BIGSERIAL PRIMARY KEY,
    batch_id           BIGINT NOT NULL,
    total_events       INTEGER NOT NULL,
    clean_events       INTEGER NOT NULL,
    invalid_events     INTEGER NOT NULL,
    duplicate_events   INTEGER NOT NULL,
    invalid_by_reason  JSONB NOT NULL DEFAULT '{}'::jsonb,
    avg_lag_seconds    DOUBLE PRECISION,
    max_lag_seconds    DOUBLE PRECISION,
    processing_seconds DOUBLE PRECISION,
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_stream_quality_recorded ON stream_quality_metrics (recorded_at DESC);

-- ---- Observability tables -------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id            BIGSERIAL PRIMARY KEY,
    alert_type    TEXT NOT NULL,           -- LOW_RENEWABLE | NO_DATA | COMPONENT_FAILED | HIGH_INVALID_RATE
                                           -- | HIGH_STREAM_LAG | RECONCILIATION_DRIFT
    scope         TEXT NOT NULL,           -- grid zone, component name or sim_day
    severity      TEXT NOT NULL DEFAULT 'WARNING',
    message       TEXT NOT NULL,
    metric_value  DOUBLE PRECISION,
    threshold     DOUBLE PRECISION,
    triggered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved      BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts (triggered_at DESC);
-- At most one OPEN alert per (type, scope): the engine updates it instead of spamming.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_open ON alerts (alert_type, scope) WHERE NOT resolved;

CREATE TABLE IF NOT EXISTS pipeline_health (
    component      TEXT PRIMARY KEY,       -- meter_producer | tariff_batch_source | speed_layer
                                           -- | batch_layer | alerts_engine
    last_heartbeat TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'OK',
    detail         TEXT
);

-- ---- Batch layer tables ---------------------------------------------------
CREATE TABLE IF NOT EXISTS household_daily_consumption (
    household_id            TEXT NOT NULL,
    sim_day                 INTEGER NOT NULL,
    grid_zone               TEXT NOT NULL,
    total_consumption_kwh   DOUBLE PRECISION NOT NULL,
    total_solar_kwh         DOUBLE PRECISION NOT NULL,
    net_consumption_kwh     DOUBLE PRECISION NOT NULL,
    solar_export_kwh        DOUBLE PRECISION NOT NULL DEFAULT 0,
    solar_contribution_pct  DOUBLE PRECISION NOT NULL DEFAULT 0,
    peak_reading_kwh        DOUBLE PRECISION,
    reading_count           INTEGER NOT NULL,
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

CREATE TABLE IF NOT EXISTS tariff_reference (
    household_id   TEXT NOT NULL,
    sim_day        INTEGER NOT NULL,
    tariff_rate    DOUBLE PRECISION NOT NULL CHECK (tariff_rate > 0),
    billing_tier   TEXT NOT NULL,
    subsidy_flag   BOOLEAN NOT NULL,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

CREATE TABLE IF NOT EXISTS daily_billing_report (
    household_id            TEXT NOT NULL,
    sim_day                 INTEGER NOT NULL,
    grid_zone               TEXT NOT NULL,
    total_consumption_kwh   DOUBLE PRECISION NOT NULL,
    total_solar_kwh         DOUBLE PRECISION NOT NULL,
    net_consumption_kwh     DOUBLE PRECISION NOT NULL,
    solar_export_kwh        DOUBLE PRECISION NOT NULL DEFAULT 0,
    solar_contribution_pct  DOUBLE PRECISION NOT NULL DEFAULT 0,
    tariff_rate             DOUBLE PRECISION NOT NULL,
    billing_tier            TEXT NOT NULL,
    subsidy_flag            BOOLEAN NOT NULL,
    subsidy_discount_pct    DOUBLE PRECISION NOT NULL DEFAULT 0,
    tariff_source           TEXT NOT NULL DEFAULT 'current_day',  -- current_day | fallback_previous_day
    bill_amount             DOUBLE PRECISION NOT NULL,
    run_id                  TEXT,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);
CREATE INDEX IF NOT EXISTS idx_billing_sim_day ON daily_billing_report (sim_day DESC);

-- One row per billed day: exact batch view vs approximate speed view, plus
-- the data-quality counters of that run.
CREATE TABLE IF NOT EXISTS batch_reconciliation (
    sim_day                INTEGER PRIMARY KEY,
    run_id                 TEXT,
    speed_consumption_kwh  DOUBLE PRECISION,
    batch_consumption_kwh  DOUBLE PRECISION,
    drift_pct              DOUBLE PRECISION,
    speed_readings         INTEGER,
    batch_readings         INTEGER,
    raw_events             INTEGER,
    duplicates_removed     INTEGER,
    tariff_rows            INTEGER,
    invalid_tariff_rows    INTEGER,
    duplicate_tariff_rows  INTEGER,
    fallback_tariffs       INTEGER,
    households_billed      INTEGER,
    households_unbilled    INTEGER,
    total_billed           DOUBLE PRECISION,
    reconciled_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
