from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .config import deep_merge_configs
from .models import GroundStation, SatelliteRequest
from .outputs import (
    display_table_rows,
    explanation_html,
    plot_passes,
    plot_static_ground_tracks,
    plot_station_utilization,
    scenario_summary_row,
    write_csv,
    write_html_report,
    write_ics,
    write_json,
    write_map_html,
    write_pdf_report,
    write_scenario_comparison_csv,
    write_scenario_comparison_html,
)
from .presets import PRESETS, get_preset_config, preset_keys
from .tle import DEFAULT_TLE_CACHE, DEFAULT_TLE_URL, load_tle_entries, select_tle_entries, tle_age_warnings, update_tle_cache


def _satellites_text(config: dict) -> str:
    raw = config.get("satellites") or config.get("satellite") or [{"name": "ISS"}]
    if isinstance(raw, str):
        return raw
    lines = []
    for item in raw:
        if isinstance(item, str):
            lines.append(item)
        elif isinstance(item, dict):
            if item.get("norad_id") is not None:
                lines.append(str(item.get("norad_id")))
            else:
                lines.append(str(item.get("name") or item.get("query") or ""))
    return "\n".join([x for x in lines if x])


def _stations_df(config: dict, fallback_min_elev: float) -> pd.DataFrame:
    raw = config.get("stations") or config.get("station") or []
    if isinstance(raw, dict):
        raw = [raw]
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Название": item.get("name", "Ground station"),
                "Широта": float(item.get("lat", 55.7539)),
                "Долгота": float(item.get("lon", 37.6208)),
                "Высота, м": float(item.get("elevation_m", item.get("elev_m", 0.0))),
                "Мин. угол, °": float(item.get("min_elevation_deg", fallback_min_elev)),
                "Погода": str(item.get("weather_condition", item.get("weather", "clear"))),
            }
        )
    if not rows:
        rows.append({"Название": "University GS", "Широта": 55.7539, "Долгота": 37.6208, "Высота, м": 150.0, "Мин. угол, °": fallback_min_elev, "Погода": "clear"})
    return pd.DataFrame(rows)


def _stations_from_df(df: pd.DataFrame) -> list[GroundStation]:
    stations: list[GroundStation] = []
    for _, row in df.iterrows():
        name = str(row.get("Название", "Ground station")).strip() or "Ground station"
        stations.append(
            GroundStation(
                name=name,
                lat=float(row.get("Широта", 0.0)),
                lon=float(row.get("Долгота", 0.0)),
                elevation_m=float(row.get("Высота, м", 0.0)),
                min_elevation_deg=float(row.get("Мин. угол, °", 10.0)),
                weather_condition=str(row.get("Погода", "clear")),
            )
        )
    return stations


def _display_df(passes):
    return pd.DataFrame(display_table_rows(passes))


def _run_calculation_ui() -> None:
    with st.sidebar:
        st.header("0. Готовый сценарий")
        preset_list = preset_keys()
        preset_labels = [PRESETS[key]["name"] for key in preset_list]
        selected_label = st.selectbox("Выберите предзагруженный конфиг", preset_labels, index=0)
        selected_key = preset_list[preset_labels.index(selected_label)]
        preset_cfg = get_preset_config(selected_key)
        st.caption(PRESETS[selected_key]["description"])

        planning_cfg = preset_cfg.get("planning", {}) if isinstance(preset_cfg.get("planning", {}), dict) else {}
        filters_cfg = preset_cfg.get("filters", {}) if isinstance(preset_cfg.get("filters", {}), dict) else {}
        data_cfg = preset_cfg.get("data", {}) if isinstance(preset_cfg.get("data", {}), dict) else {}
        recommend_cfg = preset_cfg.get("recommendation", {}) if isinstance(preset_cfg.get("recommendation", {}), dict) else {}

        st.header("1. TLE и спутники")
        tle_source = st.text_input("TLE URL или файл", preset_cfg.get("tle") or preset_cfg.get("tle_source") or DEFAULT_TLE_URL, key=f"tle_{selected_key}")
        cache_path = st.text_input("Локальный кэш TLE", DEFAULT_TLE_CACHE)
        col_update, col_cache = st.columns(2)
        update_tle = col_update.button("Обновить TLE")
        use_cache = col_cache.checkbox("Использовать кэш", value=False)
        satellites_text = st.text_area("Спутники, по одному в строке: имя или NORAD ID", _satellites_text(preset_cfg), key=f"sats_{selected_key}")

        st.header("2. Наземные станции")
        min_elev_default = float(filters_cfg.get("min_elevation_deg", planning_cfg.get("min_elevation_deg", 10.0)))
        default_stations = _stations_df(preset_cfg, fallback_min_elev=min_elev_default)
        stations_df = st.data_editor(
            default_stations,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"stations_{selected_key}",
            column_config={
                "Название": st.column_config.TextColumn(required=True),
                "Широта": st.column_config.NumberColumn(min_value=-90.0, max_value=90.0, format="%.6f"),
                "Долгота": st.column_config.NumberColumn(min_value=-180.0, max_value=180.0, format="%.6f"),
                "Высота, м": st.column_config.NumberColumn(min_value=-500.0, max_value=9000.0, format="%.1f"),
                "Мин. угол, °": st.column_config.NumberColumn(min_value=0.0, max_value=89.0, format="%.1f"),
                "Погода": st.column_config.SelectboxColumn(options=["clear", "cloudy", "rain", "snow", "storm", "fog"]),
            },
        )

        st.header("3. Планирование")
        now = datetime.now(timezone.utc)
        start_date = st.date_input("Дата начала UTC", now.date())
        start_time = st.time_input("Время начала UTC", now.time().replace(microsecond=0))
        hours = st.number_input("Горизонт, часов", min_value=0.1, max_value=24 * 30.0, value=float(planning_cfg.get("hours", 48.0)), step=1.0, key=f"hours_{selected_key}")
        min_duration = st.number_input("Мин. длительность, мин", min_value=0.0, max_value=240.0, value=float(filters_cfg.get("min_duration_min", 5.0)), step=0.5, key=f"min_duration_{selected_key}")
        min_max_elev = st.number_input("Мин. максимальный угол, °", min_value=0.0, max_value=90.0, value=float(filters_cfg.get("min_max_elevation_deg", 15.0)), step=1.0, key=f"min_max_elev_{selected_key}")
        default_day_filter = "night" if filters_cfg.get("only_night") else "day" if filters_cfg.get("only_day") else "any"
        day_filter = st.selectbox(
            "День/ночь",
            ["any", "day", "night"],
            index=["any", "day", "night"].index(default_day_filter),
            format_func=lambda x: {"any": "любой", "day": "только день", "night": "только ночь"}[x],
            key=f"day_filter_{selected_key}",
        )
        resolve_conflicts = st.checkbox("Решать конфликты станции", value=bool(planning_cfg.get("resolve_conflicts", True)), key=f"resolve_{selected_key}")

        st.header("4. Передача данных")
        downlink_mbps = st.number_input("Скорость передачи, Мбит/с", min_value=0.0, value=float(data_cfg.get("downlink_mbps", 2.0)), step=0.5, key=f"downlink_{selected_key}")
        capacity_mb_per_pass = st.number_input("Лимит за сеанс, МБ", min_value=0.0, value=float(data_cfg.get("capacity_mb_per_pass", 500.0)), step=50.0, key=f"capacity_{selected_key}")
        data_generation_rate_mbps = st.number_input("Накопление на борту, Мбит/с", min_value=0.0, value=float(data_cfg.get("data_generation_rate_mbps", 0.2)), step=0.1, key=f"generation_{selected_key}")
        initial_backlog_mb = st.number_input("Начальный остаток данных, МБ", min_value=0.0, value=float(data_cfg.get("initial_backlog_mb", 0.0)), step=50.0, key=f"backlog_{selected_key}")

        st.header("5. Рекомендации")
        recommend_mode = st.selectbox(
            "Режим рекомендаций",
            ["all", "top_n", "best_per_satellite", "quality"],
            index=["all", "top_n", "best_per_satellite", "quality"].index(str(recommend_cfg.get("mode", "all"))),
            format_func=lambda x: {"all": "все запланированные", "top_n": "топ-N", "best_per_satellite": "лучший на спутник", "quality": "по классу качества"}[x],
        )
        max_recommended = st.number_input("N для топ-N", min_value=1, max_value=100, value=int(recommend_cfg.get("max_count", 5)), step=1)
        min_recommend_class = st.selectbox("Мин. класс", ["A", "B", "C"], index=["A", "B", "C"].index(str(recommend_cfg.get("min_quality_class", "C"))))

        st.header("6. История")
        db_path = st.text_input("SQLite база", "outputs/history.sqlite")
        save_to_db = st.checkbox("Сохранять расчёт в базу", value=True)
        run = st.button("Рассчитать", type="primary")

    if update_tle:
        try:
            cache = update_tle_cache(tle_source, cache_path)
            st.success(f"TLE обновлён: {cache}")
        except Exception as exc:
            st.error(f"Не удалось обновить TLE: {exc}")

    if not run:
        st.info("Выберите сценарий или измените параметры слева, затем нажмите «Рассчитать».")
        st.markdown("В текущей версии добавлены база SQLite, сравнение сценариев, рекомендации, карта покрытия, PDF, проверка входных данных и улучшенная визуализация загрузки станций.")
        return

    try:
        with st.spinner("Загружаю TLE и считаю пролёты..."):
            entries = load_tle_entries(tle_source, use_cache=use_cache, cache_path=cache_path)
            requests = []
            for raw_line in satellites_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.isdigit():
                    requests.append(SatelliteRequest(norad_id=line))
                else:
                    requests.append(SatelliteRequest(query=line))
            tles = select_tle_entries(entries, requests)
            start = datetime.combine(start_date, start_time, tzinfo=timezone.utc)
            end = start + timedelta(hours=float(hours))
            warnings = tle_age_warnings(tles, start)
            stations = _stations_from_df(stations_df)
            for station in stations:
                station.validate()
            from .planning import plan_contacts

            passes = plan_contacts(
                tle_entries=tles,
                stations=stations,
                start=start,
                end=end,
                min_duration_min=float(min_duration),
                min_max_elevation_deg=float(min_max_elev) if min_max_elev > 0 else None,
                coarse_step_sec=int(planning_cfg.get("coarse_step_sec", 60)),
                sample_step_sec=int(planning_cfg.get("sample_step_sec", 15)),
                day_filter=day_filter,
                resolve_conflicts=resolve_conflicts,
                downlink_rate_mbps=float(downlink_mbps) if downlink_mbps > 0 else None,
                capacity_mb_per_pass=float(capacity_mb_per_pass) if capacity_mb_per_pass > 0 else None,
                data_generation_rate_mbps=float(data_generation_rate_mbps) if data_generation_rate_mbps > 0 else None,
                initial_backlog_mb=float(initial_backlog_mb),
                recommendation_mode=recommend_mode,
                max_recommended=int(max_recommended),
                min_recommend_quality_class=min_recommend_class,
            )
            if save_to_db:
                from .database import save_run

                run_id = save_run(db_path, passes=passes, stations=stations, tles=tles, config=preset_cfg, scenario_name=PRESETS[selected_key]["name"])
                st.success(f"Расчёт сохранён в SQLite, run_id={run_id}")
    except Exception as exc:
        st.error(f"Ошибка: {exc}")
        return

    scheduled = [p for p in passes if p.scheduled]
    recommended = [p for p in scheduled if p.recommended]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Найдено", len(passes))
    c2.metric("Запланировано", len(scheduled))
    c3.metric("Рекомендовано", len(recommended))
    c4.metric("Передано, МБ", round(sum(p.transmitted_mb or 0 for p in scheduled), 2))
    c5.metric("Средний индекс", round(sum(p.quality_score for p in scheduled) / len(scheduled), 2) if scheduled else 0)

    if warnings:
        st.warning("\n".join(warnings))

    st.subheader("Расписание")
    if not passes:
        st.warning("Подходящих сеансов не найдено.")
        return
    st.dataframe(_display_df(passes), use_container_width=True, hide_index=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        csv_path = write_csv(passes, tmpdir / "schedule.csv")
        json_path = write_json(passes, tmpdir / "schedule.json")
        ics_path = write_ics(passes, tmpdir / "schedule.ics")
        map_path = write_map_html(passes, tmpdir / "map.html", stations=stations)
        static_map_path = plot_static_ground_tracks(passes, tmpdir / "static_map.png", stations=stations)
        plots = plot_passes(passes, tmpdir / "plots", only_scheduled=False)
        util_path = plot_station_utilization(passes, tmpdir / "station_utilization.png")
        report_path = write_html_report(passes, tmpdir / "report.html", plot_paths=plots, map_path=map_path, utilization_path=util_path, static_map_path=static_map_path, warnings=warnings)
        pdf_path = write_pdf_report(passes, tmpdir / "report.pdf", warnings=warnings, plot_paths=plots, utilization_path=util_path, static_map_path=static_map_path)

        st.subheader("Карта покрытия и трассы")
        st.caption("Сначала показана интерактивная карта. Ниже — статическая карта, которая также вставляется в PDF-отчёт.")
        try:
            components.html(map_path.read_text(encoding="utf-8"), height=550, scrolling=True)
        except Exception:
            st.download_button("Скачать карту HTML", map_path.read_bytes(), file_name="map.html", mime="text/html")

        st.markdown("**Статическая карта для PDF/печати**")
        st.image(str(static_map_path), use_container_width=True)

        st.subheader("Загрузка станций")
        st.image(str(util_path), use_container_width=True)

        st.subheader("Скачать результаты")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.download_button("CSV", csv_path.read_bytes(), file_name="schedule.csv", mime="text/csv")
        col2.download_button("JSON", json_path.read_bytes(), file_name="schedule.json", mime="application/json")
        col3.download_button("ICS", ics_path.read_bytes(), file_name="schedule.ics", mime="text/calendar")
        col4.download_button("HTML-отчёт", report_path.read_bytes(), file_name="report.html", mime="text/html")
        col5.download_button("PDF-отчёт", pdf_path.read_bytes(), file_name="report.pdf", mime="application/pdf")

        if plots:
            st.subheader("Графики угла места")
            for p in plots[:5]:
                st.image(str(p), caption=p.name, use_container_width=True)


def _compare_ui() -> None:
    st.subheader("Сравнение нескольких сценариев")
    keys = preset_keys()
    selected = st.multiselect("Выберите пресеты", keys, default=["iss_moscow", "iss_multi_station"])
    if st.button("Сравнить сценарии"):
        if not selected:
            st.warning("Выберите хотя бы один сценарий.")
            return
        rows = []
        try:
            with st.spinner("Считаю сценарии..."):
                from .scenario import run_preset

                for key in selected:
                    result = run_preset(key)
                    rows.append(result.summary_row())
        except Exception as exc:
            st.error(f"Ошибка сравнения: {exc}")
            return
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            csv_path = write_scenario_comparison_csv(rows, tmpdir / "scenario_comparison.csv")
            html_path = write_scenario_comparison_html(rows, tmpdir / "scenario_comparison.html")
            col1, col2 = st.columns(2)
            col1.download_button("CSV сравнения", csv_path.read_bytes(), "scenario_comparison.csv", "text/csv")
            col2.download_button("HTML сравнения", html_path.read_bytes(), "scenario_comparison.html", "text/html")


def _history_ui() -> None:
    st.subheader("История расчётов SQLite")
    db_path = st.text_input("Путь к базе", "outputs/history.sqlite", key="history_db")
    if st.button("Показать историю"):
        try:
            from .database import list_runs

            rows = list_runs(db_path)
        except Exception as exc:
            st.error(f"Не удалось открыть базу: {exc}")
            return
        if not rows:
            st.info("История пока пустая.")
        else:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _explanation_ui() -> None:
    st.subheader("Как работает программа")
    components.html(explanation_html(), height=520, scrolling=True)
    st.markdown(
        """
**Параметры по умолчанию:** горизонт расчёта 48 часов, минимальный угол 10°, минимальная длительность 5 минут, минимальный максимальный угол обычно 15°, скорость передачи 2 Мбит/с.  
**Главная идея:** спутник виден станции только короткими окнами, поэтому программа заранее находит эти окна и выбирает лучшие.
"""
    )


def main() -> None:
    st.set_page_config(page_title="Планировщик сеансов связи", layout="wide")
    st.title("Планировщик сеансов связи со спутниками")

    tab_calc, tab_compare, tab_history, tab_explain = st.tabs(["Расчёт", "Сравнение сценариев", "История", "Объяснение"])
    with tab_calc:
        _run_calculation_ui()
    with tab_compare:
        _compare_ui()
    with tab_history:
        _history_ui()
    with tab_explain:
        _explanation_ui()


if __name__ == "__main__":
    main()
