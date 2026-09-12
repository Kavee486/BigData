-- Smart Grid Lambda Pipeline: serving-layer schema.
-- Speed layer writes to live_zone_metrics / alerts / pipeline_health.
-- Batch layer writes to household_daily_consumption / tariff_reference / daily_billing_report.
-- The API reads from all of them to answer the business question.

CREATE TABLE IF NOT EXISTS live_zone_metrics (
    grid_zone           TEXT NOT NULL,
    window_start         TIMESTAMPTZ NOT NULL,
    window_end           TIMESTAMPTZ NOT NULL,
    avg_consumption_kwh  DOUBLE PRECISION NOT NULL,
    avg_solar_kwh        DOUBLE PRECISION NOT NULL,
    total_consumption_kwh DOUBLE PRECISION NOT NULL,
    total_solar_kwh      DOUBLE PRECISION NOT NULL,
    renewable_pct        DOUBLE PRECISION NOT NULL,
    event_count           INTEGER NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (grid_zone, window_start)
);

CREATE INDEX IF NOT EXISTS idx_live_zone_metrics_window
    ON live_zone_metrics (window_start DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id            BIGSERIAL PRIMARY KEY,
    alert_type    TEXT NOT NULL,           -- 'LOW_RENEWABLE' | 'NO_DATA' | 'HIGH_LOAD'
    scope         TEXT NOT NULL,           -- e.g. grid_zone name or 'GLOBAL'
    severity      TEXT NOT NULL DEFAULT 'WARNING',
    message       TEXT NOT NULL,
    metric_value  DOUBLE PRECISION,
    threshold     DOUBLE PRECISION,
    triggered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts (triggered_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_health (
    component     TEXT PRIMARY KEY,        -- 'kafka_producer' | 'speed_layer' | 'batch_layer'
    last_heartbeat TIMESTAMPTZ NOT NULL,
    status        TEXT NOT NULL DEFAULT 'OK',
    detail        TEXT
);

-- ---- Batch layer tables ---------------------------------------------------

CREATE TABLE IF NOT EXISTS household_daily_consumption (
    household_id          TEXT NOT NULL,
    sim_day                INTEGER NOT NULL,
    grid_zone              TEXT NOT NULL,
    total_consumption_kwh  DOUBLE PRECISION NOT NULL,
    total_solar_kwh        DOUBLE PRECISION NOT NULL,
    net_consumption_kwh    DOUBLE PRECISION NOT NULL,
    reading_count            INTEGER NOT NULL,
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

CREATE TABLE IF NOT EXISTS tariff_reference (
    household_id   TEXT NOT NULL,
    sim_day         INTEGER NOT NULL,
    tariff_rate     DOUBLE PRECISION NOT NULL,
    billing_tier    TEXT NOT NULL,
    subsidy_flag    BOOLEAN NOT NULL,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

CREATE TABLE IF NOT EXISTS daily_billing_report (
    household_id           TEXT NOT NULL,
    sim_day                 INTEGER NOT NULL,
    grid_zone               TEXT NOT NULL,
    total_consumption_kwh   DOUBLE PRECISION NOT NULL,
    total_solar_kwh         DOUBLE PRECISION NOT NULL,
    net_consumption_kwh     DOUBLE PRECISION NOT NULL,
    tariff_rate              DOUBLE PRECISION NOT NULL,
    billing_tier              TEXT NOT NULL,
    subsidy_flag              BOOLEAN NOT NULL,
    subsidy_discount_pct   DOUBLE PRECISION NOT NULL DEFAULT 0,
    bill_amount               DOUBLE PRECISION NOT NULL,
    generated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, sim_day)
);

CREATE INDEX IF NOT EXISTS idx_billing_sim_day ON daily_billing_report (sim_day DESC);
