from .models import ContactPass, GroundStation, HorizonPoint, SatelliteRequest, TleEntry
from .tle import DEFAULT_TLE_CACHE, DEFAULT_TLE_URL, load_tle_entries, parse_tle, select_tle_entries, tle_age_days, tle_age_warnings, update_tle_cache


def __getattr__(name: str):
    if name == "plan_contacts":
        from .planning import plan_contacts

        return plan_contacts
    raise AttributeError(name)


__all__ = [
    "ContactPass",
    "GroundStation",
    "HorizonPoint",
    "SatelliteRequest",
    "TleEntry",
    "DEFAULT_TLE_URL",
    "DEFAULT_TLE_CACHE",
    "load_tle_entries",
    "parse_tle",
    "select_tle_entries",
    "tle_age_days",
    "tle_age_warnings",
    "update_tle_cache",
    "plan_contacts",
]
