from __future__ import annotations

import copy
from typing import Any

from .tle import DEFAULT_TLE_URL

# Предзагруженные сценарии для CLI и интерфейса.
PRESETS: dict[str, dict[str, Any]] = {
    "iss_moscow": {
        "name": "МКС — одна станция в Москве",
        "description": "Быстрый учебный сценарий: один спутник, одна наземная станция, расчёт на 48 часов.",
        "config": {
            "tle": "examples/iss_sample.tle",
            "satellites": [{"name": "ISS"}],
            "stations": [
                {
                    "name": "Moscow GS",
                    "lat": 55.7539,
                    "lon": 37.6208,
                    "elevation_m": 150,
                    "min_elevation_deg": 10,
                    "horizon_mask": "examples/horizon_mask.csv",
                }
            ],
            "planning": {
                "start": "now",
                "hours": 48,
                "coarse_step_sec": 60,
                "sample_step_sec": 10,
                "resolve_conflicts": True,
            },
            "filters": {
                "min_duration_min": 5,
                "min_max_elevation_deg": 15,
            },
            "data": {
                "downlink_mbps": 2,
                "capacity_mb_per_pass": 500,
                "data_generation_rate_mbps": 0.2,
                "initial_backlog_mb": 0,
            },
            "recommendation": {"mode": "top_n", "max_count": 5, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/iss_moscow",
                "csv": "outputs/iss_moscow/schedule.csv",
                "json": "outputs/iss_moscow/schedule.json",
                "html": "outputs/iss_moscow/report.html",
                "map_html": "outputs/iss_moscow/map.html",
                "ics": "outputs/iss_moscow/schedule.ics",
                "plot_dir": "outputs/iss_moscow/plots",
                "pdf": "outputs/iss_moscow/report.pdf",
                "utilization_png": "outputs/iss_moscow/station_utilization.png",
                "db": "outputs/iss_moscow/history.sqlite",
            },
        },
    },
    "iss_multi_station": {
        "name": "МКС — несколько наземных станций",
        "description": "Сравнение пролётов МКС над Москвой, Новосибирском и Владивостоком.",
        "config": {
            "tle": "examples/iss_sample.tle",
            "satellites": [{"name": "ISS"}],
            "stations": [
                {"name": "Moscow GS", "lat": 55.7539, "lon": 37.6208, "elevation_m": 150, "min_elevation_deg": 10},
                {"name": "Novosibirsk GS", "lat": 55.0084, "lon": 82.9357, "elevation_m": 160, "min_elevation_deg": 10},
                {"name": "Vladivostok GS", "lat": 43.1155, "lon": 131.8855, "elevation_m": 70, "min_elevation_deg": 10},
            ],
            "planning": {"start": "now", "hours": 72, "coarse_step_sec": 60, "sample_step_sec": 15, "resolve_conflicts": True},
            "filters": {"min_duration_min": 4, "min_max_elevation_deg": 12},
            "data": {"downlink_mbps": 2, "capacity_mb_per_pass": 600, "data_generation_rate_mbps": 0.2, "initial_backlog_mb": 100},
            "recommendation": {"mode": "best_per_satellite", "max_count": 8, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/iss_multi_station",
                "csv": "outputs/iss_multi_station/schedule.csv",
                "json": "outputs/iss_multi_station/schedule.json",
                "html": "outputs/iss_multi_station/report.html",
                "map_html": "outputs/iss_multi_station/map.html",
                "ics": "outputs/iss_multi_station/schedule.ics",
                "plot_dir": "outputs/iss_multi_station/plots",
                "pdf": "outputs/iss_multi_station/report.pdf",
                "utilization_png": "outputs/iss_multi_station/station_utilization.png",
                "db": "outputs/iss_multi_station/history.sqlite",
            },
        },
    },
    "noaa_weather": {
        "name": "Метеоспутник NOAA — приём снимков",
        "description": "Сценарий для метеоспутника NOAA 19. Используется прямой CelesTrak-запрос по NORAD ID 33591, потому что в некоторых групповых списках NOAA 19 может отсутствовать.",
        "config": {
            "tle": "https://celestrak.org/NORAD/elements/gp.php?CATNR=33591&FORMAT=tle",
            "satellites": [{"name": "NOAA 19", "norad_id": "33591"}],
            "stations": [
                {"name": "Moscow Weather GS", "lat": 55.7539, "lon": 37.6208, "elevation_m": 150, "min_elevation_deg": 8}
            ],
            "planning": {"start": "now", "hours": 72, "coarse_step_sec": 60, "sample_step_sec": 15, "resolve_conflicts": True},
            "filters": {"min_duration_min": 6, "min_max_elevation_deg": 20},
            "data": {"downlink_mbps": 0.665, "capacity_mb_per_pass": 300, "data_generation_rate_mbps": 0.05, "initial_backlog_mb": 0},
            "recommendation": {"mode": "quality", "max_count": 10, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/noaa_weather",
                "csv": "outputs/noaa_weather/schedule.csv",
                "json": "outputs/noaa_weather/schedule.json",
                "html": "outputs/noaa_weather/report.html",
                "map_html": "outputs/noaa_weather/map.html",
                "ics": "outputs/noaa_weather/schedule.ics",
                "plot_dir": "outputs/noaa_weather/plots",
                "pdf": "outputs/noaa_weather/report.pdf",
                "utilization_png": "outputs/noaa_weather/station_utilization.png",
                "db": "outputs/noaa_weather/history.sqlite",
            },
        },
    },
    "night_passes": {
        "name": "МКС — только ночные пролёты",
        "description": "Фильтр оставляет только пролёты, которые происходят ночью для наземной станции.",
        "config": {
            "tle": "examples/iss_sample.tle",
            "satellites": [{"name": "ISS"}],
            "stations": [
                {"name": "Moscow Night GS", "lat": 55.7539, "lon": 37.6208, "elevation_m": 150, "min_elevation_deg": 10}
            ],
            "planning": {"start": "now", "hours": 96, "coarse_step_sec": 60, "sample_step_sec": 15, "resolve_conflicts": True},
            "filters": {"min_duration_min": 5, "min_max_elevation_deg": 15, "only_night": True},
            "data": {"downlink_mbps": 1.5, "capacity_mb_per_pass": 400, "data_generation_rate_mbps": 0.1, "initial_backlog_mb": 0},
            "recommendation": {"mode": "top_n", "max_count": 6, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/night_passes",
                "csv": "outputs/night_passes/schedule.csv",
                "json": "outputs/night_passes/schedule.json",
                "html": "outputs/night_passes/report.html",
                "map_html": "outputs/night_passes/map.html",
                "ics": "outputs/night_passes/schedule.ics",
                "plot_dir": "outputs/night_passes/plots",
                "pdf": "outputs/night_passes/report.pdf",
                "utilization_png": "outputs/night_passes/station_utilization.png",
                "db": "outputs/night_passes/history.sqlite",
            },
        },
    },
    "station_group_multi_sat": {
        "name": "Несколько станционных спутников — конфликты",
        "description": "Сценарий показывает, как программа решает конфликт, если одна станция видит несколько спутников почти одновременно.",
        "config": {
            "tle": DEFAULT_TLE_URL,
            "satellites": [{"name": "ISS"}, {"name": "CSS"}],
            "stations": [
                {"name": "Moscow GS", "lat": 55.7539, "lon": 37.6208, "elevation_m": 150, "min_elevation_deg": 10}
            ],
            "planning": {"start": "now", "hours": 72, "coarse_step_sec": 60, "sample_step_sec": 15, "resolve_conflicts": True},
            "filters": {"min_duration_min": 4, "min_max_elevation_deg": 10},
            "data": {"downlink_mbps": 2, "capacity_mb_per_pass": 500, "data_generation_rate_mbps": 0.2, "initial_backlog_mb": 200},
            "recommendation": {"mode": "top_n", "max_count": 8, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/station_group_multi_sat",
                "csv": "outputs/station_group_multi_sat/schedule.csv",
                "json": "outputs/station_group_multi_sat/schedule.json",
                "html": "outputs/station_group_multi_sat/report.html",
                "map_html": "outputs/station_group_multi_sat/map.html",
                "ics": "outputs/station_group_multi_sat/schedule.ics",
                "plot_dir": "outputs/station_group_multi_sat/plots",
                "pdf": "outputs/station_group_multi_sat/report.pdf",
                "utilization_png": "outputs/station_group_multi_sat/station_utilization.png",
                "db": "outputs/station_group_multi_sat/history.sqlite",
            },
        },
    },
    "weather_limited": {
        "name": "МКС — погодные ограничения",
        "description": "Показывает, как дождь/гроза ухудшают индекс качества и могут запретить сеанс.",
        "config": {
            "tle": "examples/iss_sample.tle",
            "satellites": [{"name": "ISS"}],
            "stations": [
                {"name": "Moscow Rain GS", "lat": 55.7539, "lon": 37.6208, "elevation_m": 150, "min_elevation_deg": 10, "weather": "rain"},
                {"name": "Novosibirsk Storm GS", "lat": 55.0084, "lon": 82.9357, "elevation_m": 160, "min_elevation_deg": 10, "weather": "storm"},
            ],
            "planning": {"start": "now", "hours": 48, "coarse_step_sec": 60, "sample_step_sec": 15, "resolve_conflicts": True},
            "filters": {"min_duration_min": 4, "min_max_elevation_deg": 12},
            "data": {"downlink_mbps": 2, "capacity_mb_per_pass": 500, "data_generation_rate_mbps": 0.2, "initial_backlog_mb": 100},
            "recommendation": {"mode": "top_n", "max_count": 5, "min_quality_class": "B"},
            "outputs": {
                "out_dir": "outputs/weather_limited",
                "csv": "outputs/weather_limited/schedule.csv",
                "json": "outputs/weather_limited/schedule.json",
                "html": "outputs/weather_limited/report.html",
                "map_html": "outputs/weather_limited/map.html",
                "ics": "outputs/weather_limited/schedule.ics",
                "plot_dir": "outputs/weather_limited/plots",
                "pdf": "outputs/weather_limited/report.pdf",
                "utilization_png": "outputs/weather_limited/station_utilization.png",
                "db": "outputs/weather_limited/history.sqlite",
            },
        },
    },
}


def preset_keys() -> list[str]:
    return list(PRESETS.keys())


def preset_options() -> list[tuple[str, str]]:
    return [(key, PRESETS[key]["name"]) for key in preset_keys()]


def get_preset_config(key: str | None) -> dict[str, Any]:
    if not key:
        return {}
    if key not in PRESETS:
        known = ", ".join(preset_keys())
        raise KeyError(f"Неизвестный пресет {key!r}. Доступные пресеты: {known}")
    return copy.deepcopy(PRESETS[key]["config"])
