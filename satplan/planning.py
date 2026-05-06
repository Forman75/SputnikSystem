from __future__ import annotations

import bisect
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, Optional

import numpy as np

try:
    from skyfield.api import EarthSatellite, load, wgs84
except ImportError:
    # Позволяет запускать тесты без skyfield.
    EarthSatellite = object
    load = None
    wgs84 = None

from .horizon import required_elevation_for_azimuth
from .models import UTC, ContactPass, GroundStation, PassProfilePoint, TleEntry, iso_utc, parse_utc_datetime
from .sun import solar_elevation_deg
from .utils import datetime_range


def make_timescale_datetimes(ts, datetimes: list[datetime]):
    try:
        return ts.from_datetimes(datetimes)
    except AttributeError:
        dts = [d.astimezone(UTC) for d in datetimes]
        return ts.utc(
            [d.year for d in dts],
            [d.month for d in dts],
            [d.day for d in dts],
            [d.hour for d in dts],
            [d.minute for d in dts],
            [d.second + d.microsecond / 1_000_000 for d in dts],
        )


def _require_skyfield() -> None:
    if load is None or wgs84 is None:
        raise ImportError("Для расчёта орбит установите зависимость skyfield: pip install skyfield")


def skyfield_station(station: GroundStation):
    _require_skyfield()
    station.validate()
    return wgs84.latlon(station.lat, station.lon, elevation_m=station.elevation_m)


def compute_alt_az_range(satellite: EarthSatellite, station_sf, ts, datetimes: list[datetime]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times = make_timescale_datetimes(ts, datetimes)
    alt, az, distance = (satellite - station_sf).at(times).altaz()
    return np.asarray(alt.degrees), np.asarray(az.degrees), np.asarray(distance.km)


def compute_subpoints(satellite: EarthSatellite, ts, datetimes: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    times = make_timescale_datetimes(ts, datetimes)
    geocentric = satellite.at(times)
    subpoints = wgs84.subpoint(geocentric)
    return np.asarray(subpoints.latitude.degrees), np.asarray(subpoints.longitude.degrees)


def visibility_margin_at(satellite: EarthSatellite, station_sf, ts, station: GroundStation, dt: datetime) -> float:
    t = ts.from_datetime(dt.astimezone(UTC))
    alt, az, _distance = (satellite - station_sf).at(t).altaz()
    required = required_elevation_for_azimuth(float(az.degrees), station.min_elevation_deg, station.horizon_mask)
    return float(alt.degrees) - float(required)


def refine_visibility_crossing(
    satellite: EarthSatellite,
    station_sf,
    ts,
    station: GroundStation,
    a: datetime,
    b: datetime,
    iterations: int = 28,
) -> datetime:
    fa = visibility_margin_at(satellite, station_sf, ts, station, a)
    fb = visibility_margin_at(satellite, station_sf, ts, station, b)
    if fa == 0:
        return a
    if fb == 0:
        return b
    if fa * fb > 0:
        return a if abs(fa) < abs(fb) else b

    left, right = a, b
    f_left = fa
    for _ in range(iterations):
        mid = left + (right - left) / 2
        f_mid = visibility_margin_at(satellite, station_sf, ts, station, mid)
        if f_left * f_mid <= 0:
            right = mid
        else:
            left = mid
            f_left = f_mid
    return left + (right - left) / 2


WEATHER_PENALTIES = {
    "clear": 0.0,
    "cloudy": 5.0,
    "fog": 10.0,
    "rain": 15.0,
    "snow": 20.0,
    "storm": 35.0,
}


def weather_penalty(condition: str) -> float:
    return WEATHER_PENALTIES.get(condition, 0.0)


def classify_pass(
    max_elevation_deg: float,
    avg_elevation_deg: float,
    duration_min: float,
    range_at_max_km: float,
    weather_condition: str = "clear",
) -> tuple[float, str, float, bool]:
    """Индекс качества 0-100.
    Чем выше и дольше пролёт, чем меньше дальность и чем лучше погода, тем выше
    индекс. Для учебной модели сильная гроза делает сеанс недоступным.
    """
    range_penalty = max(0.0, min(20.0, (range_at_max_km - 500.0) / 250.0))
    meteo_penalty = weather_penalty(weather_condition)
    raw_score = 0.55 * max_elevation_deg + 0.25 * avg_elevation_deg + 2.6 * duration_min - range_penalty
    score = round(max(0.0, min(100.0, raw_score - meteo_penalty)), 2)
    weather_ok = weather_condition != "storm"
    if score >= 80 and weather_ok:
        quality = "A"
    elif score >= 55 and weather_ok:
        quality = "B"
    else:
        quality = "C"
    return score, quality, meteo_penalty, weather_ok


def find_contact_passes_for_pair(
    satellite: EarthSatellite,
    tle: TleEntry,
    station: GroundStation,
    start: datetime,
    end: datetime,
    min_duration_min: float = 5.0,
    min_max_elevation_deg: float | None = None,
    coarse_step_sec: int = 60,
    sample_step_sec: int = 10,
    day_filter: str = "any",
) -> list[ContactPass]:
    """Находит все сеансы связи для одной пары спутник-станция."""
    _require_skyfield()
    ts = load.timescale()
    station_sf = skyfield_station(station)
    grid = datetime_range(start, end, coarse_step_sec)
    alt, az, _rng = compute_alt_az_range(satellite, station_sf, ts, grid)
    required = required_elevation_for_azimuth(az, station.min_elevation_deg, station.horizon_mask)
    above = alt >= required

    intervals: list[tuple[datetime, datetime]] = []
    in_pass = False
    pass_start: Optional[datetime] = None

    for i, is_above in enumerate(above):
        if is_above and not in_pass:
            if i == 0:
                pass_start = grid[i]
            else:
                pass_start = refine_visibility_crossing(satellite, station_sf, ts, station, grid[i - 1], grid[i])
            in_pass = True

        next_is_below = i == len(above) - 1 or not bool(above[i + 1])
        if in_pass and is_above and next_is_below:
            if i == len(above) - 1:
                pass_end = grid[i]
            else:
                pass_end = refine_visibility_crossing(satellite, station_sf, ts, station, grid[i], grid[i + 1])
            if pass_start is not None and pass_end > pass_start:
                intervals.append((pass_start, pass_end))
            in_pass = False
            pass_start = None

    passes: list[ContactPass] = []
    for pass_start, pass_end in intervals:
        duration_min = (pass_end - pass_start).total_seconds() / 60.0
        if duration_min < min_duration_min:
            continue

        sample_grid = datetime_range(pass_start, pass_end, sample_step_sec)
        alt_s, az_s, rng_s = compute_alt_az_range(satellite, station_sf, ts, sample_grid)
        required_s = required_elevation_for_azimuth(az_s, station.min_elevation_deg, station.horizon_mask)
        valid = alt_s >= required_s
        if not np.any(valid):
            continue

        max_idx = int(np.argmax(alt_s))
        max_el = float(alt_s[max_idx])
        if min_max_elevation_deg is not None and max_el < min_max_elevation_deg:
            continue

        mid = pass_start + (pass_end - pass_start) / 2
        sun_el = solar_elevation_deg(mid, station.lat, station.lon)
        day_night = "day" if sun_el >= 0 else "night"
        if day_filter == "day" and day_night != "day":
            continue
        if day_filter == "night" and day_night != "night":
            continue

        sub_lat, sub_lon = compute_subpoints(satellite, ts, sample_grid)
        avg_el = float(np.mean(alt_s[valid]))
        score, quality, meteo_penalty, weather_ok = classify_pass(max_el, avg_el, duration_min, float(rng_s[max_idx]), station.weather_condition)

        profile = [
            PassProfilePoint(
                utc=iso_utc(dt),
                elevation_deg=round(float(a), 3),
                azimuth_deg=round(float(z), 3),
                required_elevation_deg=round(float(req), 3),
                range_km=round(float(r), 3),
                sun_elevation_deg=round(solar_elevation_deg(dt, station.lat, station.lon), 3),
                sub_lat_deg=round(float(slat), 6),
                sub_lon_deg=round(float(slon), 6),
            )
            for dt, a, z, req, r, slat, slon in zip(sample_grid, alt_s, az_s, required_s, rng_s, sub_lat, sub_lon)
        ]

        passes.append(
            ContactPass(
                satellite=satellite.name,
                norad_id=tle.norad_id,
                station=station.name,
                station_lat=station.lat,
                station_lon=station.lon,
                start_utc=iso_utc(pass_start),
                end_utc=iso_utc(pass_end),
                duration_min=round(duration_min, 2),
                max_elevation_deg=round(max_el, 2),
                avg_elevation_deg=round(avg_el, 2),
                max_elevation_time_utc=iso_utc(sample_grid[max_idx]),
                azimuth_at_max_deg=round(float(az_s[max_idx]), 2),
                range_at_max_km=round(float(rng_s[max_idx]), 1),
                sun_elevation_at_mid_deg=round(float(sun_el), 2),
                day_night=day_night,
                quality_score=score,
                quality_class=quality,
                weather_condition=station.weather_condition,
                weather_penalty=round(meteo_penalty, 2),
                weather_ok=weather_ok,
                scheduled=weather_ok,
                conflict_reason=None if weather_ok else "Сеанс запрещён погодой",
                profile=profile,
            )
        )
    return passes


def resolve_station_conflicts(passes: list[ContactPass]) -> list[ContactPass]:
    """Выбирает непересекающиеся сеансы для каждой станции.
    Одна наземная станция не может одновременно принимать два спутника. Используется
    динамическое программирование для максимизации суммарного качества.
    """
    by_station: dict[str, list[ContactPass]] = defaultdict(list)
    for p in passes:
        if p.weather_ok:
            by_station[p.station].append(p)
        else:
            p.scheduled = False
            p.conflict_reason = p.conflict_reason or "Сеанс запрещён погодой"

    chosen_ids: set[int] = set()
    conflicts: dict[int, str] = {}

    for _station, items in by_station.items():
        items = sorted(items, key=lambda p: (p.end_dt(), p.start_dt()))
        n = len(items)
        ends = [p.end_dt() for p in items]
        starts = [p.start_dt() for p in items]
        p_index = [bisect.bisect_right(ends, starts[i]) - 1 for i in range(n)]
        weights = [p.quality_score + 0.1 * p.duration_min for p in items]
        dp = [0.0] * (n + 1)
        take = [False] * n
        for i in range(1, n + 1):
            with_i = weights[i - 1] + dp[p_index[i - 1] + 1]
            without_i = dp[i - 1]
            if with_i > without_i:
                dp[i] = with_i
                take[i - 1] = True
            else:
                dp[i] = without_i

        selected_local: set[int] = set()
        i = n - 1
        while i >= 0:
            with_i = weights[i] + dp[p_index[i] + 1]
            without_i = dp[i]
            if take[i] and with_i >= without_i:
                selected_local.add(i)
                i = p_index[i]
            else:
                i -= 1

        selected_intervals = [items[i] for i in selected_local]
        for idx, item in enumerate(items):
            if idx in selected_local:
                chosen_ids.add(id(item))
            else:
                overlap = [s for s in selected_intervals if not (item.end_dt() <= s.start_dt() or item.start_dt() >= s.end_dt())]
                if overlap:
                    best = max(overlap, key=lambda p: p.quality_score)
                    conflicts[id(item)] = f"Конфликт со слотом {best.satellite} {best.start_utc}–{best.end_utc}; выбран сеанс с более высоким приоритетом"
                else:
                    conflicts[id(item)] = "Отклонён оптимизатором расписания станции"

    for p in passes:
        if id(p) in chosen_ids:
            p.scheduled = True
            p.conflict_reason = None
        else:
            p.scheduled = False
            if not p.weather_ok:
                p.conflict_reason = p.conflict_reason or "Сеанс запрещён погодой"
            else:
                p.conflict_reason = conflicts.get(id(p), "Конфликт расписания")
    return passes


def apply_data_budget(
    passes: list[ContactPass],
    planning_start: datetime,
    data_generation_rate_mbps: float | None = None,
    downlink_rate_mbps: float | None = None,
    capacity_mb_per_pass: float | None = None,
    initial_backlog_mb: float = 0.0,
    scheduled_only: bool = True,
) -> None:
    """Добавляет расчёт накопления и передачи данных по каждому спутнику."""
    if data_generation_rate_mbps is None and downlink_rate_mbps is None and capacity_mb_per_pass is None:
        return

    by_sat: dict[str, list[ContactPass]] = defaultdict(list)
    for p in passes:
        by_sat[p.norad_id].append(p)

    for _norad, items in by_sat.items():
        items = sorted(items, key=lambda p: p.start_dt())
        backlog_mb = float(initial_backlog_mb)
        cursor = planning_start
        for p in items:
            pass_start = p.start_dt()
            pass_end = p.end_dt()
            elapsed_sec = max(0.0, (pass_start - cursor).total_seconds())
            generated = 0.0
            if data_generation_rate_mbps is not None:
                generated = data_generation_rate_mbps * elapsed_sec / 8.0
                backlog_mb += generated

            duration_sec = (pass_end - pass_start).total_seconds()
            capacities: list[float] = []
            if capacity_mb_per_pass is not None:
                capacities.append(float(capacity_mb_per_pass))
            if downlink_rate_mbps is not None:
                capacities.append(float(downlink_rate_mbps) * duration_sec / 8.0)
            capacity = min(capacities) if capacities else math.inf

            can_tx = p.scheduled or not scheduled_only
            transmitted = min(backlog_mb, capacity) if can_tx and math.isfinite(capacity) else (backlog_mb if can_tx else 0.0)
            backlog_mb = max(0.0, backlog_mb - transmitted)

            p.generated_before_mb = round(generated, 2)
            p.capacity_mb = round(capacity, 2) if math.isfinite(capacity) else None
            p.transmitted_mb = round(transmitted, 2)
            p.backlog_after_mb = round(backlog_mb, 2)
            cursor = pass_end if can_tx else pass_start


def apply_recommendations(
    passes: list[ContactPass],
    mode: str = "all",
    max_count: int | None = None,
    min_quality_class: str = "C",
) -> None:
    """Помечает рекомендованное расписание.

    mode:
    - all: все запланированные сеансы;
    - top_n: лучшие N сеансов по индексу качества;
    - best_per_satellite: лучший сеанс для каждого спутника;
    - quality: только сеансы не ниже указанного класса качества.
    """
    rank = {"A": 3, "B": 2, "C": 1}
    mode = (mode or "all").strip().lower()
    candidates = [p for p in passes if p.scheduled and p.weather_ok]
    for p in passes:
        p.recommended = False
        p.recommendation_reason = None

    if mode == "all":
        chosen = candidates
        reason = "Все запланированные сеансы"
    elif mode == "top_n":
        n = max_count or 5
        chosen = sorted(candidates, key=lambda p: (p.quality_score, p.duration_min), reverse=True)[:n]
        reason = f"Топ-{n} по индексу качества"
    elif mode == "best_per_satellite":
        grouped: dict[str, list[ContactPass]] = defaultdict(list)
        for p in candidates:
            grouped[p.norad_id].append(p)
        chosen = [max(items, key=lambda p: (p.quality_score, p.duration_min)) for items in grouped.values()]
        reason = "Лучший сеанс для каждого спутника"
    elif mode == "quality":
        min_rank = rank.get(min_quality_class.upper(), 1)
        chosen = [p for p in candidates if rank.get(p.quality_class, 0) >= min_rank]
        reason = f"Класс качества не ниже {min_quality_class.upper()}"
    else:
        raise ValueError("Неизвестный режим рекомендаций. Доступно: all, top_n, best_per_satellite, quality")

    chosen_ids = {id(p) for p in chosen}
    for p in passes:
        if id(p) in chosen_ids:
            p.recommended = True
            p.recommendation_reason = reason
        elif p.scheduled:
            p.recommendation_reason = "Не вошёл в рекомендованное расписание"


def plan_contacts(
    tle_entries: Iterable[TleEntry],
    stations: Iterable[GroundStation],
    start: datetime,
    end: datetime,
    min_duration_min: float = 5.0,
    min_max_elevation_deg: float | None = None,
    coarse_step_sec: int = 60,
    sample_step_sec: int = 10,
    day_filter: str = "any",
    resolve_conflicts: bool = True,
    data_generation_rate_mbps: float | None = None,
    downlink_rate_mbps: float | None = None,
    capacity_mb_per_pass: float | None = None,
    initial_backlog_mb: float = 0.0,
    recommendation_mode: str = "all",
    max_recommended: int | None = None,
    min_recommend_quality_class: str = "C",
) -> list[ContactPass]:
    from .validation import validate_planning_parameters

    validate_planning_parameters(
        start=start,
        end=end,
        min_duration_min=min_duration_min,
        min_max_elevation_deg=min_max_elevation_deg,
        coarse_step_sec=coarse_step_sec,
        sample_step_sec=sample_step_sec,
        day_filter=day_filter,
        downlink_rate_mbps=downlink_rate_mbps,
        capacity_mb_per_pass=capacity_mb_per_pass,
        data_generation_rate_mbps=data_generation_rate_mbps,
        initial_backlog_mb=initial_backlog_mb,
    )
    _require_skyfield()
    ts = load.timescale()
    passes: list[ContactPass] = []
    station_list = list(stations)
    for station in station_list:
        station.validate()

    for tle in tle_entries:
        sat = EarthSatellite(tle.line1, tle.line2, tle.name, ts)
        for station in station_list:
            passes.extend(
                find_contact_passes_for_pair(
                    satellite=sat,
                    tle=tle,
                    station=station,
                    start=start,
                    end=end,
                    min_duration_min=min_duration_min,
                    min_max_elevation_deg=min_max_elevation_deg,
                    coarse_step_sec=coarse_step_sec,
                    sample_step_sec=sample_step_sec,
                    day_filter=day_filter,
                )
            )

    passes.sort(key=lambda p: (p.start_utc, p.station, p.satellite))
    if resolve_conflicts:
        resolve_station_conflicts(passes)
    apply_data_budget(
        passes,
        planning_start=start,
        data_generation_rate_mbps=data_generation_rate_mbps,
        downlink_rate_mbps=downlink_rate_mbps,
        capacity_mb_per_pass=capacity_mb_per_pass,
        initial_backlog_mb=initial_backlog_mb,
        scheduled_only=True,
    )
    apply_recommendations(
        passes,
        mode=recommendation_mode,
        max_count=max_recommended,
        min_quality_class=min_recommend_quality_class,
    )
    return passes
