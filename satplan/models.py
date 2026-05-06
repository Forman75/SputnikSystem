from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

UTC = timezone.utc


@dataclass(frozen=True)
class TleEntry:
    name: str
    line1: str
    line2: str

    @property
    def norad_id(self) -> str:
        return self.line1[2:7].strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HorizonPoint:
    azimuth_deg: float
    min_elevation_deg: float


@dataclass
class GroundStation:
    name: str
    lat: float
    lon: float
    elevation_m: float = 0.0
    min_elevation_deg: float = 10.0
    horizon_mask: Optional[list[HorizonPoint]] = None
    # Учебная погода: clear/cloudy/rain/snow/storm/fog.
    weather_condition: str = "clear"

    def validate(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("У станции должно быть название.")
        if not -90 <= self.lat <= 90:
            raise ValueError(f"Некорректная широта станции {self.name}: {self.lat}. Ожидается диапазон [-90; 90].")
        if not -180 <= self.lon <= 180:
            raise ValueError(f"Некорректная долгота станции {self.name}: {self.lon}. Ожидается диапазон [-180; 180].")
        if not -500 <= self.elevation_m <= 9000:
            raise ValueError(f"Некорректная высота станции {self.name}: {self.elevation_m} м.")
        if self.min_elevation_deg < 0 or self.min_elevation_deg > 89:
            raise ValueError(f"Некорректный минимальный угол места станции {self.name}: {self.min_elevation_deg}. Ожидается [0; 89].")
        allowed_weather = {"clear", "cloudy", "rain", "snow", "storm", "fog"}
        if self.weather_condition not in allowed_weather:
            known = ", ".join(sorted(allowed_weather))
            raise ValueError(f"Некорректная погода станции {self.name}: {self.weather_condition}. Доступно: {known}.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SatelliteRequest:
    query: Optional[str] = None
    norad_id: Optional[str] = None


@dataclass
class PassProfilePoint:
    utc: str
    elevation_deg: float
    azimuth_deg: float
    required_elevation_deg: float
    range_km: float
    sun_elevation_deg: Optional[float] = None
    sub_lat_deg: Optional[float] = None
    sub_lon_deg: Optional[float] = None


@dataclass
class ContactPass:
    satellite: str
    norad_id: str
    station: str
    station_lat: float
    station_lon: float
    start_utc: str
    end_utc: str
    duration_min: float
    max_elevation_deg: float
    avg_elevation_deg: float
    max_elevation_time_utc: str
    azimuth_at_max_deg: float
    range_at_max_km: float
    sun_elevation_at_mid_deg: float
    day_night: str
    quality_score: float
    quality_class: str
    scheduled: bool = True
    conflict_reason: Optional[str] = None
    capacity_mb: Optional[float] = None
    generated_before_mb: Optional[float] = None
    transmitted_mb: Optional[float] = None
    backlog_after_mb: Optional[float] = None
    recommended: bool = True
    recommendation_reason: Optional[str] = None
    weather_condition: str = "clear"
    weather_penalty: float = 0.0
    weather_ok: bool = True
    profile: list[PassProfilePoint] = field(default_factory=list)

    def start_dt(self) -> datetime:
        return parse_utc_datetime(self.start_utc)

    def end_dt(self) -> datetime:
        return parse_utc_datetime(self.end_utc)

    def flat_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("profile", None)
        return d


def parse_utc_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        v = value.strip()
        if v.lower() in {"now", "utcnow", "сейчас"}:
            return datetime.now(tz=UTC)
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
