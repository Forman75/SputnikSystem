from __future__ import annotations

import base64
import csv
import html
import json
import math
import mimetypes
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from .models import UTC, ContactPass, GroundStation, parse_utc_datetime
from .utils import ensure_dir, escape_ics, ics_dt, safe_filename

CSV_FIELDS = [
    "scheduled",
    "recommended",
    "quality_class",
    "quality_score",
    "satellite",
    "norad_id",
    "station",
    "start_utc",
    "end_utc",
    "duration_min",
    "max_elevation_deg",
    "avg_elevation_deg",
    "max_elevation_time_utc",
    "azimuth_at_max_deg",
    "range_at_max_km",
    "sun_elevation_at_mid_deg",
    "day_night",
    "weather_condition",
    "weather_penalty",
    "weather_ok",
    "capacity_mb",
    "generated_before_mb",
    "transmitted_mb",
    "backlog_after_mb",
    "conflict_reason",
    "recommendation_reason",
]

RUSSIAN_COLUMN_LABELS = {
    "scheduled": "Запланирован",
    "recommended": "Рекомендован",
    "quality_class": "Класс качества",
    "quality_score": "Индекс качества, 0-100",
    "satellite": "Спутник",
    "norad_id": "NORAD ID",
    "station": "Станция",
    "start_utc": "Начало UTC",
    "end_utc": "Конец UTC",
    "duration_min": "Длительность, мин",
    "max_elevation_deg": "Макс. угол, °",
    "avg_elevation_deg": "Средний угол, °",
    "max_elevation_time_utc": "Время макс. угла UTC",
    "azimuth_at_max_deg": "Азимут при макс. угле, °",
    "range_at_max_km": "Дальность при макс. угле, км",
    "sun_elevation_at_mid_deg": "Высота Солнца в середине, °",
    "day_night": "День/ночь",
    "weather_condition": "Погода",
    "weather_penalty": "Штраф за погоду",
    "weather_ok": "Погода допускает связь",
    "capacity_mb": "Ёмкость сеанса, МБ",
    "generated_before_mb": "Накоплено перед сеансом, МБ",
    "transmitted_mb": "Передано, МБ",
    "backlog_after_mb": "Остаток после сеанса, МБ",
    "conflict_reason": "Причина пропуска",
    "recommendation_reason": "Причина рекомендации",
}

DAY_NIGHT_RU = {"day": "день", "night": "ночь", "any": "любой"}
WEATHER_RU = {
    "clear": "ясно",
    "cloudy": "облачно",
    "rain": "дождь",
    "snow": "снег",
    "storm": "гроза",
    "fog": "туман",
}


def _format_display_value(key: str, value: Any) -> Any:
    if value is None:
        return ""
    if key in {"scheduled", "recommended", "weather_ok"}:
        return "да" if bool(value) else "нет"
    if key == "day_night":
        return DAY_NIGHT_RU.get(str(value), value)
    if key == "weather_condition":
        return WEATHER_RU.get(str(value), value)
    return value


def display_table_rows(passes: Iterable[ContactPass]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in passes:
        raw = p.flat_dict()
        rows.append({RUSSIAN_COLUMN_LABELS[key]: _format_display_value(key, raw.get(key)) for key in CSV_FIELDS})
    return rows


def write_csv(passes: Iterable[ContactPass], path: str | Path, russian_headers: bool = True) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    passes_list = list(passes)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        if russian_headers:
            writer = csv.DictWriter(f, fieldnames=[RUSSIAN_COLUMN_LABELS[key] for key in CSV_FIELDS])
            writer.writeheader()
            for row in display_table_rows(passes_list):
                writer.writerow(row)
        else:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for p in passes_list:
                d = p.flat_dict()
                writer.writerow({key: d.get(key) for key in CSV_FIELDS})
    return path


def write_json(passes: Iterable[ContactPass], path: str | Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    data = [asdict(p) for p in passes]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_rich_table(passes: list[ContactPass], show_unscheduled: bool = True) -> None:
    rows = [p for p in passes if show_unscheduled or p.scheduled]
    if not rows:
        print("Подходящих сеансов не найдено.")
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Расписание сеансов связи")
        for col in ["Статус", "Рек.", "Класс", "Индекс", "Спутник", "Станция", "Начало UTC", "Длит., мин", "Макс. угол", "Погода", "Передано, МБ"]:
            table.add_column(col)
        for p in rows:
            status = "✓" if p.scheduled else "×"
            rec = "★" if p.recommended else ""
            table.add_row(
                status,
                rec,
                p.quality_class,
                f"{p.quality_score:.1f}",
                p.satellite,
                p.station,
                p.start_utc,
                f"{p.duration_min:.2f}",
                f"{p.max_elevation_deg:.1f}°",
                WEATHER_RU.get(p.weather_condition, p.weather_condition),
                "" if p.transmitted_mb is None else f"{p.transmitted_mb:.1f}",
            )
        Console().print(table)
        return
    except Exception:
        pass

    headers = ["Статус", "Рек.", "Класс", "Индекс", "Спутник", "Станция", "Начало UTC", "Длит., мин", "Макс. угол", "Погода"]
    body = []
    for p in rows:
        body.append([
            "да" if p.scheduled else "нет",
            "да" if p.recommended else "нет",
            p.quality_class,
            f"{p.quality_score:.1f}",
            p.satellite,
            p.station,
            p.start_utc,
            f"{p.duration_min:.2f}",
            f"{p.max_elevation_deg:.1f}°",
            WEATHER_RU.get(p.weather_condition, p.weather_condition),
        ])
    widths = [len(h) for h in headers]
    for row in body:
        widths = [max(w, len(str(c))) for w, c in zip(widths, row)]
    print(" | ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in body:
        print(" | ".join(str(c).ljust(w) for c, w in zip(row, widths)))


def plot_passes(passes: Iterable[ContactPass], plot_dir: str | Path, only_scheduled: bool = False) -> list[Path]:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    plot_dir = ensure_dir(plot_dir)
    outputs: list[Path] = []
    selected = [p for p in passes if (p.scheduled or not only_scheduled)]
    for idx, p in enumerate(selected, start=1):
        if not p.profile:
            continue
        times = [parse_utc_datetime(point.utc) for point in p.profile]
        elevations = [point.elevation_deg for point in p.profile]
        required = [point.required_elevation_deg for point in p.profile]
        if len(times) < 2:
            continue

        fig, ax = plt.subplots(figsize=(10.5, 4.8))
        marker = "o" if len(times) <= 45 else None
        ax.plot(times, elevations, marker=marker, linewidth=1.8, label="угол места спутника")
        ax.plot(times, required, linestyle="--", linewidth=1.2, label="минимально допустимый угол")
        try:
            max_time = parse_utc_datetime(p.max_elevation_time_utc)
            ax.axvline(max_time, linewidth=1.0, linestyle=":", label="максимум")
        except Exception:
            pass
        ax.set_title(f"{p.satellite} / {p.station}\nначало {p.start_utc}, макс. угол {p.max_elevation_deg}°")
        ax.set_xlabel("Время UTC")
        ax.set_ylabel("Угол места, градусы")
        ymin = min(min(elevations), min(required), 0.0) - 2.0
        ymax = max(max(elevations), max(required), p.max_elevation_deg, 10.0) + 3.0
        ax.set_ylim(ymin, ymax)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=UTC))
        fig.autofmt_xdate()
        fig.tight_layout()

        filename = f"{idx:03d}_{safe_filename(p.station)}_{safe_filename(p.satellite)}_{safe_filename(p.start_utc)}.png"
        out = plot_dir / filename
        fig.savefig(out, dpi=150)
        plt.close(fig)
        outputs.append(out)
    return outputs


def plot_station_utilization(passes: Iterable[ContactPass], path: str | Path, only_recommended: bool = False) -> Path:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")

    passes_list = sorted(list(passes), key=lambda p: (p.start_dt(), p.station, p.satellite))
    items = [p for p in passes_list if p.scheduled and (p.recommended or not only_recommended)]
    stations = sorted({p.station for p in items}) or sorted({p.station for p in passes_list}) or ["Нет сеансов"]

    fig_height = max(4.8, 1.05 * len(stations) + 3.0)
    fig, ax = plt.subplots(figsize=(14.5, fig_height))
    y_map = {station: idx for idx, station in enumerate(stations)}

    scheduled_color = "#2E86AB"
    recommended_color = "#F28E2B"
    skipped_color = "#9E9E9E"

    if items:
        starts = [p.start_dt() for p in items]
        ends = [p.end_dt() for p in items]
        min_dt = min(starts)
        max_dt = max(ends)
        total_span_sec = max((max_dt - min_dt).total_seconds(), 60.0)

        # Расширяем только отображение коротких сеансов.
        min_visible_sec = min(max(total_span_sec * 0.012, 8 * 60.0), 45 * 60.0)

        # Разводим близкие события по вертикали.
        station_time_buckets: dict[tuple[str, str], int] = {}

        for p in items:
            start_dt = p.start_dt()
            end_dt = p.end_dt()
            real_duration_sec = max((end_dt - start_dt).total_seconds(), 60.0)
            visible_duration_sec = max(real_duration_sec, min_visible_sec)
            mid_dt_num = (mdates.date2num(start_dt) + mdates.date2num(end_dt)) / 2.0
            visible_width_days = visible_duration_sec / 86400.0
            left_num = mid_dt_num - visible_width_days / 2.0
            right_num = mid_dt_num + visible_width_days / 2.0

            y_base = y_map[p.station]
            bucket = start_dt.strftime("%Y-%m-%d %H")
            offset_idx = station_time_buckets.get((p.station, bucket), 0)
            station_time_buckets[(p.station, bucket)] = offset_idx + 1
            y = y_base + ((offset_idx % 3) - 1) * 0.11

            is_rec = bool(p.recommended)
            color = recommended_color if is_rec else scheduled_color
            marker = "*" if is_rec else "o"
            marker_size = 10 if is_rec else 7

            ax.plot(
                [left_num, right_num],
                [y, y],
                linewidth=7.0,
                solid_capstyle="round",
                color=color,
                alpha=0.55,
                zorder=2,
            )
            # Штрихи показывают реальные границы сеанса.
            ax.vlines(
                [mdates.date2num(start_dt), mdates.date2num(end_dt)],
                y - 0.10,
                y + 0.10,
                color=color,
                linewidth=1.0,
                alpha=0.75,
                zorder=3,
            )
            ax.plot(
                [mid_dt_num],
                [y],
                marker=marker,
                markersize=marker_size,
                markerfacecolor=color,
                markeredgecolor="black",
                markeredgewidth=0.55,
                linestyle="None",
                zorder=4,
            )

        for station in stations:
            station_items = [p for p in items if p.station == station]
            recommended_count = sum(1 for p in station_items if p.recommended)
            scheduled_count = len(station_items)
            total_minutes = sum(p.duration_min for p in station_items)
            ax.text(
                1.012,
                y_map[station],
                f"{scheduled_count} сеанс.; {recommended_count} рек.; {total_minutes:.0f} мин",
                transform=ax.get_yaxis_transform(),
                va="center",
                ha="left",
                fontsize=8.5,
                clip_on=False,
            )

        legend_items = [
            Line2D([0], [0], color=scheduled_color, linewidth=7, marker="o", markersize=7,
                   markerfacecolor=scheduled_color, markeredgecolor="black", label="запланированный сеанс"),
            Line2D([0], [0], color=recommended_color, linewidth=7, marker="*", markersize=11,
                   markerfacecolor=recommended_color, markeredgecolor="black", label="рекомендованный сеанс"),
            Line2D([0], [0], color=scheduled_color, linewidth=0, marker="|", markersize=13,
                   markeredgewidth=1.2, label="точное начало/конец"),
        ]
        fig.legend(
            handles=legend_items,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.91),
            ncol=3,
            frameon=False,
            fontsize=9,
        )
    elif passes_list:
        min_dt = min(p.start_dt() for p in passes_list)
        max_dt = max(p.end_dt() for p in passes_list)
        ax.text(
            0.5,
            0.5,
            "Нет запланированных сеансов\n(возможно, они отфильтрованы или запрещены погодой)",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
    else:
        from datetime import datetime, timedelta
        min_dt = datetime.now(tz=UTC)
        max_dt = min_dt + timedelta(hours=1)
        ax.text(0.5, 0.5, "Нет данных для отображения", transform=ax.transAxes, ha="center", va="center")

    pad = max((max_dt - min_dt).total_seconds() * 0.06, 35 * 60)
    ax.set_xlim(mdates.date2num(min_dt) - pad / 86400.0, mdates.date2num(max_dt) + pad / 86400.0)
    ax.set_yticks(list(y_map.values()), list(y_map.keys()))
    ax.set_ylim(-0.65, max(0.65, len(stations) - 0.35))
    ax.set_xlabel("Время UTC")
    ax.set_ylabel("Наземная станция")
    ax.grid(True, axis="x", alpha=0.25)
    ax.grid(True, axis="y", alpha=0.08)
    ax.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=UTC))
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")

    fig.suptitle("Загрузка наземных станций по времени", fontsize=14, y=0.985)
    fig.text(
        0.01,
        0.018,
        "Полосы показывают интервалы связи; для очень коротких сеансов задана минимальная видимая ширина. Точные начало и конец отмечены штрихами.",
        fontsize=8.5,
        color="dimgray",
    )
    fig.subplots_adjust(left=0.13, right=0.80, bottom=0.18, top=0.76)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path

def _coverage_radius_km(min_elevation_deg: float, satellite_altitude_km: float = 550.0) -> float:
    """Приближённый радиус зоны видимости станции для LEO.
    """
    earth_radius_km = 6371.0
    elev = math.radians(max(0.0, min(89.0, min_elevation_deg)))
    ratio = earth_radius_km / (earth_radius_km + satellite_altitude_km)
    central = max(0.0, math.acos(min(1.0, ratio * math.cos(elev))) - elev)
    return earth_radius_km * central


def _normalize_lon(lon: float) -> float:
    """Нормализует долготу в диапазон [-180; 180]."""
    return ((float(lon) + 180.0) % 360.0) - 180.0


def _split_antimeridian(coords: list[list[float]]) -> list[list[list[float]]]:
    """Разбивает линию на сегменты, чтобы трек не протягивался через всю карту.
    """
    segments: list[list[list[float]]] = []
    current: list[list[float]] = []
    prev_lon: float | None = None
    for item in coords:
        if len(item) < 2:
            continue
        lat, lon = float(item[0]), _normalize_lon(float(item[1]))
        if not (-90.0 <= lat <= 90.0) or not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if prev_lon is not None and abs(lon - prev_lon) > 180.0:
            if len(current) >= 2:
                segments.append(current)
            current = []
        current.append([lat, lon])
        prev_lon = lon
    if len(current) >= 2:
        segments.append(current)
    return segments


def _coverage_boundary_points(lat_deg: float, lon_deg: float, radius_km: float, points: int = 181) -> list[list[float]]:
    """Строит границу зоны покрытия как окружность на сфере."""
    earth_radius_km = 6371.0
    angular = max(0.0, float(radius_km)) / earth_radius_km
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    result: list[list[float]] = []
    for i in range(points + 1):
        bearing = math.radians(360.0 * i / points)
        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular)
            + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular) * math.cos(lat1),
            math.cos(angular) - math.sin(lat1) * math.sin(lat2),
        )
        result.append([math.degrees(lat2), _normalize_lon(math.degrees(lon2))])
    return result


def write_map_html(
    passes: Iterable[ContactPass],
    path: str | Path,
    only_scheduled: bool = False,
    stations: Iterable[GroundStation] | None = None,
    show_coverage: bool = True,
    show_track_markers: bool = True,
) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    import folium

    passes_list = [p for p in passes if (p.scheduled or not only_scheduled)]
    station_records: dict[str, tuple[float, float, float]] = {}
    for st in stations or []:
        station_records[st.name] = (st.lat, st.lon, st.min_elevation_deg)
    for p in passes_list:
        station_records.setdefault(p.station, (p.station_lat, p.station_lon, 10.0))

    if station_records:
        center_lat = sum(v[0] for v in station_records.values()) / len(station_records)
        center_lon = sum(v[1] for v in station_records.values()) / len(station_records)
    elif passes_list:
        center_lat = sum(p.station_lat for p in passes_list) / len(passes_list)
        center_lon = sum(p.station_lon for p in passes_list) / len(passes_list)
    else:
        center_lat, center_lon = 0.0, 0.0

    m = folium.Map(location=[center_lat, center_lon], zoom_start=3, control_scale=True, tiles="OpenStreetMap")

    fg_stations = folium.FeatureGroup(name="Наземные станции", show=True)
    fg_coverage = folium.FeatureGroup(name="Зоны видимости", show=True)
    fg_tracks = folium.FeatureGroup(name="Трассы спутников", show=True)
    fg_points = folium.FeatureGroup(name="Ключевые точки пролётов", show=False)

    for name, (lat, lon, min_el) in station_records.items():
        popup = f"Наземная станция: {html.escape(name)}<br>Мин. угол: {min_el:.1f}°"
        folium.Marker([lat, lon], tooltip=name, popup=popup).add_to(fg_stations)
        if show_coverage:
            radius_m = _coverage_radius_km(min_el) * 1000.0
            folium.Circle(
                [lat, lon],
                radius=radius_m,
                tooltip=f"Зона видимости {name}",
                popup=f"Приближённая зона видимости при угле > {min_el:.1f}°",
                fill=True,
                fill_opacity=0.08,
                weight=1,
            ).add_to(fg_coverage)

    for p in passes_list:
        coords = [
            [pt.sub_lat_deg, pt.sub_lon_deg]
            for pt in p.profile
            if pt.sub_lat_deg is not None and pt.sub_lon_deg is not None
        ]
        segments = _split_antimeridian(coords)
        if segments:
            status = "запланирован" if p.scheduled else "пропущен"
            rec = "да" if p.recommended else "нет"
            popup = (
                f"{html.escape(p.satellite)} / {html.escape(p.station)}<br>"
                f"{p.start_utc} — {p.end_utc}<br>"
                f"Макс. угол: {p.max_elevation_deg}°<br>"
                f"Индекс качества: {p.quality_score}/100<br>"
                f"Класс: {p.quality_class}<br>"
                f"Рекомендован: {rec}<br>"
                f"Статус: {status}"
            )
            color = "green" if p.scheduled and p.recommended else "blue" if p.scheduled else "gray"
            for segment in segments:
                folium.PolyLine(
                    segment,
                    tooltip=f"{p.satellite}: {p.start_utc}",
                    popup=popup,
                    color=color,
                    weight=3,
                    opacity=0.8,
                ).add_to(fg_tracks)

            if show_track_markers and p.profile:
                profile_points = [pt for pt in p.profile if pt.sub_lat_deg is not None and pt.sub_lon_deg is not None]
                if profile_points:
                    max_point = max(profile_points, key=lambda pt: pt.elevation_deg)
                    folium.CircleMarker(
                        [max_point.sub_lat_deg, _normalize_lon(max_point.sub_lon_deg)],
                        radius=4,
                        tooltip=f"Максимальный угол: {p.max_elevation_deg}°",
                        popup=popup,
                        fill=True,
                    ).add_to(fg_points)

    fg_stations.add_to(m)
    fg_coverage.add_to(m)
    fg_tracks.add_to(m)
    fg_points.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(path))
    return path



# Упрощённая подложка карты, если Basemap недоступен.
_WORLD_FALLBACK_POLYGONS: list[list[tuple[float, float]]] = [
    [(-168, 72), (-145, 70), (-126, 58), (-124, 45), (-117, 32), (-103, 22), (-90, 17), (-82, 25), (-76, 36), (-66, 45), (-55, 52), (-60, 62), (-96, 72), (-130, 73), (-168, 72)],
    [(-73, 83), (-20, 82), (-18, 60), (-43, 58), (-60, 70), (-73, 83)],
    [(-82, 12), (-70, 9), (-60, 2), (-49, -7), (-43, -20), (-51, -38), (-66, -55), (-75, -45), (-81, -20), (-82, 12)],
    [(-12, 36), (5, 43), (30, 42), (45, 35), (60, 28), (78, 8), (105, 4), (123, 18), (145, 45), (180, 55), (180, 70), (130, 72), (95, 76), (55, 70), (28, 72), (4, 60), (-10, 50), (-12, 36)],
    [(-18, 36), (7, 37), (34, 31), (51, 12), (46, -25), (31, -35), (15, -34), (0, -22), (-10, 0), (-18, 36)],
    [(37, 30), (48, 30), (56, 22), (54, 12), (44, 14), (37, 30)],
    [(68, 24), (89, 23), (92, 8), (80, 7), (68, 24)],
    [(112, -10), (154, -11), (154, -30), (140, -43), (116, -36), (112, -10)],
    [(166, -35), (179, -38), (174, -47), (166, -35)],
    [(-180, -62), (-120, -66), (-60, -64), (0, -68), (60, -65), (120, -67), (180, -62), (180, -90), (-180, -90), (-180, -62)],
]


def _collect_static_map_points(
    passes_list: list[ContactPass],
    station_records: dict[str, tuple[float, float, float]],
    show_coverage: bool,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for lat, lon, min_el in station_records.values():
        if math.isfinite(lat) and math.isfinite(lon):
            points.append((_normalize_lon(lon), lat))
        if show_coverage:
            for boundary_point in _coverage_boundary_points(lat, lon, _coverage_radius_km(min_el), points=96):
                b_lat, b_lon = boundary_point
                if math.isfinite(b_lat) and math.isfinite(b_lon):
                    points.append((_normalize_lon(b_lon), b_lat))
    for cp in passes_list:
        for pt in cp.profile:
            if pt.sub_lat_deg is not None and pt.sub_lon_deg is not None:
                lat = float(pt.sub_lat_deg)
                lon = _normalize_lon(float(pt.sub_lon_deg))
                if -90.0 <= lat <= 90.0 and math.isfinite(lat) and math.isfinite(lon):
                    points.append((lon, lat))
    return points


def _static_map_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    if not points:
        return -180.0, 180.0, -90.0, 90.0
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]

    # При пересечении 180-го меридиана показываем весь мир.
    if max(lons) - min(lons) > 300:
        lon_min, lon_max = -180.0, 180.0
    else:
        lon_min, lon_max = min(lons), max(lons)
        lon_span = max(lon_max - lon_min, 1.0)
        lon_pad = max(lon_span * 0.14, 5.0)
        lon_min = max(-180.0, lon_min - lon_pad)
        lon_max = min(180.0, lon_max + lon_pad)
        if lon_max - lon_min < 18.0:
            mid = (lon_min + lon_max) / 2.0
            lon_min = max(-180.0, mid - 9.0)
            lon_max = min(180.0, mid + 9.0)

    lat_min, lat_max = min(lats), max(lats)
    lat_span = max(lat_max - lat_min, 1.0)
    lat_pad = max(lat_span * 0.18, 5.0)
    lat_min = max(-90.0, lat_min - lat_pad)
    lat_max = min(90.0, lat_max + lat_pad)
    if lat_max - lat_min < 16.0:
        mid = (lat_min + lat_max) / 2.0
        lat_min = max(-90.0, mid - 8.0)
        lat_max = min(90.0, mid + 8.0)
    return lon_min, lon_max, lat_min, lat_max


def _draw_fallback_world_background(ax: Any, bounds: tuple[float, float, float, float]) -> None:
    from matplotlib.patches import Polygon

    lon_min, lon_max, lat_min, lat_max = bounds
    ax.set_facecolor('#eaf4ff')
    for poly in _WORLD_FALLBACK_POLYGONS:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        if max(xs) < lon_min or min(xs) > lon_max or max(ys) < lat_min or min(ys) > lat_max:
            continue
        ax.add_patch(
            Polygon(
                poly,
                closed=True,
                facecolor='#f2efe6',
                edgecolor='#8a8a8a',
                linewidth=0.5,
                alpha=0.95,
                zorder=0,
            )
        )


def _draw_world_background(ax: Any, bounds: tuple[float, float, float, float]) -> None:
    """Рисует географическую подложку для статической карты.
    """
    lon_min, lon_max, lat_min, lat_max = bounds
    try:
        from mpl_toolkits.basemap import Basemap

        basemap = Basemap(
            projection='cyl',
            llcrnrlon=lon_min,
            urcrnrlon=lon_max,
            llcrnrlat=lat_min,
            urcrnrlat=lat_max,
            resolution='l',
            ax=ax,
        )
        basemap.drawmapboundary(fill_color='#eaf4ff', linewidth=0.6)
        basemap.fillcontinents(color='#f2efe6', lake_color='#eaf4ff', zorder=0)
        basemap.drawcoastlines(color='#5f6b73', linewidth=0.45, zorder=1)
        basemap.drawcountries(color='#9aa3aa', linewidth=0.30, zorder=1)
    except Exception:
        _draw_fallback_world_background(ax, bounds)


def plot_static_ground_tracks(
    passes: Iterable[ContactPass],
    path: str | Path,
    stations: Iterable[GroundStation] | None = None,
    only_scheduled: bool = False,
    show_coverage: bool = True,
    zoom_to_data: bool = True,
) -> Path:
    """Создаёт статическую PNG-карту для HTML/PDF-отчётов.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator

    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    passes_list = [p for p in passes if (p.scheduled or not only_scheduled)]
    station_records: dict[str, tuple[float, float, float]] = {}
    for st in stations or []:
        station_records[st.name] = (st.lat, st.lon, st.min_elevation_deg)
    for p in passes_list:
        station_records.setdefault(p.station, (p.station_lat, p.station_lon, 10.0))

    map_points = _collect_static_map_points(passes_list, station_records, show_coverage)
    bounds = _static_map_bounds(map_points) if zoom_to_data else (-180.0, 180.0, -90.0, 90.0)
    lon_min, lon_max, lat_min, lat_max = bounds
    lon_span = max(lon_max - lon_min, 1.0)
    lat_span = max(lat_max - lat_min, 1.0)
    fig_width = 12.5
    fig_height = min(8.2, max(5.3, fig_width * lat_span / max(lon_span, 20.0) * 0.62))

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    _draw_world_background(ax, bounds)
    ax.set_title("Статическая карта трасс и зон видимости", pad=12)
    ax.set_xlabel("Долгота, °")
    ax.set_ylabel("Широта, °")
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.grid(True, alpha=0.28, linewidth=0.6)

    station_color = '#d62728'
    coverage_color = '#1f77b4'
    track_color = '#2ca02c'
    max_color = '#ff7f0e'

    for name, (lat, lon, min_el) in station_records.items():
        lon_norm = _normalize_lon(lon)
        ax.scatter([lon_norm], [lat], marker="^", s=90, color=station_color, edgecolor='black', linewidth=0.4, zorder=6)
        ax.annotate(
            name[:28],
            xy=(lon_norm, lat),
            xytext=(7, 7),
            textcoords='offset points',
            fontsize=8.5,
            bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.75),
            zorder=7,
        )
        if show_coverage:
            boundary = _coverage_boundary_points(lat, lon_norm, _coverage_radius_km(min_el), points=181)
            for segment in _split_antimeridian(boundary):
                xs = [pt[1] for pt in segment]
                ys = [pt[0] for pt in segment]
                ax.plot(xs, ys, linewidth=1.1, color=coverage_color, alpha=0.45, zorder=3)

    for cp in passes_list:
        coords = [
            [pt.sub_lat_deg, pt.sub_lon_deg]
            for pt in cp.profile
            if pt.sub_lat_deg is not None and pt.sub_lon_deg is not None
        ]
        for segment in _split_antimeridian(coords):
            xs = [pt[1] for pt in segment]
            ys = [pt[0] for pt in segment]
            ax.plot(xs, ys, linewidth=1.8, color=track_color if cp.scheduled else '#7f7f7f', alpha=0.88, zorder=4)
        if cp.profile:
            profile_points = [pt for pt in cp.profile if pt.sub_lat_deg is not None and pt.sub_lon_deg is not None]
            if profile_points:
                max_point = max(profile_points, key=lambda pt: pt.elevation_deg)
                ax.scatter(
                    [_normalize_lon(max_point.sub_lon_deg)],
                    [max_point.sub_lat_deg],
                    s=26,
                    color=max_color,
                    edgecolor='black',
                    linewidth=0.3,
                    zorder=5,
                )

    if not passes_list and not station_records:
        ax.text(0.5, 0.5, "Нет данных для отображения", transform=ax.transAxes, ha="center", va="center")

    legend_items = [
        Line2D([0], [0], marker='^', color='none', markerfacecolor=station_color, markeredgecolor='black', markersize=8, label='наземная станция'),
        Line2D([0], [0], color=coverage_color, linewidth=1.4, label='приближённая зона видимости'),
        Line2D([0], [0], color=track_color, linewidth=2.0, label='трасса спутника'),
        Line2D([0], [0], marker='o', color='none', markerfacecolor=max_color, markeredgecolor='black', markersize=6, label='точка максимального угла'),
    ]
    ax.legend(handles=legend_items, loc='lower left', ncol=2, frameon=True, fontsize=8.3, framealpha=0.88)
    fig.text(
        0.01,
        0.01,
        "Примечание: зона видимости показана приближённо; точный расчёт сеансов находится в таблице.",
        fontsize=8,
        color='dimgray',
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path

def write_ics(passes: Iterable[ContactPass], path: str | Path, only_scheduled: bool = True, only_recommended: bool = False) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//sat-session-planner//RU"]
    for p in passes:
        if only_scheduled and not p.scheduled:
            continue
        if only_recommended and not p.recommended:
            continue
        uid = f"{p.norad_id}-{safe_filename(p.station)}-{safe_filename(p.start_utc)}@sat-session-planner"
        summary = f"{p.satellite} над {p.station} ({p.quality_class}, {p.quality_score}/100)"
        desc = (
            f"Максимальный угол места: {p.max_elevation_deg} град.\n"
            f"Длительность: {p.duration_min} мин.\n"
            f"Индекс качества: {p.quality_score}/100\n"
            f"Погода: {WEATHER_RU.get(p.weather_condition, p.weather_condition)}\n"
            f"Передано, МБ: {p.transmitted_mb if p.transmitted_mb is not None else ''}\n"
        )
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{escape_ics(uid)}",
            f"DTSTAMP:{ics_dt(parse_utc_datetime(p.start_utc))}",
            f"DTSTART:{ics_dt(parse_utc_datetime(p.start_utc))}",
            f"DTEND:{ics_dt(parse_utc_datetime(p.end_utc))}",
            f"SUMMARY:{escape_ics(summary)}",
            f"DESCRIPTION:{escape_ics(desc)}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def build_summary(passes: list[ContactPass]) -> dict[str, object]:
    scheduled = [p for p in passes if p.scheduled]
    recommended = [p for p in scheduled if p.recommended]
    return {
        "total": len(passes),
        "scheduled": len(scheduled),
        "recommended": len(recommended),
        "skipped": len(passes) - len(scheduled),
        "total_duration_min": round(sum(p.duration_min for p in scheduled), 2),
        "recommended_duration_min": round(sum(p.duration_min for p in recommended), 2),
        "total_transmitted_mb": round(sum(p.transmitted_mb or 0 for p in scheduled), 2),
        "recommended_transmitted_mb": round(sum(p.transmitted_mb or 0 for p in recommended), 2),
        "avg_quality": round(sum(p.quality_score for p in scheduled) / len(scheduled), 2) if scheduled else 0,
        "by_class": {cls: sum(1 for p in scheduled if p.quality_class == cls) for cls in ["A", "B", "C"]},
        "satellites": sorted({p.satellite for p in passes}),
        "stations": sorted({p.station for p in passes}),
    }


def scenario_summary_row(name: str, passes: list[ContactPass]) -> dict[str, Any]:
    summary = build_summary(passes)
    return {
        "Сценарий": name,
        "Всего сеансов": summary["total"],
        "Запланировано": summary["scheduled"],
        "Рекомендовано": summary["recommended"],
        "Минут связи": summary["total_duration_min"],
        "Передано, МБ": summary["total_transmitted_mb"],
        "Средний индекс": summary["avg_quality"],
        "Класс A": summary["by_class"].get("A", 0),
        "Класс B": summary["by_class"].get("B", 0),
        "Класс C": summary["by_class"].get("C", 0),
    }


def write_scenario_comparison_csv(rows: list[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    fieldnames = list(rows[0].keys()) if rows else ["Сценарий"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _path_to_data_uri(path: str | Path) -> str:
    p = Path(path)
    mime, _ = mimetypes.guess_type(p.name)
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _embedded_map_html(map_path: str | Path | None) -> str:
    if not map_path:
        return "<p>Карта не создавалась.</p>"
    try:
        map_doc = Path(map_path).read_text(encoding="utf-8")
    except Exception as exc:
        return f"<p>Карту не удалось встроить: {html.escape(str(exc))}</p>"
    srcdoc = html.escape(map_doc, quote=True)
    return (
        '<iframe class="map-frame" title="Интерактивная карта" '
        f'srcdoc="{srcdoc}"></iframe>'
        '<p class="small">Карта встроена прямо в отчёт. Синие/зелёные линии - трасса спутника, круги - приближённые зоны видимости станций.</p>'
    )


def _embedded_plots_html(plot_paths: list[Path]) -> str:
    figures: list[str] = []
    for p in plot_paths[:40]:
        try:
            src = _path_to_data_uri(p)
        except Exception:
            continue
        figures.append(f'<figure><img src="{src}" alt="График"><figcaption>{html.escape(Path(p).name)}</figcaption></figure>')
    return "".join(figures) if figures else "<p>Графики не создавались.</p>"


def explanation_html() -> str:
    return """
<section class="explain">
<h2>Как программа выполняет расчёт</h2>
<ol>
  <li>Загружает TLE - реальные орбитальные параметры спутников.</li>
  <li>Для заданного периода считает положение спутника относительно каждой станции.</li>
  <li>Находит интервалы, где угол места выше минимального порога и станция реально видит спутник.</li>
  <li>Для каждого сеанса считает длительность, максимальный и средний угол, дальность, день/ночь и условную погоду.</li>
  <li>Считает индекс качества 0-100 и класс A/B/C.</li>
  <li>Разрешает конфликты: одна станция не может принимать два спутника одновременно.</li>
  <li>Формирует рекомендованное расписание и считает, сколько данных можно передать.</li>
</ol>
<p>Индекс качества - учебная оценка. Он растёт при большом угле места, большой длительности и малой дальности, а ухудшается при плохой погоде.</p>
</section>
"""


def write_html_report(
    passes: list[ContactPass],
    path: str | Path,
    title: str = "Отчёт планировщика сеансов связи",
    plot_paths: list[Path] | None = None,
    map_path: str | Path | None = None,
    utilization_path: str | Path | None = None,
    static_map_path: str | Path | None = None,
    warnings: list[str] | None = None,
) -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    summary = build_summary(passes)
    plot_paths = plot_paths or []
    warnings = warnings or []

    rows_html = []
    for p in passes:
        status = "запланирован" if p.scheduled else "пропущен"
        rec = "да" if p.recommended else "нет"
        reason = p.conflict_reason or ""
        day_night = DAY_NIGHT_RU.get(p.day_night, p.day_night)
        weather = WEATHER_RU.get(p.weather_condition, p.weather_condition)
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{html.escape(rec)}</td>"
            f"<td>{html.escape(p.quality_class)}</td>"
            f"<td>{p.quality_score:.2f}</td>"
            f"<td>{html.escape(p.satellite)}</td>"
            f"<td>{html.escape(p.station)}</td>"
            f"<td>{html.escape(p.start_utc)}</td>"
            f"<td>{html.escape(p.end_utc)}</td>"
            f"<td>{p.duration_min:.2f}</td>"
            f"<td>{p.max_elevation_deg:.1f}°</td>"
            f"<td>{p.avg_elevation_deg:.1f}°</td>"
            f"<td>{html.escape(day_night)}</td>"
            f"<td>{html.escape(weather)}</td>"
            f"<td>{p.weather_penalty:.1f}</td>"
            f"<td>{'' if p.transmitted_mb is None else f'{p.transmitted_mb:.1f}'}</td>"
            f"<td>{'' if p.backlog_after_mb is None else f'{p.backlog_after_mb:.1f}'}</td>"
            f"<td>{html.escape(reason)}</td>"
            f"<td>{html.escape(p.recommendation_reason or '')}</td>"
            "</tr>"
        )

    plots_html = _embedded_plots_html(plot_paths)
    map_html = _embedded_map_html(map_path)
    static_map_html = _embedded_plots_html([Path(static_map_path)]) if static_map_path else "<p>Статическая карта не создавалась.</p>"
    util_html = _embedded_plots_html([Path(utilization_path)]) if utilization_path else "<p>Диаграмма занятости станции не создавалась.</p>"
    warnings_html = "".join(f"<li>{html.escape(w)}</li>" for w in warnings) or "<li>Предупреждений нет.</li>"

    doc = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; line-height: 1.45; color: #18212f; }}
h1, h2 {{ margin-top: 1.4em; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
.card {{ border: 1px solid #d8dee9; border-radius: 14px; padding: 14px; background: #f8fafc; }}
.card b {{ display: block; font-size: 1.6rem; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ border: 1px solid #d8dee9; padding: 7px 8px; vertical-align: top; }}
th {{ background: #eef2f7; position: sticky; top: 0; }}
img {{ max-width: 100%; border: 1px solid #d8dee9; border-radius: 12px; }}
figure {{ margin: 18px 0; }}
.small {{ color: #5a6675; }}
.map-frame {{ width: 100%; height: 620px; border: 1px solid #d8dee9; border-radius: 12px; }}
.warn {{ background: #fff8e1; border: 1px solid #f6d365; border-radius: 12px; padding: 12px 18px; }}
.explain {{ background: #f7fbff; border: 1px solid #dbeafe; border-radius: 12px; padding: 12px 18px; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="small">Сгенерировано программой sat-session-planner. Карта, графики и диаграмма загрузки встроены внутрь HTML-отчёта.</p>
<div class="cards">
  <div class="card"><span>Всего найдено</span><b>{summary['total']}</b></div>
  <div class="card"><span>Запланировано</span><b>{summary['scheduled']}</b></div>
  <div class="card"><span>Рекомендовано</span><b>{summary['recommended']}</b></div>
  <div class="card"><span>Пропущено</span><b>{summary['skipped']}</b></div>
  <div class="card"><span>Минут связи</span><b>{summary['total_duration_min']}</b></div>
  <div class="card"><span>Передано, МБ</span><b>{summary['total_transmitted_mb']}</b></div>
  <div class="card"><span>Средний индекс</span><b>{summary['avg_quality']}</b></div>
</div>
<h2>Предупреждения</h2>
<ul class="warn">{warnings_html}</ul>
<h2>Интерактивная карта и зоны покрытия</h2>
{map_html}
<h3>Статическая карта для просмотра без интернета и PDF-конвертации</h3>
{static_map_html}
<h2>Загрузка станций</h2>
{util_html}
<h2>Расписание</h2>
<div class="table-wrap">
<table>
<thead><tr><th>Статус</th><th>Рекомендован</th><th>Класс качества</th><th>Индекс 0-100</th><th>Спутник</th><th>Станция</th><th>Начало UTC</th><th>Конец UTC</th><th>Длительность, мин</th><th>Макс. угол</th><th>Средний угол</th><th>День/ночь</th><th>Погода</th><th>Штраф погоды</th><th>Передано, МБ</th><th>Остаток, МБ</th><th>Причина пропуска</th><th>Причина рекомендации</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</div>
<h2>Графики угла места</h2>
{plots_html}
{explanation_html()}
</body>
</html>"""
    path.write_text(doc, encoding="utf-8")
    return path


def write_scenario_comparison_html(rows: list[dict[str, Any]], path: str | Path, title: str = "Сравнение сценариев") -> Path:
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    headers = list(rows[0].keys()) if rows else ["Сценарий"]
    table_rows = []
    for row in rows:
        table_rows.append("<tr>" + "".join(f"<td>{html.escape(str(row.get(h, '')))}</td>" for h in headers) + "</tr>")
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui;margin:32px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d8dee9;padding:8px}}th{{background:#eef2f7}}</style>
</head><body><h1>{html.escape(title)}</h1><table><thead><tr>{''.join(f'<th>{html.escape(h)}</th>' for h in headers)}</tr></thead><tbody>{''.join(table_rows)}</tbody></table></body></html>"""
    path.write_text(doc, encoding="utf-8")
    return path


def _find_pdf_font() -> tuple[str, str | None]:
    """Возвращает имя шрифта ReportLab и путь к TTF-файлу.
    """
    candidates: list[str] = []

    try:
        import matplotlib

        mpl_dir = Path(matplotlib.get_data_path())
        candidates.extend([
            str(mpl_dir / "fonts" / "ttf" / "DejaVuSans.ttf"),
            str(mpl_dir / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"),
        ])
    except Exception:
        pass

    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
    ])

    for candidate in candidates:
        font_path = Path(candidate)
        if font_path.exists() and font_path.is_file():
            return "ReportFont", str(font_path)

    # Helvetica используется только как запасной вариант.
    return "Helvetica", None


def _ru_pdf_safe_text(value: Any, unicode_font_available: bool) -> str:
    """Готовит текст для PDF.
    """
    text = "" if value is None else str(value)
    if unicode_font_available:
        return text
    mapping = str.maketrans({
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E", "Ж": "Zh", "З": "Z",
        "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R",
        "С": "S", "Т": "T", "У": "U", "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch",
        "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
        "№": "N", "—": "-", "–": "-", "°": " deg",
    })
    return text.translate(mapping)


def _add_image_to_pdf_story(
    story: list[Any],
    image_path: str | Path | None,
    caption: str,
    styles: Any,
    font_name: str,
    unicode_font_available: bool,
    max_width_mm: float = 265.0,
    max_height_mm: float = 125.0,
) -> None:
    if not image_path:
        return
    p = Path(image_path)
    if not p.exists() or not p.is_file():
        return
    try:
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer

        width_px, height_px = ImageReader(str(p)).getSize()
        if width_px <= 0 or height_px <= 0:
            return
        max_w = max_width_mm * mm
        max_h = max_height_mm * mm
        scale = min(max_w / width_px, max_h / height_px)
        img = Image(str(p), width=width_px * scale, height=height_px * scale)
        block = [
            Spacer(1, 6),
            Paragraph(html.escape(_ru_pdf_safe_text(caption, unicode_font_available)), styles["Heading2"]),
            Spacer(1, 6),
            img,
            Spacer(1, 10),
        ]
        story.append(KeepTogether(block))
    except Exception:
        return


def write_pdf_report(
    passes: list[ContactPass],
    path: str | Path,
    title: str = "Отчёт планировщика сеансов связи",
    warnings: list[str] | None = None,
    plot_paths: list[Path] | None = None,
    utilization_path: str | Path | None = None,
    static_map_path: str | Path | None = None,
) -> Path:
    """Создаёт PDF-отчёт с кириллицей и ключевыми визуализациями.
    """
    path = Path(path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    plot_paths = plot_paths or []
    font_name, font_path = _find_pdf_font()
    unicode_font_available = font_path is not None
    if font_path:
        pdfmetrics.registerFont(TTFont(font_name, font_path))

    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name

    safe_title = _ru_pdf_safe_text(title, unicode_font_available)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    story: list[Any] = [Paragraph(html.escape(safe_title), styles["Title"]), Spacer(1, 6)]
    summary = build_summary(passes)
    summary_text = (
        f"Всего: {summary['total']}; запланировано: {summary['scheduled']}; "
        f"рекомендовано: {summary['recommended']}; минут связи: {summary['total_duration_min']}; "
        f"передано: {summary['total_transmitted_mb']} МБ; средний индекс: {summary['avg_quality']}"
    )
    story.append(Paragraph(html.escape(_ru_pdf_safe_text(summary_text, unicode_font_available)), styles["Normal"]))
    if not unicode_font_available:
        story.append(Paragraph("Unicode font was not found; Russian text was transliterated to avoid broken glyphs.", styles["Normal"]))
    for warning in warnings or []:
        story.append(Paragraph(html.escape(_ru_pdf_safe_text("Предупреждение: " + warning, unicode_font_available)), styles["Normal"]))

    _add_image_to_pdf_story(story, static_map_path, "Статическая карта трасс и зон видимости", styles, font_name, unicode_font_available)
    _add_image_to_pdf_story(story, utilization_path, "Диаграмма загрузки наземных станций", styles, font_name, unicode_font_available)
    for idx, plot_path in enumerate(plot_paths[:3], start=1):
        _add_image_to_pdf_story(story, plot_path, f"График угла места #{idx}", styles, font_name, unicode_font_available, max_height_mm=95.0)

    if static_map_path or utilization_path or plot_paths:
        story.append(PageBreak())

    headers = ["Рек.", "Класс", "Индекс", "Спутник", "Станция", "Начало UTC", "Длит.", "Макс. угол", "Погода", "МБ"]
    data = [[_ru_pdf_safe_text(h, unicode_font_available) for h in headers]]
    for p in passes[:70]:
        row = [
            "да" if p.recommended else "нет",
            p.quality_class,
            f"{p.quality_score:.1f}",
            p.satellite[:24],
            p.station[:24],
            p.start_utc.replace("T", " ").replace("Z", ""),
            f"{p.duration_min:.1f}",
            f"{p.max_elevation_deg:.1f}",
            WEATHER_RU.get(p.weather_condition, p.weather_condition),
            "" if p.transmitted_mb is None else f"{p.transmitted_mb:.1f}",
        ]
        data.append([_ru_pdf_safe_text(cell, unicode_font_available) for cell in row])

    story.append(Paragraph(html.escape(_ru_pdf_safe_text("Таблица сеансов", unicode_font_available)), styles["Heading2"]))
    col_widths = [11 * mm, 13 * mm, 16 * mm, 38 * mm, 42 * mm, 42 * mm, 16 * mm, 22 * mm, 24 * mm, 18 * mm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    if len(passes) > 70:
        story.append(Spacer(1, 8))
        msg = f"В PDF показаны первые 70 строк из {len(passes)}. Полные данные см. в CSV/HTML."
        story.append(Paragraph(html.escape(_ru_pdf_safe_text(msg, unicode_font_available)), styles["Normal"]))
    doc.build(story)
    return path
