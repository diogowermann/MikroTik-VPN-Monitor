from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Router
from app.schemas import EventIngestResult, RouterEvent
from app.security import authenticate_router
from app.services.events import EventConflictError, EventValidationError, process_event

router = APIRouter(prefix="/router", tags=["router-ingestion"])


@router.post("/events", response_model=EventIngestResult)
def ingest_router_event(
    event: RouterEvent,
    authenticated_router: Router = Depends(authenticate_router),
    db: Session = Depends(get_db),
) -> EventIngestResult:
    try:
        result = process_event(db, router=authenticated_router, event=event)
    except EventConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EventValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return EventIngestResult(
        accepted=result.accepted,
        duplicates=result.duplicates,
        event_id=result.event_id,
        session_action=result.session_action,
    )
