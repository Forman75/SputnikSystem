from satplan.models import ContactPass
from satplan.planning import resolve_station_conflicts


def make_pass(name, start, end, score):
    return ContactPass(
        satellite=name,
        norad_id=name,
        station="S",
        station_lat=0,
        station_lon=0,
        start_utc=start,
        end_utc=end,
        duration_min=10,
        max_elevation_deg=40,
        avg_elevation_deg=20,
        max_elevation_time_utc=start,
        azimuth_at_max_deg=100,
        range_at_max_km=1000,
        sun_elevation_at_mid_deg=10,
        day_night="day",
        quality_score=score,
        quality_class="B",
    )


def test_conflict_resolution_prefers_better_pass():
    a = make_pass("A", "2025-01-01T00:00:00Z", "2025-01-01T00:10:00Z", 10)
    b = make_pass("B", "2025-01-01T00:05:00Z", "2025-01-01T00:15:00Z", 50)
    resolve_station_conflicts([a, b])
    assert not a.scheduled
    assert b.scheduled
