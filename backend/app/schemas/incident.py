from datetime import datetime

from pydantic import BaseModel


class IncidentEventOut(BaseModel):
    id: str
    actor_id: str | None
    action: str
    ts: datetime
    note: str | None

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: str
    type: str
    status: str
    impact_score: float
    confidence_score: float
    explanation: dict
    camera_id: str | None
    zone_id: str | None
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    disposition: str | None = None
    events: list[IncidentEventOut] = []

    class Config:
        from_attributes = True


class IncidentActionIn(BaseModel):
    action: str  # acknowledge | investigate | escalate | resolve
    note: str | None = None
    disposition: str | None = None  # true_positive | false_positive | uncertain -- only used with action=resolve
