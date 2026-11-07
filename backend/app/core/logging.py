import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(handler, "_researchgraph", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._researchgraph = True
        root.addHandler(handler)
