from satplan.tle import parse_tle, select_tle_entry

SAMPLE = """ISS (ZARYA)
1 25544U 98067A   25115.53800926  .00012022  00000+0  21608-3 0  9991
2 25544  51.6388 226.7095 0003921 132.9172 227.2150 15.50144785507702
"""


def test_parse_tle_with_name():
    entries = parse_tle(SAMPLE)
    assert len(entries) == 1
    assert entries[0].name == "ISS (ZARYA)"
    assert entries[0].norad_id == "25544"


def test_select_tle_by_query():
    entries = parse_tle(SAMPLE)
    assert select_tle_entry(entries, query="ISS").norad_id == "25544"

NOAA_SAMPLE = """NOAA-19
1 33591U 09005A   25115.50000000  .00000080  00000+0  70000-4 0  9991
2 33591  99.0000 180.0000 0014000 100.0000 260.0000 14.12000000123456
"""


def test_select_tle_by_norad_string_query_and_normalized_name():
    entries = parse_tle(NOAA_SAMPLE)
    assert select_tle_entry(entries, query="33591").name == "NOAA-19"
    assert select_tle_entry(entries, query="NOAA 19").norad_id == "33591"
    assert select_tle_entry(entries, norad_id="33591").norad_id == "33591"
