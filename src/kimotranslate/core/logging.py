"""Logging estructurado stdlib. Redacta claves antes de emitir."""

from __future__ import annotations

import logging
import re

_REDACT = re.compile(r"(?i)(api[_-]?key|worker[_-]?key|token|secret|password)\s*[:=]\s*\S+")


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _REDACT.sub(r"\1=<redacted>", str(record.msg))
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger = logging.getLogger("kimotranslate")
    logger.addFilter(RedactFilter())
    return logger
