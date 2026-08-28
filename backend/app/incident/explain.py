"""Deterministic 'why was this raised' explanation. Built entirely from
template strings over concrete rule inputs -- no generative text model
is involved anywhere in this system."""

RULE_DESCRIPTIONS = {
    "restricted_entry": "a tracked person entered zone '{zone}', which is configured as restricted",
    "after_hours": "a tracked person was present in zone '{zone}' outside its configured business hours",
    "loitering": "a tracked person remained in zone '{zone}' for at least {threshold}s, exceeding the loitering threshold",
    "camera_offline": "camera '{camera}' stopped delivering frames and did not recover within the offline timeout",
    "camera_frozen": "camera '{camera}' has shown no meaningful frame-to-frame change for the frozen-feed window",
    "camera_blackout": "camera '{camera}' frame brightness/variance dropped below the covered-camera threshold",
    "camera_blur": "camera '{camera}' image sharpness (Laplacian variance) dropped below the severe-blur threshold",
    "fall_warning": "a tracked person's bounding box matched a possible fall/collapse pattern (sudden wide/flat posture) in zone '{zone}' for at least {threshold}s",
    "abandoned_object_warning": "a static object, not overlapping any tracked person, was left in place in zone '{zone}' for at least {threshold}s",
    "fire_smoke_warning": "a sustained region of flame-like color was visible in zone '{zone}' for at least {threshold}s",
}

# These three are classical-CV heuristics, not validated classifiers -- every
# explanation for one of them carries this caveat verbatim so a responder
# never mistakes "raised" for "confirmed."
HEURISTIC_WARNING_TYPES = {"fall_warning", "abandoned_object_warning", "fire_smoke_warning"}
HEURISTIC_CAVEAT = (
    " This is a low-confidence heuristic warning, not a validated detector result -- "
    "it requires human verification before any response action is taken."
)


def build_explanation(
    incident_type: str,
    camera_name: str,
    zone_name: str | None,
    observation_count: int,
    first_ts: str,
    last_ts: str,
    avg_confidence: float,
    camera_status_at_scoring: str,
    access_event_matched: bool,
    threshold_seconds: int | None = None,
) -> dict:
    template = RULE_DESCRIPTIONS.get(incident_type, "rule '{incident_type}' fired")
    rule_text = template.format(
        zone=zone_name or "unknown zone",
        camera=camera_name,
        threshold="" if threshold_seconds is None else threshold_seconds,
        incident_type=incident_type,
    )
    narrative = (
        f"Raised because {rule_text}. "
        f"{observation_count} corroborating observation(s) between {first_ts} and {last_ts} "
        f"(average detector confidence {avg_confidence:.2f}). "
        f"Camera health at scoring time: {camera_status_at_scoring}."
    )
    if access_event_matched:
        narrative += " A simulated access-authorization event was recorded near this zone/time; impact score was reduced accordingly."
    if incident_type in HEURISTIC_WARNING_TYPES:
        narrative += HEURISTIC_CAVEAT

    return {
        "rule": incident_type,
        "camera": camera_name,
        "zone": zone_name,
        "observation_count": observation_count,
        "first_observed": first_ts,
        "last_observed": last_ts,
        "avg_detector_confidence": round(avg_confidence, 3),
        "camera_health_at_scoring": camera_status_at_scoring,
        "access_event_matched": access_event_matched,
        "narrative": narrative,
    }
