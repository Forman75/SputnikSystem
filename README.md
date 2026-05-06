# Планировщик сеансов связи со спутниками

Учебная Python-система для планирования связи между LEO-спутниками и наземными станциями. Программа берёт реальные TLE-данные, рассчитывает видимость спутника над станцией, фильтрует пролёты, оценивает качество связи, решает конфликты расписания, считает передачу данных и формирует отчёты.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

## Запуск веб-интерфейса

```bash
streamlit run web_app.py
```

В интерфейсе есть вкладки:

- **Расчёт** — выбор пресета, спутников, станций, погоды, фильтров и генерация отчётов;
- **Сравнение сценариев** — сравнение нескольких готовых систем;
- **История** — просмотр последних расчётов из SQLite;
- **Объяснение** — краткая теория и описание алгоритма.

## Быстрый запуск CLI

```bash
python session_planner.py --preset iss_moscow
```

После запуска результаты появятся в папке `outputs/iss_moscow/`:

- `schedule.csv` — таблица с русскими заголовками;
- `schedule.json` — полные данные с профилями пролётов;
- `report.html` — автономный HTML-отчёт с картой, графиками и таблицей;
- `report.pdf` — PDF-отчёт;
- `map.html` — отдельная интерактивная карта;
- `station_utilization.png` — диаграмма загрузки станции;
- `schedule.ics` — календарь;
- `history.sqlite` — база истории расчётов.

## Готовые сценарии

```bash
python session_planner.py --list-presets
```

Доступны:

- `iss_moscow` — МКС и одна станция в Москве;
- `iss_multi_station` — МКС и несколько наземных станций;
- `noaa_weather` — метеоспутник NOAA 19;
- `night_passes` — только ночные пролёты;
- `station_group_multi_sat` — несколько спутников и конфликты станции;
- `weather_limited` — демонстрация погодных ограничений.

## Сравнение сценариев

```bash
python session_planner.py \
  --compare-presets iss_moscow,iss_multi_station,weather_limited \
  --out-dir outputs/comparison
```

Будут созданы:

- `outputs/comparison/scenario_comparison.csv`;
- `outputs/comparison/scenario_comparison.html`.

## Рекомендованное расписание

Примеры:

```bash
# взять топ-5 лучших сеансов
python session_planner.py --preset iss_moscow --recommend-mode top_n --max-recommended 5

# оставить рекомендованными только сеансы класса A и B
python session_planner.py --preset iss_moscow --recommend-mode quality --min-recommend-class B

# выбрать лучший сеанс для каждого спутника
python session_planner.py --preset station_group_multi_sat --recommend-mode best_per_satellite
```

В таблице есть колонка **Рекомендован**.

## Обновление TLE

```bash
python session_planner.py \
  --tle "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle" \
  --update-tle \
  --tle-cache data/stations_latest.tle \
  --preset iss_moscow
```

Можно затем запускать из кэша:

```bash
python session_planner.py --preset iss_moscow --use-tle-cache --tle-cache data/stations_latest.tle
```

## История расчётов SQLite

Расчёт сохраняется в базу автоматически, если задан путь `outputs.db` в конфиге или аргумент `--db`:

```bash
python session_planner.py --preset iss_moscow --db outputs/history.sqlite
python session_planner.py --list-runs --db outputs/history.sqlite
```

## Погодные ограничения

Погода задаётся для станции:

```yaml
stations:
  - name: Moscow GS
    lat: 55.7539
    lon: 37.6208
    min_elevation_deg: 10
    weather: rain
```

Поддерживаются значения:

```text
clear, cloudy, rain, snow, storm, fog
```

Плохая погода снижает индекс качества, а `storm` запрещает сеансы.

## Пример YAML-конфига

```yaml
tle: examples/iss_sample.tle
satellites:
  - name: ISS
stations:
  - name: Moscow GS
    lat: 55.7539
    lon: 37.6208
    elevation_m: 150
    min_elevation_deg: 10
    weather: clear
planning:
  start: now
  hours: 48
  coarse_step_sec: 60
  sample_step_sec: 10
  resolve_conflicts: true
filters:
  min_duration_min: 5
  min_max_elevation_deg: 15
data:
  downlink_mbps: 2
  capacity_mb_per_pass: 500
  data_generation_rate_mbps: 0.2
  initial_backlog_mb: 0
recommendation:
  mode: top_n
  max_count: 5
  min_quality_class: B
outputs:
  out_dir: outputs
  html: outputs/report.html
  pdf: outputs/report.pdf
  db: outputs/history.sqlite
```

## Как программа работает кратко

1. Загружает TLE спутников.
2. Проверяет возраст TLE и входные параметры.
3. На заданном интервале времени считает положение спутника относительно станции.
4. Находит окна, где спутник выше минимального угла места.
5. Считает длительность, максимальный угол, средний угол, дальность и день/ночь.
6. Учитывает условную погоду и считает индекс качества 0-100.
7. Убирает конфликтующие сеансы одной станции.
8. Выбирает рекомендованное расписание.
9. Считает, сколько данных можно передать.
10. Сохраняет таблицы, отчёты, карту, графики и историю.

## Структура проекта

```text
sat_session_planner_v9/
├── session_planner.py
├── web_app.py
├── requirements.txt
├── examples/
│   ├── config.yaml
│   ├── iss_sample.tle
│   ├── horizon_mask.csv
│   ├── stations.csv
│   └── presets/
├── satplan/
│   ├── cli.py
│   ├── config.py
│   ├── database.py
│   ├── horizon.py
│   ├── models.py
│   ├── outputs.py
│   ├── planning.py
│   ├── presets.py
│   ├── scenario.py
│   ├── sun.py
│   ├── tle.py
│   ├── utils.py
│   ├── validation.py
│   └── web_app.py
└── tests/
```

## Примечание

Это учебная система. Для настоящей эксплуатации нужно дополнительно учитывать частоты, мощность передатчика, диаграммы антенн, реальные погодные данные, правила радиосвязи и более строгую валидацию орбитальных данных.

Проверка проекта:

```bash
python -m compileall -q .
pytest -q
```

Ожидаемый результат: все тесты проходят успешно.
