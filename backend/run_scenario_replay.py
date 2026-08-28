"""Runs every deterministic scenario, verifies its expected events fired,
times it, and records a ScorecardRun per scenario -- this is what backs
the Governance 'measured performance scorecard' view. Safe to re-run;
each run just appends fresh rows.

Usage: backend/.venv/Scripts/python.exe run_scenario_replay.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import Base, SessionLocal, engine
from app.models import ScorecardRun
from app.replay.scenarios import SCENARIOS, run_scenario
from app.config import MODEL_PASSPORT


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for scenario in SCENARIOS:
            start = time.perf_counter()
            events = run_scenario(scenario)
            elapsed_ms = (time.perf_counter() - start) * 1000

            produced = {e["event_type"] for e in events}
            expected = scenario.expected_event_types
            true_positives = len(expected & produced)
            false_positives = len(produced - expected)
            false_negatives = len(expected - produced)

            precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 1.0
            recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 1.0
            passed = expected.issubset(produced)

            db.add(ScorecardRun(
                scenario_id=scenario.id,
                precision=precision,
                recall=recall,
                avg_latency_ms=elapsed_ms,
                model_version=MODEL_PASSPORT["model_version"],
                notes=f"{'PASS' if passed else 'FAIL'} -- expected={sorted(expected)} produced={sorted(produced)}",
            ))
            print(f"[{scenario.id}] {'PASS' if passed else 'FAIL'} precision={precision:.2f} recall={recall:.2f} latency={elapsed_ms:.2f}ms")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
