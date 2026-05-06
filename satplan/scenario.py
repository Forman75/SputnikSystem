from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from .config import satellite_requests_from_config, stations_from_config
from .models import ContactPass, GroundStation, TleEntry, parse_utc_datetime
from .outputs import scenario_summary_row
from .presets import get_preset_config
from .tle import DEFAULT_TLE_URL, load_tle_entries, select_tle_entries, tle_age_warnings


def _coalesce(*values):
    for v in values:
        if v is not None:
            return v
    return None


@dataclass
class ScenarioResult:
    name: str
    config: dict[str, Any]
    passes: list[ContactPass]
    stations: list[GroundStation]
    tles: list[TleEntry]
    warnings: list[str]

    def summary_row(self) -> dict[str, Any]:
        return scenario_summary_row(self.name, self.passes)


def run_config(config: dict[str, Any], name: str = "Сценарий") -> ScenarioResult:
    planning_cfg = config.get("planning", {}) if isinstance(config.get("planning", {}), dict) else {}
    filters_cfg = config.get("filters", {}) if isinstance(config.get("filters", {}), dict) else {}
    data_cfg = config.get("data", {}) if isinstance(config.get("data", {}), dict) else {}
    recommend_cfg = config.get("recommendation", {}) if isinstance(config.get("recommendation", {}), dict) else {}

    min_elev = float(_coalesce(filters_cfg.get("min_elevation_deg"), planning_cfg.get("min_elevation_deg"), 10.0))
    min_duration = float(_coalesce(filters_cfg.get("min_duration_min"), planning_cfg.get("min_duration_min"), 5.0))
    min_max_elev = filters_cfg.get("min_max_elevation_deg")
    min_max_elev = float(min_max_elev) if min_max_elev is not None else None
    start = parse_utc_datetime(planning_cfg.get("start") or "now")
    end = start + timedelta(hours=float(planning_cfg.get("hours", 48.0)))
    day_filter = "night" if filters_cfg.get("only_night") else "day" if filters_cfg.get("only_day") else "any"

    tle_source = config.get("tle") or config.get("tle_source") or DEFAULT_TLE_URL
    entries = load_tle_entries(tle_source)
    requests = satellite_requests_from_config(config) or []
    tles = select_tle_entries(entries, requests)
    stations = stations_from_config(config, default_min_elev=min_elev)
    warnings = tle_age_warnings(tles, start)

    from .planning import plan_contacts

    passes = plan_contacts(
        tle_entries=tles,
        stations=stations,
        start=start,
        end=end,
        min_duration_min=min_duration,
        min_max_elevation_deg=min_max_elev,
        coarse_step_sec=int(planning_cfg.get("coarse_step_sec", 60)),
        sample_step_sec=int(planning_cfg.get("sample_step_sec", 10)),
        day_filter=day_filter,
        resolve_conflicts=bool(planning_cfg.get("resolve_conflicts", True)),
        data_generation_rate_mbps=data_cfg.get("data_generation_rate_mbps"),
        downlink_rate_mbps=data_cfg.get("downlink_mbps"),
        capacity_mb_per_pass=data_cfg.get("capacity_mb_per_pass"),
        initial_backlog_mb=float(data_cfg.get("initial_backlog_mb", 0.0)),
        recommendation_mode=str(recommend_cfg.get("mode", "all")),
        max_recommended=recommend_cfg.get("max_count"),
        min_recommend_quality_class=str(recommend_cfg.get("min_quality_class", "C")),
    )
    return ScenarioResult(name=name, config=config, passes=passes, stations=stations, tles=tles, warnings=warnings)


def run_preset(key: str) -> ScenarioResult:
    from .presets import PRESETS

    return run_config(get_preset_config(key), name=PRESETS[key]["name"])


def compare_presets(keys: list[str]) -> tuple[list[ScenarioResult], list[dict[str, Any]]]:
    results = [run_preset(key) for key in keys]
    rows = [result.summary_row() for result in results]
    return results, rows
