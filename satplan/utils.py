from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from .models import UTC


def datetime_range(start: datetime, end: datetime, step_seconds: int) -> list[datetime]:
    if step_seconds <= 0:
        raise ValueError("Шаг времени должен быть положительным")
    result: list[datetime] = []
    cur = start.astimezone(UTC)
    end = end.astimezone(UTC)
    step = timedelta(seconds=step_seconds)
    while cur <= end:
        result.append(cur)
        cur += step
    if not result or result[-1] < end:
        result.append(end)
    return result


def safe_filename(value: str, max_len: int = 96) -> str:
    safe = re.sub(r"[^A-Za-zА-Яа-я0-9_.-]+", "_", value).strip("_")
    return safe[:max_len] or "file"


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def ics_dt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
