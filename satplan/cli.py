from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from .config import deep_merge_configs, load_config, parse_station_arg, satellite_requests_from_config, stations_from_config, stations_from_csv
from .horizon import load_horizon_mask
from .models import GroundStation, SatelliteRequest, iso_utc, parse_utc_datetime
from .outputs import plot_passes, plot_static_ground_tracks, plot_station_utilization, print_rich_table, write_csv, write_html_report, write_ics, write_json, write_map_html, write_pdf_report, write_scenario_comparison_csv, write_scenario_comparison_html
from .presets import PRESETS, get_preset_config, preset_keys
from .tle import DEFAULT_TLE_CACHE, DEFAULT_TLE_URL, load_tle_entries, search_satellites, select_tle_entries, tle_age_warnings, update_tle_cache
from .utils import ensure_dir


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Расширенный планировщик сеансов связи LEO-спутников с наземными станциями.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", help="YAML-конфигурация проекта")
    p.add_argument("--preset", choices=preset_keys(), help="Предзагруженный конфиг/сценарий")
    p.add_argument("--list-presets", action="store_true", help="Показать доступные предзагруженные конфиги и выйти")
    p.add_argument("--compare-presets", help="Сравнить несколько пресетов через запятую, например iss_moscow,iss_multi_station")
    p.add_argument("--tle", help="URL или путь к TLE-файлу")
    p.add_argument("--update-tle", action="store_true", help="Скачать/обновить TLE в локальный кэш и использовать его")
    p.add_argument("--use-tle-cache", action="store_true", help="Использовать локальный кэш TLE, если он существует")
    p.add_argument("--tle-cache", default=DEFAULT_TLE_CACHE, help="Путь к локальному TLE-кэшу")
    p.add_argument("--sat", action="append", help="Имя/подстрока имени спутника. Можно указать несколько раз")
    p.add_argument("--norad-id", action="append", help="NORAD ID спутника. Можно указать несколько раз")
    p.add_argument("--list-satellites", action="store_true", help="Показать спутники из TLE и выйти")
    p.add_argument("--search", default="", help="Фильтр для --list-satellites")

    p.add_argument("--station", action="append", help="Станция в формате Name,lat,lon,elev[,min_elev]. Можно несколько раз")
    p.add_argument("--stations-csv", help="CSV со станциями: name,lat,lon,elevation_m,min_elevation_deg")
    p.add_argument("--station-name", default=None, help="Название станции для legacy-режима с --lat/--lon")
    p.add_argument("--lat", type=float, help="Широта станции, legacy-режим")
    p.add_argument("--lon", type=float, help="Долгота станции, legacy-режим")
    p.add_argument("--elev-m", type=float, default=0.0, help="Высота станции, legacy-режим")
    p.add_argument("--horizon-mask", help="CSV-маска горизонта для legacy/CLI-станций")
    p.add_argument("--weather", choices=["clear", "cloudy", "rain", "snow", "storm", "fog"], help="Глобальная погода для всех CLI-станций")

    p.add_argument("--start", default=None, help="Начало расчёта: ISO UTC, now")
    p.add_argument("--hours", type=float, default=None, help="Длина расчёта, часы")
    p.add_argument("--min-elev-deg", type=float, default=None, help="Базовый минимальный угол места")
    p.add_argument("--min-max-elev-deg", type=float, default=None, help="Минимальный максимальный угол пролёта")
    p.add_argument("--min-duration-min", type=float, default=None, help="Минимальная длительность сеанса")
    p.add_argument("--coarse-step-sec", type=int, default=None, help="Грубый шаг поиска")
    p.add_argument("--sample-step-sec", type=int, default=None, help="Шаг профиля пролёта")
    day = p.add_mutually_exclusive_group()
    day.add_argument("--only-day", action="store_true", help="Оставить только дневные пролёты")
    day.add_argument("--only-night", action="store_true", help="Оставить только ночные пролёты")

    p.add_argument("--no-conflict-resolution", action="store_true", help="Не решать конфликты одной станции")
    p.add_argument("--drop-unscheduled", action="store_true", help="Не сохранять пропущенные из-за конфликтов сеансы")
    p.add_argument("--max-passes", type=int, default=None, help="Ограничить число строк после планирования")
    p.add_argument("--recommend-mode", choices=["all", "top_n", "best_per_satellite", "quality"], default=None, help="Режим рекомендованного расписания")
    p.add_argument("--max-recommended", type=int, default=None, help="Сколько лучших сеансов рекомендовать в режиме top_n")
    p.add_argument("--min-recommend-class", choices=["A", "B", "C"], default=None, help="Минимальный класс для режима quality")

    p.add_argument("--capacity-mb-per-pass", type=float, default=None, help="Жёсткий лимит MB за один сеанс")
    p.add_argument("--downlink-mbps", type=float, default=None, help="Скорость передачи во время сеанса, Mbit/s")
    p.add_argument("--data-generation-rate-mbps", type=float, default=None, help="Скорость накопления данных на борту, Mbit/s")
    p.add_argument("--initial-backlog-mb", type=float, default=None, help="Начальные данные на борту, MB")

    p.add_argument("--out-dir", default=None, help="Папка результатов")
    p.add_argument("--out-csv", default=None, help="CSV-расписание")
    p.add_argument("--out-json", default=None, help="JSON с профилями")
    p.add_argument("--html", default=None, help="HTML-отчёт")
    p.add_argument("--map-html", default=None, help="Интерактивная карта HTML")
    p.add_argument("--ics", default=None, help="Календарь .ics")
    p.add_argument("--pdf", default=None, help="PDF-отчёт")
    p.add_argument("--utilization-png", default=None, help="PNG-диаграмма загрузки станций")
    p.add_argument("--db", default=None, help="SQLite-база для сохранения истории расчётов")
    p.add_argument("--list-runs", action="store_true", help="Показать последние расчёты из SQLite-базы")
    p.add_argument("--plot-dir", default=None, help="Папка PNG-графиков")
    p.add_argument("--no-plots", action="store_true", help="Не строить графики даже для HTML-отчёта")
    return p


def _get(config: dict, section: str, key: str, default=None):
    sec = config.get(section, {}) if isinstance(config.get(section, {}), dict) else {}
    return sec.get(key, default)


def _coalesce(*values):
    for v in values:
        if v is not None:
            return v
    return None


def build_requests(args, config: dict) -> list[SatelliteRequest]:
    requests = satellite_requests_from_config(config)
    for sat in args.sat or []:
        requests.append(SatelliteRequest(query=sat))
    for norad in args.norad_id or []:
        requests.append(SatelliteRequest(norad_id=norad))
    if not requests:
        requests.append(SatelliteRequest(query="ISS"))
    return requests


def build_stations(args, config: dict, default_min_elev: float) -> list[GroundStation]:
    stations = stations_from_config(config, default_min_elev=default_min_elev)
    if args.stations_csv:
        stations.extend(stations_from_csv(args.stations_csv, default_min_elev=default_min_elev))
    if args.station:
        for value in args.station:
            stations.append(parse_station_arg(value, default_min_elev=default_min_elev))
    if args.lat is not None and args.lon is not None:
        stations.append(
            GroundStation(
                name=args.station_name or "Ground station",
                lat=args.lat,
                lon=args.lon,
                elevation_m=args.elev_m or 0.0,
                min_elevation_deg=default_min_elev,
            )
        )
    if args.horizon_mask:
        mask = load_horizon_mask(args.horizon_mask)
        for st in stations:
            if st.horizon_mask is None:
                st.horizon_mask = mask
    if args.weather:
        for st in stations:
            st.weather_condition = args.weather
    if not stations:
        raise ValueError("Не задана ни одна станция. Используйте --station, --lat/--lon или config.yaml")
    for st in stations:
        st.validate()
    return stations


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        print("Доступные предзагруженные конфиги:")
        for key in preset_keys():
            item = PRESETS[key]
            print(f"- {key}: {item['name']} — {item['description']}")
        return 0

    if args.list_runs:
        from .database import list_runs

        db_path = args.db or "outputs/history.sqlite"
        runs = list_runs(db_path)
        if not runs:
            print("История расчётов пуста.")
        for row in runs:
            print(f"#{row['id']} {row['created_utc']} {row.get('scenario_name') or ''}: запланировано={row.get('scheduled')}, рекомендовано={row.get('recommended')}, передано={row.get('total_transmitted_mb')} МБ")
        return 0

    if args.compare_presets:
        from .scenario import compare_presets

        keys = [k.strip() for k in args.compare_presets.split(',') if k.strip()]
        _results, rows = compare_presets(keys)
        out_dir = ensure_dir(args.out_dir or "outputs/comparison")
        csv_path = write_scenario_comparison_csv(rows, Path(out_dir) / "scenario_comparison.csv")
        html_path = write_scenario_comparison_html(rows, Path(out_dir) / "scenario_comparison.html")
        print("Сравнение сценариев:")
        for row in rows:
            print(f"- {row['Сценарий']}: запланировано={row['Запланировано']}, рекомендовано={row['Рекомендовано']}, передано={row['Передано, МБ']} МБ, средний индекс={row['Средний индекс']}")
        print(f"Сохранено: {csv_path}, {html_path}")
        return 0

    preset_config = get_preset_config(args.preset) if args.preset else {}
    file_config = load_config(args.config)
    config = deep_merge_configs(preset_config, file_config)

    tle_source = args.tle or config.get("tle") or config.get("tle_source") or DEFAULT_TLE_URL
    if args.update_tle:
        cache_path = update_tle_cache(tle_source, args.tle_cache)
        print(f"TLE обновлён и сохранён в кэш: {cache_path}")
        tle_source = str(cache_path)
    entries = load_tle_entries(tle_source, use_cache=args.use_tle_cache, cache_path=args.tle_cache)

    if args.list_satellites:
        found = search_satellites(entries, args.search, limit=50)
        for e in found:
            print(f"{e.name}\tNORAD={e.norad_id}")
        print(f"Показано: {len(found)} из {len(entries)}")
        return 0

    planning_cfg = config.get("planning", {}) if isinstance(config.get("planning", {}), dict) else {}
    filters_cfg = config.get("filters", {}) if isinstance(config.get("filters", {}), dict) else {}
    data_cfg = config.get("data", {}) if isinstance(config.get("data", {}), dict) else {}
    outputs_cfg = config.get("outputs", {}) if isinstance(config.get("outputs", {}), dict) else {}

    min_elev = float(_coalesce(args.min_elev_deg, filters_cfg.get("min_elevation_deg"), planning_cfg.get("min_elevation_deg"), 10.0))
    min_duration = float(_coalesce(args.min_duration_min, filters_cfg.get("min_duration_min"), planning_cfg.get("min_duration_min"), 5.0))
    min_max_elev = _coalesce(args.min_max_elev_deg, filters_cfg.get("min_max_elevation_deg"))
    min_max_elev = float(min_max_elev) if min_max_elev is not None else None
    coarse_step = int(_coalesce(args.coarse_step_sec, planning_cfg.get("coarse_step_sec"), 60))
    sample_step = int(_coalesce(args.sample_step_sec, planning_cfg.get("sample_step_sec"), 10))

    start_raw = args.start or planning_cfg.get("start") or "now"
    hours = float(_coalesce(args.hours, planning_cfg.get("hours"), 48.0))
    start = parse_utc_datetime(start_raw)
    end = start + timedelta(hours=hours)

    day_filter = "any"
    if args.only_day or filters_cfg.get("only_day"):
        day_filter = "day"
    if args.only_night or filters_cfg.get("only_night"):
        day_filter = "night"

    requests = build_requests(args, config)
    tles = select_tle_entries(entries, requests)
    stations = build_stations(args, config, default_min_elev=min_elev)
    warnings = tle_age_warnings(tles, start)

    print(f"TLE: {tle_source}")
    print("Спутники: " + ", ".join(f"{t.name} ({t.norad_id})" for t in tles))
    print("Станции: " + ", ".join(f"{s.name} ({s.lat}, {s.lon})" for s in stations))
    print(f"Интервал: {iso_utc(start)} — {iso_utc(end)}")
    print(f"Фильтры: угол места >= {min_elev}°, длительность >= {min_duration} мин, максимальный угол >= {min_max_elev or 'любой'}, режим день/ночь={day_filter}")
    for warning in warnings:
        print(f"Предупреждение: {warning}")

    from .planning import plan_contacts

    recommend_cfg = config.get("recommendation", {}) if isinstance(config.get("recommendation", {}), dict) else {}

    passes = plan_contacts(
        tle_entries=tles,
        stations=stations,
        start=start,
        end=end,
        min_duration_min=min_duration,
        min_max_elevation_deg=min_max_elev,
        coarse_step_sec=coarse_step,
        sample_step_sec=sample_step,
        day_filter=day_filter,
        resolve_conflicts=not args.no_conflict_resolution and bool(planning_cfg.get("resolve_conflicts", True)),
        data_generation_rate_mbps=_coalesce(args.data_generation_rate_mbps, data_cfg.get("data_generation_rate_mbps")),
        downlink_rate_mbps=_coalesce(args.downlink_mbps, data_cfg.get("downlink_mbps")),
        capacity_mb_per_pass=_coalesce(args.capacity_mb_per_pass, data_cfg.get("capacity_mb_per_pass")),
        initial_backlog_mb=float(_coalesce(args.initial_backlog_mb, data_cfg.get("initial_backlog_mb"), 0.0)),
        recommendation_mode=str(_coalesce(args.recommend_mode, recommend_cfg.get("mode"), "all")),
        max_recommended=_coalesce(args.max_recommended, recommend_cfg.get("max_count")),
        min_recommend_quality_class=str(_coalesce(args.min_recommend_class, recommend_cfg.get("min_quality_class"), "C")),
    )
    if args.max_passes is not None:
        passes = passes[: args.max_passes]
    if args.drop_unscheduled:
        passes_to_save = [p for p in passes if p.scheduled]
    else:
        passes_to_save = passes

    print()
    print_rich_table(passes, show_unscheduled=not args.drop_unscheduled)

    out_dir = ensure_dir(args.out_dir or outputs_cfg.get("out_dir") or "outputs")
    csv_path = Path(args.out_csv or outputs_cfg.get("csv") or out_dir / "schedule.csv")
    json_path = Path(args.out_json or outputs_cfg.get("json") or out_dir / "schedule.json")
    html_path = args.html if args.html is not None else outputs_cfg.get("html", out_dir / "report.html")
    map_path = args.map_html if args.map_html is not None else outputs_cfg.get("map_html", out_dir / "map.html")
    ics_path = args.ics if args.ics is not None else outputs_cfg.get("ics", out_dir / "schedule.ics")
    pdf_path = args.pdf if args.pdf is not None else outputs_cfg.get("pdf", out_dir / "report.pdf")
    utilization_path = args.utilization_png if args.utilization_png is not None else outputs_cfg.get("utilization_png", out_dir / "station_utilization.png")
    static_map_path = outputs_cfg.get("static_map_png", out_dir / "static_map.png")
    db_path = args.db if args.db is not None else outputs_cfg.get("db", out_dir / "history.sqlite")
    plot_dir = args.plot_dir or outputs_cfg.get("plot_dir") or out_dir / "plots"

    saved = []
    saved.append(write_csv(passes_to_save, csv_path))
    saved.append(write_json(passes_to_save, json_path))
    map_out = write_map_html(passes_to_save, map_path, only_scheduled=args.drop_unscheduled, stations=stations) if map_path else None
    if map_out:
        saved.append(map_out)
    static_map_out = plot_static_ground_tracks(passes_to_save, static_map_path, stations=stations, only_scheduled=args.drop_unscheduled) if static_map_path else None
    if static_map_out:
        saved.append(static_map_out)
    if ics_path:
        saved.append(write_ics(passes_to_save, ics_path, only_scheduled=True))

    plot_paths = []
    if not args.no_plots:
        plot_paths = plot_passes(passes_to_save, plot_dir, only_scheduled=args.drop_unscheduled)
        saved.extend(plot_paths)
    util_out = None
    if utilization_path:
        util_out = plot_station_utilization(passes_to_save, utilization_path, only_recommended=False)
        saved.append(util_out)
    if html_path:
        saved.append(write_html_report(passes_to_save, html_path, plot_paths=plot_paths, map_path=map_out, utilization_path=util_out, static_map_path=static_map_out, warnings=warnings))
    if pdf_path:
        saved.append(write_pdf_report(passes_to_save, pdf_path, warnings=warnings, plot_paths=plot_paths, utilization_path=util_out, static_map_path=static_map_out))
    if db_path:
        from .database import save_run

        run_id = save_run(db_path, passes=passes_to_save, stations=stations, tles=tles, config=config, scenario_name=args.preset or args.config or "CLI")
        saved.append(Path(db_path))
        print(f"История сохранена в SQLite, run_id={run_id}")

    print("\nСохранено:")
    for path in saved[:20]:
        print(f"- {path}")
    if len(saved) > 20:
        print(f"... и ещё {len(saved) - 20} файлов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
