"""GET /health — service and database status. Public, and no AI involved."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.schemas import HealthResponse
from app.services import utc_now

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """Report status, version, database reachability and the current time.

    The database is checked with a trivial query rather than assumed: a health
    check that only proves the web process is alive would report "ok" while
    every real request failed.
    """
    try:
        db.execute(text("SELECT 1"))
        database_state = "connected"
    except SQLAlchemyError:
        database_state = "unavailable"

    return HealthResponse(
        status="ok",
        version=config.APP_VERSION,
        database=database_state,
        timestamp=utc_now(),
    )
