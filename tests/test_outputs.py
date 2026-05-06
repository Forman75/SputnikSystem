from pathlib import Path

from satplan.models import ContactPass, GroundStation, PassProfilePoint
from satplan.outputs import (
    _split_antimeridian,
    plot_static_ground_tracks,
    plot_station_utilization,
    write_ics,
    write_html_report,
    write_map_html,
    write_pdf_report,
)


def _fake_pass() -> ContactPass:
    profile = [
        PassProfilePoint("2026-01-01T00:00:00Z", 12, 10, 10, 900, sub_lat_deg=10, sub_lon_deg=170),
        PassProfilePoint("2026-01-01T00:01:00Z", 25, 20, 10, 800, sub_lat_deg=12, sub_lon_deg=179),
        PassProfilePoint("2026-01-01T00:02:00Z", 30, 30, 10, 750, sub_lat_deg=14, sub_lon_deg=-179),
        PassProfilePoint("2026-01-01T00:03:00Z", 20, 40, 10, 850, sub_lat_deg=16, sub_lon_deg=-170),
    ]
    return ContactPass(
        satellite="TESTSAT",
        norad_id="99999",
        station="Тестовая станция",
        station_lat=55.0,
        station_lon=37.0,
        start_utc="2026-01-01T00:00:00Z",
        end_utc="2026-01-01T00:03:00Z",
        duration_min=3.0,
        max_elevation_deg=30.0,
        avg_elevation_deg=21.75,
        max_elevation_time_utc="2026-01-01T00:02:00Z",
        azimuth_at_max_deg=30.0,
        range_at_max_km=750.0,
        sun_elevation_at_mid_deg=-5.0,
        day_night="night",
        quality_score=60.0,
        quality_class="B",
        scheduled=True,
        recommended=True,
        weather_condition="clear",
        profile=profile,
    )


def test_antimeridian_split_breaks_long_jump():
    segments = _split_antimeridian([[0, 170], [1, 179], [2, -179], [3, -170]])
    assert len(segments) == 2
    assert segments[0][-1][1] == 179
    assert segments[1][0][1] == -179


def test_outputs_render_without_duplicate_ics_summary(tmp_path: Path):
    passes = [_fake_pass()]
    stations = [GroundStation("Тестовая станция", 55, 37, min_elevation_deg=10)]
    ics = write_ics(passes, tmp_path / "schedule.ics")
    text = ics.read_text(encoding="utf-8")
    assert text.count("SUMMARY:") == 1

    map_html = write_map_html(passes, tmp_path / "map.html", stations=stations)
    static_map = plot_static_ground_tracks(passes, tmp_path / "static_map.png", stations=stations)
    util = plot_station_utilization(passes, tmp_path / "util.png")
    report = write_html_report(passes, tmp_path / "report.html", map_path=map_html, static_map_path=static_map, utilization_path=util)
    pdf = write_pdf_report(passes, tmp_path / "report.pdf", static_map_path=static_map, utilization_path=util)

    assert map_html.exists() and map_html.stat().st_size > 0
    assert static_map.exists() and static_map.stat().st_size > 0
    assert util.exists() and util.stat().st_size > 0
    assert "Статическая карта" in report.read_text(encoding="utf-8")
    assert pdf.exists() and pdf.stat().st_size > 0


def test_utilization_empty_data_does_not_crash(tmp_path: Path):
    out = plot_station_utilization([], tmp_path / "empty_util.png")
    assert out.exists() and out.stat().st_size > 0
