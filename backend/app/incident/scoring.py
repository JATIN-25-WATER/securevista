"""Deterministic, rule-based scoring. No ML/LLM involved: same inputs
always produce the same scores, and every term is traceable back to a
concrete rule for the explanation view."""

BASE_IMPACT = {
    "restricted_entry": 70,
    "after_hours": 50,
    "loitering": 40,
    "camera_offline": 60,
    "camera_frozen": 50,
    "camera_blackout": 80,
    "camera_blur": 30,
    "fall_warning": 65,  # potentially a medical emergency -- high impact even though the heuristic is uncertain
    "abandoned_object_warning": 35,
    "fire_smoke_warning": 75,  # life-safety impact if real, despite this being the least reliable heuristic
}

REPEAT_OBSERVATION_BONUS = 3  # per corroborating observation beyond the first
REPEAT_OBSERVATION_CAP = 15
ACCESS_EVENT_CORRELATION_PENALTY = 30  # a plausibly-matching simulated access event lowers impact

HEALTH_CONFIDENCE_PENALTY = {
    "blurred": 30,
    "frozen": 50,
    "blackout": 70,
    "offline": 90,
}

# These three types are classical-CV heuristics, not trained/validated classifiers
# (see detection/fall_heuristic.py, abandoned_object.py, fire_smoke_heuristic.py).
# Their confidence score is hard-capped regardless of anything else, so a high
# impact score (see BASE_IMPACT above) can never be misread as a high-confidence
# claim -- this is the P0 "separate impact and confidence" requirement doing
# real work: fire/smoke is scored as high-impact / low-confidence on purpose.
MAX_CONFIDENCE_BY_TYPE = {
    "fall_warning": 55,
    "abandoned_object_warning": 50,
    "fire_smoke_warning": 30,  # least reliable heuristic in the system
}


def compute_impact_score(incident_type: str, observation_count: int, access_event_matched: bool) -> float:
    base = BASE_IMPACT.get(incident_type, 40)
    repeat_bonus = min(REPEAT_OBSERVATION_BONUS * max(0, observation_count - 1), REPEAT_OBSERVATION_CAP)
    score = base + repeat_bonus
    if access_event_matched:
        score -= ACCESS_EVENT_CORRELATION_PENALTY
    return float(max(0, min(100, score)))


def compute_confidence_score(incident_type: str, avg_detector_confidence: float, observation_count: int, camera_status: str) -> float:
    score = avg_detector_confidence * 100
    score += min(observation_count - 1, 5) * 2  # more corroborating detections -> more confidence, small cap
    score -= HEALTH_CONFIDENCE_PENALTY.get(camera_status, 0)
    score = max(0, min(100, score))
    cap = MAX_CONFIDENCE_BY_TYPE.get(incident_type)
    if cap is not None:
        score = min(score, cap)
    return float(score)
