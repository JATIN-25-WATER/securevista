import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detection.fall_heuristic import FallHeuristic


def _bbox(cx, cy, half_w, half_h):
    return [cx - half_w, cy - half_h, cx + half_w, cy + half_h]


def test_no_warning_for_a_track_that_has_always_been_flat():
    # Never observed upright -> could just be furniture/shadow noise, not a fall.
    heuristic = FallHeuristic()
    events = heuristic.evaluate({1: {"bbox": _bbox(0.5, 0.5, 0.2, 0.08)}}, now_ts=0.0)
    assert events == []


def test_warning_fires_after_sustained_flat_posture_following_upright():
    heuristic = FallHeuristic()
    upright_bbox = _bbox(0.5, 0.5, 0.08, 0.2)  # taller than wide
    flat_bbox = _bbox(0.5, 0.5, 0.2, 0.08)  # wider than tall

    assert heuristic.evaluate({1: {"bbox": upright_bbox}}, now_ts=0.0) == []
    assert heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=1.0) == []  # not sustained yet
    events = heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=4.0)  # past FALL_SUSTAIN_SECONDS
    assert len(events) == 1
    assert events[0]["event_type"] == "fall_warning"
    assert events[0]["track_id"] == 1
    assert events[0]["emit"] is True


def test_warning_has_cooldown_but_stays_visible_every_tick():
    # `emit` (gates a new incident) is cooldown-limited, but the heuristic
    # still returns the warning every tick so the live-feed overlay box
    # doesn't disappear between incidents.
    heuristic = FallHeuristic()
    upright_bbox = _bbox(0.5, 0.5, 0.08, 0.2)
    flat_bbox = _bbox(0.5, 0.5, 0.2, 0.08)

    heuristic.evaluate({1: {"bbox": upright_bbox}}, now_ts=0.0)
    heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=0.5)  # starts the flat-dwell timer
    first = heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=4.0)  # past FALL_SUSTAIN_SECONDS
    assert len(first) == 1 and first[0]["emit"] is True

    again = heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=4.5)
    assert len(again) == 1
    assert again[0]["emit"] is False  # still within FALL_COOLDOWN_SECONDS


def test_brief_bend_does_not_fire_a_warning():
    heuristic = FallHeuristic()
    upright_bbox = _bbox(0.5, 0.5, 0.08, 0.2)
    flat_bbox = _bbox(0.5, 0.5, 0.2, 0.08)

    heuristic.evaluate({1: {"bbox": upright_bbox}}, now_ts=0.0)
    heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=1.0)  # briefly flat
    events = heuristic.evaluate({1: {"bbox": upright_bbox}}, now_ts=1.5)  # back upright before sustain threshold
    assert events == []


def test_confidence_is_always_capped_low():
    heuristic = FallHeuristic()
    upright_bbox = _bbox(0.5, 0.5, 0.08, 0.2)
    flat_bbox = _bbox(0.5, 0.5, 0.2, 0.08)

    heuristic.evaluate({1: {"bbox": upright_bbox}}, now_ts=0.0)
    heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=0.5)  # starts the flat-dwell timer
    events = heuristic.evaluate({1: {"bbox": flat_bbox}}, now_ts=100.0)  # very long dwell, first emission
    assert len(events) == 1
    assert events[0]["confidence"] <= 0.55
