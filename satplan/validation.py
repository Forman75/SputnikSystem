from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import GroundStation, TleEntry


def validate_planning_parameters(
    *,
    start: datetime,
    end: datetime,
    min_duration_min: float,
    min_max_elevation_deg: float | None,
    coarse_step_sec: int,
    sample_step_sec: int,
    day_filter: str,
    downlink_rate_mbps: float | None = None,
    capacity_mb_per_pass: float | None = None,
    data_generation_rate_mbps: float | None = None,
    initial_backlog_mb: float = 0.0,
) -> None:
    if end <= start:
        raise ValueError("Конец периода расчёта должен быть позже начала.")
    hours = (end - start).total_seconds() / 3600.0
    if hours <= 0 or hours > 24 * 30:
        raise ValueError("Горизонт расчёта должен быть в диапазоне от 1 минуты до 30 суток.")
    if min_duration_min < 0 or min_duration_min > 240:
        raise ValueError("Минимальная длительность должна быть от 0 до 240 минут.")
    if min_max_elevation_deg is not None and not (0 <= min_max_elevation_deg <= 90):
        raise ValueError("Минимальный максимальный угол должен быть от 0 до 90 градусов.")
    if coarse_step_sec <= 0 or sample_step_sec <= 0:
        raise ValueError("Шаги расчёта должны быть положительными.")
    if sample_step_sec > max(1, coarse_step_sec):
        raise ValueError("Шаг профиля пролёта не должен быть больше грубого шага поиска.")
    if day_filter not in {"any", "day", "night"}:
        raise ValueError("Фильтр день/ночь должен быть: any, day или night.")
    for label, value in {
        "скорость передачи": downlink_rate_mbps,
        "лимит за сеанс": capacity_mb_per_pass,
        "скорость накопления": data_generation_rate_mbps,
        "начальный остаток": initial_backlog_mb,
    }.items():
        if value is not None and float(value) < 0:
            raise ValueError(f"Параметр '{label}' не может быть отрицательным.")


def validate_tles(tles: Iterable[TleEntry]) -> None:
    items = list(tles)
    if not items:
        raise ValueError("Не выбран ни один спутник.")
    for tle in items:
        if not tle.line1.startswith("1 ") or not tle.line2.startswith("2 "):
            raise ValueError(f"Некорректная TLE-запись для {tle.name}.")
        if len(tle.line1) < 60 or len(tle.line2) < 60:
            raise ValueError(f"TLE-запись для {tle.name} выглядит слишком короткой.")


def validate_stations(stations: Iterable[GroundStation]) -> None:
    items = list(stations)
    if not items:
        raise ValueError("Не задана ни одна наземная станция.")
    seen: set[str] = set()
    for station in items:
        station.validate()
        key = station.name.strip().casefold()
        if key in seen:
            raise ValueError(f"Название станции повторяется: {station.name}.")
        seen.add(key)
