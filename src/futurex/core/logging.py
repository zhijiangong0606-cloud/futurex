from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

import structlog


_SENSITIVE_PATTERN = re.compile(r"(key|secret|token|password)", re.IGNORECASE)


def _sanitize_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if _SENSITIVE_PATTERN.search(key):
            event_dict[key] = "***"
    return event_dict


def setup_logging(log_dir: str | Path = "logs", level: str = "INFO") -> None:
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _sanitize_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
        foreign_pre_chain=shared_processors,
    )

    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    trading_handler = logging.FileHandler(str(log_path / "trading.log"), encoding="utf-8")
    trading_handler.setFormatter(json_formatter)

    risk_handler = logging.FileHandler(str(log_path / "risk.log"), encoding="utf-8")
    risk_handler.setFormatter(json_formatter)

    system_handler = logging.FileHandler(str(log_path / "system.log"), encoding="utf-8")
    system_handler.setFormatter(json_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(system_handler)

    trading_logger = logging.getLogger("futurex.trading")
    trading_logger.addHandler(trading_handler)
    trading_logger.propagate = True

    risk_logger = logging.getLogger("futurex.risk")
    risk_logger.addHandler(risk_handler)
    risk_logger.propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
