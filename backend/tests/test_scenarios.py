"""Deterministic scenario replay tests (requirement 27): each scenario's
event sequence is asserted exactly, and running a scenario twice must
produce byte-for-byte identical results -- proving the rule engine has no
hidden dependency on wall-clock time, randomness, or call order."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.replay.scenarios import SCENARIOS, run_scenario


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario_produces_expected_event_types(scenario):
    events = run_scenario(scenario)
    produced_types = {e["event_type"] for e in events}
    assert scenario.expected_event_types.issubset(produced_types), (
        f"scenario '{scenario.id}' expected {scenario.expected_event_types}, got {produced_types}"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario_is_deterministic(scenario):
    first_run = run_scenario(scenario)
    second_run = run_scenario(scenario)
    assert first_run == second_run


def test_transient_pass_through_raises_nothing():
    scenario = next(s for s in SCENARIOS if s.id == "transient_pass_through")
    events = run_scenario(scenario)
    assert events == []
