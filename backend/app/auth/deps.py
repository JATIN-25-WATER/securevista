from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _resolve_user(token: str | None, db: Session) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    payload = decode_access_token(token)
    if not payload:
        raise unauthorized
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise unauthorized
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(token, db)


def get_current_user_flexible(
    token: str | None = Depends(oauth2_scheme),
    token_qs: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """Same as get_current_user, but also accepts ?token= as a fallback --
    needed for <img>/<video> src requests (MJPEG streams) that can't set an
    Authorization header."""
    return _resolve_user(token or token_qs, db)


def require_roles(*roles: str):
    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted to perform this action",
            )
        return user

    return _guard


require_admin = require_roles("admin")
require_admin_or_operator = require_roles("admin", "operator")
any_authenticated = require_roles("admin", "operator", "supervisor")
