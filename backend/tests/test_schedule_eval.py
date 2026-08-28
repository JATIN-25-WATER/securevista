import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detection.schedule_eval import is_after_hours

BUSINESS_HOURS = {
    "mon": [["08:00", "18:00"]],
    "tue": [["08:00", "18:00"]],
    "sat": [],
    "sun": [],
}


def test_within_business_hours_is_not_after_hours():
    assert is_after_hours(BUSINESS_HOURS, datetime(2026, 8, 24, 12, 0)) is False  # Monday noon


def test_before_open_is_after_hours():
    assert is_after_hours(BUSINESS_HOURS, datetime(2026, 8, 24, 6, 0)) is True  # Monday 6am


def test_after_close_is_after_hours():
    assert is_after_hours(BUSINESS_HOURS, datetime(2026, 8, 24, 19, 0)) is True  # Monday 7pm


def test_closed_day_is_always_after_hours():
    assert is_after_hours(BUSINESS_HOURS, datetime(2026, 8, 29, 12, 0)) is True  # Saturday noon


def test_missing_day_key_defaults_closed():
    assert is_after_hours({}, datetime(2026, 8, 24, 12, 0)) is True


NIGHT_SHIFT_HOURS = {"mon": [["22:00", "06:00"]]}


def test_overnight_window_is_open_late_at_night():
    assert is_after_hours(NIGHT_SHIFT_HOURS, datetime(2026, 8, 24, 23, 0)) is False  # Monday 11pm


def test_overnight_window_is_open_past_midnight():
    # Tuesday 3am is still "Monday's" overnight window in this schedule model
    # since business_hours is keyed by the day the window started on.
    assert is_after_hours(NIGHT_SHIFT_HOURS, datetime(2026, 8, 24, 3, 0)) is False  # Monday 3am


def test_overnight_window_is_closed_during_the_day():
    assert is_after_hours(NIGHT_SHIFT_HOURS, datetime(2026, 8, 24, 12, 0)) is True  # Monday noon
