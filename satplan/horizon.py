from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .models import HorizonPoint


def load_horizon_mask(path: str | Path) -> list[HorizonPoint]:
    """Загружает CSV-маску горизонта: azimuth_deg,min_elevation_deg."""
    points: list[HorizonPoint] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Пустой CSV-файл маски горизонта")
        fields = {name.casefold(): name for name in reader.fieldnames}
        az_key = fields.get("azimuth_deg") or fields.get("azimuth") or fields.get("az")
        el_key = fields.get("min_elevation_deg") or fields.get("elevation_deg") or fields.get("el")
        if not az_key or not el_key:
            raise ValueError("Маска горизонта должна содержать колонки azimuth_deg,min_elevation_deg")
        for row in reader:
            points.append(HorizonPoint(float(row[az_key]) % 360.0, float(row[el_key])))
    if len(points) < 2:
        raise ValueError("Для маски горизонта нужно хотя бы две точки")
    return sorted(points, key=lambda p: p.azimuth_deg)


def required_elevation_for_azimuth(azimuth_deg: float | np.ndarray, base_min_elev_deg: float, mask: list[HorizonPoint] | None) -> float | np.ndarray:
    """Возвращает требуемый угол места: максимум из базового порога и маски горизонта."""
    if not mask:
        if isinstance(azimuth_deg, np.ndarray):
            return np.full_like(azimuth_deg, float(base_min_elev_deg), dtype=float)
        return float(base_min_elev_deg)

    az = np.asarray([p.azimuth_deg for p in mask], dtype=float)
    el = np.asarray([p.min_elevation_deg for p in mask], dtype=float)

    # Замыкаем 0/360° для интерполяции.
    az_ext = np.concatenate([az, [az[0] + 360.0]])
    el_ext = np.concatenate([el, [el[0]]])
    x = np.asarray(azimuth_deg, dtype=float) % 360.0
    interpolated = np.interp(x, az_ext, el_ext)
    required = np.maximum(float(base_min_elev_deg), interpolated)
    if np.isscalar(azimuth_deg):
        return float(required)
    return required
