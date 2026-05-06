from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .models import SatelliteRequest, TleEntry, UTC
from .utils import ensure_dir

DEFAULT_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
DEFAULT_TLE_CACHE = "data/tle_cache.tle"


class TleError(ValueError):
    pass


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source, re.IGNORECASE))


def read_text_from_source(source: str) -> str:
    """Читает TLE из локального файла или URL."""
    if is_url(source):
        with urllib.request.urlopen(source, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"TLE-файл не найден: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def update_tle_cache(source: str = DEFAULT_TLE_URL, cache_path: str | Path = DEFAULT_TLE_CACHE) -> Path:
    """Скачивает/копирует свежий TLE в локальный кэш и возвращает путь к файлу."""
    text = read_text_from_source(source)
    parse_tle(text)
    path = Path(cache_path)
    ensure_dir(path.parent if path.parent != Path("") else ".")
    path.write_text(text, encoding="utf-8")
    return path


def load_tle_entries(source: str = DEFAULT_TLE_URL, *, use_cache: bool = False, cache_path: str | Path = DEFAULT_TLE_CACHE) -> list[TleEntry]:
    if use_cache and Path(cache_path).exists():
        return parse_tle(Path(cache_path).read_text(encoding="utf-8", errors="replace"))
    return parse_tle(read_text_from_source(source))


def parse_tle(text: str) -> list[TleEntry]:
    """Парсит TLE в формате name + line1 + line2 или line1 + line2."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[TleEntry] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            line1, line2 = lines[i], lines[i + 1]
            entries.append(TleEntry(name=f"NORAD-{line1[2:7].strip()}", line1=line1, line2=line2))
            i += 2
            continue
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            entries.append(TleEntry(name=lines[i], line1=lines[i + 1], line2=lines[i + 2]))
            i += 3
            continue
        i += 1
    if not entries:
        raise TleError("В источнике не найдено ни одной TLE-записи")
    return entries


def tle_epoch_datetime(tle: TleEntry) -> datetime | None:
    """Возвращает эпоху TLE из line1. Формат: YYDDD.dddddddd."""
    try:
        raw = tle.line1[18:32].strip()
        yy = int(raw[:2])
        day = float(raw[2:])
        year = 2000 + yy if yy < 57 else 1900 + yy
        jan1 = datetime(year, 1, 1, tzinfo=UTC)
        return jan1 + timedelta(days=day - 1.0)
    except Exception:
        return None


def tle_age_days(tle: TleEntry, reference: datetime | None = None) -> float | None:
    epoch = tle_epoch_datetime(tle)
    if epoch is None:
        return None
    ref = (reference or datetime.now(tz=UTC)).astimezone(UTC)
    return (ref - epoch).total_seconds() / 86400.0


def tle_age_warnings(tles: Iterable[TleEntry], reference: datetime | None = None, warn_days: float = 7.0, danger_days: float = 14.0) -> list[str]:
    warnings: list[str] = []
    for tle in tles:
        age = tle_age_days(tle, reference)
        if age is None:
            warnings.append(f"Не удалось определить возраст TLE для {tle.name}.")
            continue
        if age > danger_days:
            warnings.append(f"TLE для {tle.name} старше {danger_days:.0f} дней ({age:.1f} дн.) — расчёт может быть заметно неточным.")
        elif age > warn_days:
            warnings.append(f"TLE для {tle.name} старше {warn_days:.0f} дней ({age:.1f} дн.) — желательно обновить данные.")
        elif age < -1:
            warnings.append(f"Эпоха TLE для {tle.name} находится в будущем ({age:.1f} дн.). Проверьте дату расчёта.")
    return warnings


def _normalize_satellite_name(value: str) -> str:
    """Нормализует название спутника для устойчивого поиска.
    """
    return re.sub(r"[^0-9a-zа-я]+", "", value.casefold())


def select_tle_entry(entries: list[TleEntry], query: str | None = None, norad_id: str | None = None) -> TleEntry:
    if norad_id:
        n = str(norad_id).strip()
        matches = [e for e in entries if e.norad_id == n]
        if not matches:
            examples = ", ".join(f"{e.name} ({e.norad_id})" for e in entries[:10])
            raise TleError(f"Спутник с NORAD ID {n} не найден в выбранном TLE-источнике. Примеры из TLE: {examples}")
        return matches[0]

    if query:
        q = query.casefold().strip()
        if q.isdigit():
            return select_tle_entry(entries, norad_id=q)

        exact = [e for e in entries if e.name.casefold().strip() == q]
        if exact:
            return exact[0]

        matches = [e for e in entries if q in e.name.casefold()]
        if matches:
            return matches[0]

        # Поддерживает варианты вроде NOAA 19, NOAA-19 и ISS (ZARYA).
        nq = _normalize_satellite_name(query)
        normalized_matches = [e for e in entries if nq and nq in _normalize_satellite_name(e.name)]
        if normalized_matches:
            return normalized_matches[0]

        examples = ", ".join(f"{e.name} ({e.norad_id})" for e in entries[:10])
        hint = ""
        if "noaa" in q and "19" in q:
            hint = " Для NOAA 19 попробуйте TLE-источник https://celestrak.org/NORAD/elements/gp.php?CATNR=33591&FORMAT=tle или NORAD ID 33591."
        raise TleError(f"Спутник по запросу '{query}' не найден в выбранном TLE-источнике. Примеры из TLE: {examples}.{hint}")

    return entries[0]


def select_tle_entries(entries: list[TleEntry], requests: Iterable[SatelliteRequest]) -> list[TleEntry]:
    selected: list[TleEntry] = []
    seen: set[str] = set()
    for request in requests:
        tle = select_tle_entry(entries, query=request.query, norad_id=request.norad_id)
        key = tle.norad_id
        if key not in seen:
            selected.append(tle)
            seen.add(key)
    if not selected:
        selected.append(entries[0])
    return selected


def search_satellites(entries: list[TleEntry], query: str, limit: int = 20) -> list[TleEntry]:
    q = query.casefold().strip()
    if not q:
        return entries[:limit]
    matches = [e for e in entries if q in e.name.casefold() or q == e.norad_id]
    return matches[:limit]
