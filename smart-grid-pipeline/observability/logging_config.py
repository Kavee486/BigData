"""Shared structured (JSON) logging for every pipeline stage.

Every component calls get_logger(component_name) so log lines are uniform
and greppable/parseable, e.g. by a log shipper in a real deployment. Each
line is one JSON object -> {"ts", "level", "component", "msg", ...extra}.
"""
import json
import logging
import os
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(component: str) -> logging.Logger:
    logger = logging.getLogger(component)
    if logger.handlers:
        return logger  # already configured (avoid duplicate handlers)

    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonFormatter())
    logger.addHandler(stream_handler)

    log_dir = os.getenv("LOG_DIR", "/logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, f"{component}.log"))
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    except OSError:
        pass  # e.g. no write access when running ad-hoc locally; stdout is enough

    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: str, msg: str, **fields):
    record_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(record_level, msg, extra={"component": logger.name, "extra_fields": fields})
