from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import any_authenticated
from app.config import MODEL_PASSPORT
from app.db import get_db
from app.models import ScorecardRun

router = APIRouter(prefix="/api/passport", tags=["passport"])


@router.get("")
def get_passport(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    runs = db.query(ScorecardRun).order_by(ScorecardRun.run_at.desc()).limit(20).all()
    return {
        "passport": MODEL_PASSPORT,
        "scorecard_runs": [
            {
                "id": r.id,
                "run_at": r.run_at,
                "scenario_id": r.scenario_id,
                "precision": r.precision,
                "recall": r.recall,
                "avg_latency_ms": r.avg_latency_ms,
                "model_version": r.model_version,
                "notes": r.notes,
            }
            for r in runs
        ],
    }
