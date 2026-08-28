import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.incident.scoring import compute_confidence_score, compute_impact_score


def test_impact_score_uses_base_weight_for_first_observation():
    assert compute_impact_score("restricted_entry", 1, False) == 70.0


def test_impact_score_increases_with_repeat_observations_up_to_cap():
    score_2 = compute_impact_score("restricted_entry", 2, False)
    score_10 = compute_impact_score("restricted_entry", 10, False)
    assert score_2 == 73.0
    assert score_10 == 85.0  # capped bonus: 70 + min(3*9, 15) = 85


def test_access_event_match_reduces_impact_deterministically():
    without = compute_impact_score("restricted_entry", 1, False)
    with_match = compute_impact_score("restricted_entry", 1, True)
    assert with_match == without - 30


def test_impact_score_is_clamped_to_0_100():
    assert compute_impact_score("restricted_entry", 1, True) >= 0
    assert compute_impact_score("camera_blackout", 50, False) <= 100


def test_confidence_score_penalized_by_degraded_camera_health():
    healthy = compute_confidence_score("restricted_entry", 0.9, 1, "online")
    blurred = compute_confidence_score("restricted_entry", 0.9, 1, "blurred")
    assert blurred == healthy - 30


def test_confidence_score_is_deterministic_and_clamped():
    a = compute_confidence_score("restricted_entry", 0.5, 3, "frozen")
    b = compute_confidence_score("restricted_entry", 0.5, 3, "frozen")
    assert a == b
    assert 0 <= a <= 100


def test_heuristic_warning_types_have_confidence_hard_capped():
    # Even a maxed-out detector confidence and observation count must not push
    # a heuristic warning's confidence above its type-specific cap.
    fire_smoke = compute_confidence_score("fire_smoke_warning", 1.0, 10, "online")
    fall = compute_confidence_score("fall_warning", 1.0, 10, "online")
    assert fire_smoke <= 30
    assert fall <= 55


def test_fire_smoke_is_high_impact_low_confidence_by_design():
    # This is the point of separating impact from confidence: a fire/smoke
    # warning must read as high potential impact but low evidence confidence,
    # never the reverse.
    impact = compute_impact_score("fire_smoke_warning", 1, False)
    confidence = compute_confidence_score("fire_smoke_warning", 0.9, 1, "online")
    assert impact > 70
    assert confidence <= 30
    assert impact > confidence
