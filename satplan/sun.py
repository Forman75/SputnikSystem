from __future__ import annotations

import math
from datetime import datetime

from .models import UTC


def solar_elevation_deg(dt: datetime, lat_deg: float, lon_deg: float) -> float:
    """Приближённая высота Солнца над горизонтом.
    """
    d = dt.astimezone(UTC)
    day_of_year = d.timetuple().tm_yday
    hour = d.hour + d.minute / 60 + d.second / 3600 + d.microsecond / 3_600_000_000
    gamma = 2 * math.pi / 365.0 * (day_of_year - 1 + (hour - 12) / 24.0)

    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    eqtime_min = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )

    true_solar_time_min = (hour * 60.0 + eqtime_min + 4.0 * lon_deg) % 1440.0
    hour_angle_deg = true_solar_time_min / 4.0 - 180.0
    if hour_angle_deg < -180:
        hour_angle_deg += 360.0

    lat = math.radians(lat_deg)
    ha = math.radians(hour_angle_deg)
    cos_zenith = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.acos(cos_zenith)
    return 90.0 - math.degrees(zenith)
