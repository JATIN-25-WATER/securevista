"""
backend/alerts/router.py

Endpoints for real-time WebSocket alert subscriptions, alert history querying,
and alert acknowledgement.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.jwt import decode_token, get_current_user, require_role
from backend.db.database import get_db
from backend.db.models import Camera, Observation, User
from backend.alerts.alert_manager import get_alert_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    track_id: str
    event_type: str
    timestamp: str
    zone_id: Optional[int] = None
    confidence_score: float
    impact_score: float
    explanation: str
    acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_by_username: Optional[str] = None
    acknowledged_at: Optional[str] = None

    class Config:
        from_attributes = True


class AcknowledgeResponse(BaseModel):
    status: str
    alert_id: int
    acknowledged_by: str
    acknowledged_at: str


# ── WebSocket Subscription ───────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_alerts(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Authenticated WebSocket connection endpoint.
    Client must supply valid JWT access token via ?token=<jwt>.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token required")
        return

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
            return
    except Exception as exc:
        logger.warning(f"WebSocket auth failed: {exc}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    alert_mgr = get_alert_manager()
    alert_mgr.register_loop(asyncio.get_running_loop())
    await alert_mgr.connect(websocket)

    try:
        while True:
            # Keep connection alive, listen for ping/messages from client
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        alert_mgr.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"WebSocket error: {exc}")
        alert_mgr.disconnect(websocket)


# ── Alert History REST Query ─────────────────────────────────────────────────

@router.get("", response_model=List[AlertOut])
def list_alerts(
    camera_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
):
    """
    List security alerts (observations) with optional filtering.
    """
    q = db.query(Observation, Camera.name.label("camera_name"), User.username.label("ack_username"))\
          .join(Camera, Observation.camera_id == Camera.id)\
          .outerjoin(User, Observation.acknowledged_by == User.id)

    if user.username == "operator 1":
        q = q.filter(Observation.camera_id == 1)
    elif user.username == "operator 2":
        q = q.filter(Observation.camera_id == 2)
    elif user.username == "operator 3":
        q = q.filter(Observation.camera_id == 3)
    elif camera_id is not None:
        q = q.filter(Observation.camera_id == camera_id)
    if event_type:
        q = q.filter(Observation.event_type == event_type)
    if acknowledged is not None:
        q = q.filter(Observation.acknowledged == acknowledged)

    results = q.order_by(Observation.timestamp.desc()).limit(limit).all()

    alerts = []
    for obs, cam_name, ack_username in results:
        alerts.append(
            AlertOut(
                id=obs.id,
                camera_id=obs.camera_id,
                camera_name=cam_name or f"Camera {obs.camera_id}",
                track_id=obs.track_id,
                event_type=obs.event_type,
                timestamp=obs.timestamp.isoformat(),
                zone_id=obs.zone_id,
                confidence_score=obs.confidence_score,
                impact_score=obs.impact_score,
                explanation=obs.explanation,
                acknowledged=obs.acknowledged,
                acknowledged_by=obs.acknowledged_by,
                acknowledged_by_username=ack_username,
                acknowledged_at=obs.acknowledged_at.isoformat() if obs.acknowledged_at else None,
            )
        )
    return alerts


# ── Acknowledge Alert Endpoint ───────────────────────────────────────────────

@router.post("/{alert_id}/acknowledge", response_model=AcknowledgeResponse)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator", "responder")),
):
    """
    Acknowledge a security alert. Updates DB status and notifies connected WebSocket clients.
    """
    obs = db.query(Observation).filter(Observation.id == alert_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    now = datetime.utcnow()
    obs.acknowledged = True
    obs.acknowledged_by = current_user.id
    obs.acknowledged_at = now
    db.commit()

    ack_data = {
        "alert_id": alert_id,
        "camera_id": obs.camera_id,
        "acknowledged_by": current_user.username,
        "acknowledged_by_id": current_user.id,
        "acknowledged_at": now.isoformat(),
    }

    alert_mgr = get_alert_manager()
    alert_mgr.publish_ack(ack_data)

    logger.info(f"Alert {alert_id} acknowledged by user {current_user.username}")
    return AcknowledgeResponse(
        status="acknowledged",
        alert_id=alert_id,
        acknowledged_by=current_user.username,
        acknowledged_at=now.isoformat(),
    )


# ── Telegram Test Endpoint ───────────────────────────────────────────────────

@router.post("/test-telegram/{dashboard_id}")
def test_telegram_notification(
    dashboard_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger a test Telegram notification for Dashboard 1, 2, or 3.
    """
    if dashboard_id not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="dashboard_id must be 1, 2, or 3")

    from backend.services.telegram_service import get_telegram_notifier
    result = get_telegram_notifier().send_test_notification(dashboard_id)
    return result
