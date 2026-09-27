"""Shared pytest setup: import project modules from the repo root and pin the
simulated clock so no test needs Postgres, Kafka or Spark."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("SIM_EPOCH", "1767225600")  # 2026-01-01T00:00:00Z
os.environ.setdefault("LOG_DIR", os.path.join(os.path.dirname(__file__), ".test-logs"))
