from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.query_schemas import (
    QuerySummary,
    RouterQueryItem,
    SessionQueryItem,
    SourceQueryItem,
    UserQueryItem,
)
from app.security import authenticate_query_api
from app.services.queries import get_summary, list_routers, list_sessions, list_sources, list_users


router = APIRouter(
    prefix="/query",
    tags=["local-query"],
    dependencies=[Depends(authenticate_query_api)],
)


@router.get("/summary", response_model=QuerySummary)
def query_summary(db: Session = Depends(get_db)) -> QuerySummary:
    return get_summary(db)


@router.get("/sessions/active", response_model=list[SessionQueryItem])
def query_active_sessions(
    router_id: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[SessionQueryItem]:
    return list_sessions(
        db,
        state="ACTIVE",
        router_id=router_id,
        source_id=source_id,
        username=username,
        limit=limit,
    )


@router.get("/sessions/history", response_model=list[SessionQueryItem])
def query_session_history(
    state: Literal["ACTIVE", "CLOSED"] | None = None,
    router_id: str | None = None,
    source_id: str | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[SessionQueryItem]:
    return list_sessions(
        db,
        state=state,
        router_id=router_id,
        source_id=source_id,
        username=username,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )


@router.get("/routers", response_model=list[RouterQueryItem])
def query_routers(db: Session = Depends(get_db)) -> list[RouterQueryItem]:
    return list_routers(db)


@router.get("/sources", response_model=list[SourceQueryItem])
def query_sources(db: Session = Depends(get_db)) -> list[SourceQueryItem]:
    return list_sources(db)


@router.get("/users", response_model=list[UserQueryItem])
def query_users(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[UserQueryItem]:
    return list_users(db, limit=limit)
