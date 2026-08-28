from datetime import datetime, time

_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def is_after_hours(business_hours: dict, dt: datetime) -> bool:
    """business_hours: {"mon": [["08:00","18:00"], ...], ...}. Empty list for a
    day means closed all day (always after-hours). No entry for a day is also
    treated as closed. A window may wrap past midnight (start > end, e.g.
    ["22:00","06:00"] for a night shift) and is still treated as open across
    the wrap. Returns True when dt falls outside every listed window."""
    day_key = _DAY_KEYS[dt.weekday()]
    windows = business_hours.get(day_key, [])
    current = dt.time()
    for start_s, end_s in windows:
        start, end = _parse_hhmm(start_s), _parse_hhmm(end_s)
        if start <= end:
            if start <= current <= end:
                return False
        else:  # wraps past midnight
            if current >= start or current <= end:
                return False
    return True
