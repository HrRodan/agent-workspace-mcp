"""Logging helpers for tool modules."""

import time
import logging
from typing import Any

MAX_LOG_VALUE_LEN = 200


def truncate(value: Any, max_len: int = MAX_LOG_VALUE_LEN) -> str:
    """Truncate a string for log display, appending '…' if clipped."""
    s = str(value)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"…({len(s)} chars total)"


def log_tool_entry(logger: logging.Logger, tool_name: str, **kwargs) -> float:
    """Log tool invocation at INFO and return the start timestamp."""
    parts = [f"{k}={truncate(repr(v))}" for k, v in kwargs.items()]
    logger.info("TOOL_CALL %s(%s)", tool_name, ", ".join(parts))
    return time.monotonic()


def log_tool_exit(
    logger: logging.Logger,
    tool_name: str,
    start: float,
    *,
    success: bool = True,
    summary: str = "",
    output: Any = None,
) -> None:
    """Log tool completion at INFO (or WARNING on failure) with duration."""
    elapsed_ms = (time.monotonic() - start) * 1000
    status = "OK" if success else "FAIL"
    msg = f"TOOL_DONE {tool_name} [{status}] {elapsed_ms:.0f}ms"
    if summary:
        msg += f" | {truncate(summary)}"
    
    if output is not None and str(output) != summary:
        # Use a slightly larger snippet for results (150 chars)
        msg += f" | Output snippet: {truncate(repr(output), max_len=150)}"

    if success:
        logger.info(msg)
    else:
        logger.warning(msg)
