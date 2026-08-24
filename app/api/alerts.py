from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.query_schemas import LogonAlertItem
from app.security import authenticate_query_api
from app.services.queries import list_logon_alerts


router = APIRouter(
    prefix="/alerts",
    tags=["local-alerts"],
    dependencies=[Depends(authenticate_query_api)],
)


@router.get("/logons", response_model=list[LogonAlertItem])
def query_logon_alerts(
    lookback_minutes: int = Query(default=5, ge=1, le=60),
    db: Session = Depends(get_db),
) -> list[LogonAlertItem]:
    return list_logon_alerts(db, lookback_minutes=lookback_minutes)
