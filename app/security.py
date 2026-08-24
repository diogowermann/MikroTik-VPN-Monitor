import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Router, RouterCredential
from app.timeutils import utc_now


def hash_router_secret(secret: str) -> str:
    """Hash a high-entropy router bearer secret for persistence."""
    if not secret:
        raise ValueError("router secret must not be empty")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def authenticate_router(
    authorization: str | None = Header(default=None, alias="Authorization"),
    router_id: str | None = Header(default=None, alias="X-Router-ID"),
    db: Session = Depends(get_db),
) -> Router:
    if not authorization or not authorization.startswith("Bearer ") or not router_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="router authentication required",
        )

    secret = authorization[7:].strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="router authentication required",
        )

    router = db.get(Router, router_id)
    if router is None or not router.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid router credentials",
        )

    supplied_hash = hash_router_secret(secret)
    credentials = db.scalars(
        select(RouterCredential).where(
            RouterCredential.router_id == router.id,
            RouterCredential.revoked_at.is_(None),
        )
    ).all()
    matched = next(
        (
            credential
            for credential in credentials
            if hmac.compare_digest(credential.token_hash, supplied_hash)
        ),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid router credentials",
        )

    now = utc_now()
    matched.last_used_at = now
    router.last_seen_at = now
    db.commit()
    return router


def authenticate_query_api(
    query_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Require the locally configured read-only API key for query endpoints."""
    configured_key = get_settings().query_api_key
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="query API is not configured",
        )

    if not query_api_key or not hmac.compare_digest(query_api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid query API key",
        )
