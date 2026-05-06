from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ContactPass, GroundStation, TleEntry, UTC
from .outputs import build_summary
from .utils import ensure_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    scenario_name TEXT,
    config_json TEXT,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    satellite TEXT,
    norad_id TEXT,
    station TEXT,
    start_utc TEXT,
    end_utc TEXT,
    duration_min REAL,
    max_elevation_deg REAL,
    quality_score REAL,
    quality_class TEXT,
    scheduled INTEGER,
    recommended INTEGER,
    transmitted_mb REAL,
    row_json TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    name TEXT,
    lat REAL,
    lon REAL,
    elevation_m REAL,
    min_elevation_deg REAL,
    weather_condition TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS satellites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    name TEXT,
    norad_id TEXT,
    tle_epoch_utc TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_run(
    db_path: str | Path,
    *,
    passes: list[ContactPass],
    stations: list[GroundStation] | None = None,
    tles: list[TleEntry] | None = None,
    config: dict[str, Any] | None = None,
    scenario_name: str | None = None,
) -> int:
    from .tle import tle_epoch_datetime

    summary = build_summary(passes)
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO runs(created_utc, scenario_name, config_json, summary_json) VALUES (?, ?, ?, ?)",
            (
                datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                scenario_name,
                json.dumps(config or {}, ensure_ascii=False),
                json.dumps(summary, ensure_ascii=False),
            ),
        )
        run_id = int(cur.lastrowid)
        for st in stations or []:
            conn.execute(
                "INSERT INTO stations(run_id, name, lat, lon, elevation_m, min_elevation_deg, weather_condition) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, st.name, st.lat, st.lon, st.elevation_m, st.min_elevation_deg, st.weather_condition),
            )
        for tle in tles or []:
            epoch = tle_epoch_datetime(tle)
            conn.execute(
                "INSERT INTO satellites(run_id, name, norad_id, tle_epoch_utc) VALUES (?, ?, ?, ?)",
                (run_id, tle.name, tle.norad_id, epoch.isoformat().replace("+00:00", "Z") if epoch else None),
            )
        for p in passes:
            conn.execute(
                """INSERT INTO passes(run_id, satellite, norad_id, station, start_utc, end_utc, duration_min, max_elevation_deg, quality_score, quality_class, scheduled, recommended, transmitted_mb, row_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    p.satellite,
                    p.norad_id,
                    p.station,
                    p.start_utc,
                    p.end_utc,
                    p.duration_min,
                    p.max_elevation_deg,
                    p.quality_score,
                    p.quality_class,
                    int(p.scheduled),
                    int(p.recommended),
                    p.transmitted_mb,
                    json.dumps(p.flat_dict(), ensure_ascii=False),
                ),
            )
        return run_id


def list_runs(db_path: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, created_utc, scenario_name, summary_json FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for run_id, created_utc, scenario_name, summary_json in rows:
        summary = json.loads(summary_json or "{}")
        result.append({"id": run_id, "created_utc": created_utc, "scenario_name": scenario_name, **summary})
    return result
