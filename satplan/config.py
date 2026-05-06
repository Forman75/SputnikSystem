from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .horizon import load_horizon_mask
from .models import GroundStation, SatelliteRequest, parse_utc_datetime


def load_config(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Конфигурационный файл не найден: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml должен содержать словарь верхнего уровня")
    return data


def deep_merge_configs(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    """Возвращает копию base, поверх которой рекурсивно наложен override.
    """
    import copy

    result: dict[str, Any] = copy.deepcopy(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_configs(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def satellite_requests_from_config(config: dict[str, Any]) -> list[SatelliteRequest]:
    raw = config.get("satellites") or config.get("satellite") or []
    if isinstance(raw, str):
        raw = [raw]
    requests: list[SatelliteRequest] = []
    for item in raw:
        if isinstance(item, str):
            requests.append(SatelliteRequest(query=item))
        elif isinstance(item, dict):
            requests.append(SatelliteRequest(query=item.get("name") or item.get("query"), norad_id=str(item.get("norad_id")) if item.get("norad_id") is not None else None))
        else:
            raise ValueError(f"Некорректное описание спутника: {item!r}")
    return requests


def stations_from_config(config: dict[str, Any], default_min_elev: float = 10.0) -> list[GroundStation]:
    raw = config.get("stations") or config.get("station") or []
    if isinstance(raw, dict):
        raw = [raw]
    stations: list[GroundStation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Некорректное описание станции: {item!r}")
        mask = None
        if item.get("horizon_mask"):
            mask = load_horizon_mask(item["horizon_mask"])
        st = GroundStation(
            name=item.get("name", "Ground station"),
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            elevation_m=float(item.get("elevation_m", item.get("elev_m", 0.0))),
            min_elevation_deg=float(item.get("min_elevation_deg", default_min_elev)),
            horizon_mask=mask,
            weather_condition=str(item.get("weather_condition", item.get("weather", "clear"))),
        )
        st.validate()
        stations.append(st)
    return stations


def parse_station_arg(value: str, default_min_elev: float = 10.0) -> GroundStation:
    """Парсит --station "Name,lat,lon,elev[,min_elev]"."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 3:
        raise ValueError("--station должен иметь вид Name,lat,lon,elev[,min_elev]")
    name = parts[0]
    lat = float(parts[1])
    lon = float(parts[2])
    elev = float(parts[3]) if len(parts) >= 4 and parts[3] else 0.0
    min_el = float(parts[4]) if len(parts) >= 5 and parts[4] else default_min_elev
    st = GroundStation(name=name, lat=lat, lon=lon, elevation_m=elev, min_elevation_deg=min_el)
    st.validate()
    return st


def stations_from_csv(path: str | Path, default_min_elev: float = 10.0) -> list[GroundStation]:
    import csv

    stations: list[GroundStation] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            st = GroundStation(
                name=row.get("name") or row.get("station") or "Ground station",
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                elevation_m=float(row.get("elevation_m") or row.get("elev_m") or 0.0),
                min_elevation_deg=float(row.get("min_elevation_deg") or default_min_elev),
                weather_condition=str(row.get("weather_condition") or row.get("weather") or "clear"),
            )
            st.validate()
            stations.append(st)
    return stations


def planning_window(config: dict[str, Any], start_override: str | None = None, hours_override: float | None = None):
    planning = config.get("planning", {}) if isinstance(config.get("planning", {}), dict) else {}
    start_raw = start_override or planning.get("start") or "now"
    hours = float(hours_override if hours_override is not None else planning.get("hours", 48.0))
    start = parse_utc_datetime(start_raw)
    return start, start + __import__("datetime").timedelta(hours=hours)
