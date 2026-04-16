CREATE TABLE IF NOT EXISTS raw_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id TEXT NOT NULL,
  raw_event_id INTEGER NOT NULL,
  trend_key TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  normalization_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_signals (
  signal_id TEXT PRIMARY KEY,
  trend_key TEXT NOT NULL,
  source TEXT NOT NULL,
  evidence_url TEXT NOT NULL,
  evidence_score REAL NOT NULL,
  source_diversity REAL NOT NULL,
  label_stability REAL NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trend_features_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feature_date TEXT NOT NULL,
  trend_key TEXT NOT NULL,
  adoption REAL NOT NULL,
  persistence REAL NOT NULL,
  burst REAL NOT NULL,
  novelty REAL NOT NULL,
  cross_source REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trend_scores_periodic (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trend_key TEXT NOT NULL,
  period_type TEXT NOT NULL,
  period_start TEXT NOT NULL,
  trend_score REAL NOT NULL,
  confidence REAL NOT NULL,
  lifecycle_stage TEXT NOT NULL,
  algo_version TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  score_components_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS removal_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT UNIQUE NOT NULL,
  token TEXT NOT NULL,
  request_type TEXT NOT NULL,
  requester_contact TEXT NOT NULL,
  target_signal_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  retries INTEGER NOT NULL
);
