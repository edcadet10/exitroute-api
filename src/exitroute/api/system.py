"""Liveness and dependency-readiness endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from exitroute.api.deps import SessionDep
from exitroute.errors import ApiProblemError
from exitroute.schemas import Health, Ready

router = APIRouter(tags=["system"])


@router.get("/healthz", operation_id="getHealth", response_model=Health)
def health() -> Health:
    return Health()


@router.get("/readyz", operation_id="getReadiness", response_model=Ready)
def readiness(session: SessionDep) -> Ready:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise ApiProblemError(
            503,
            "database_unavailable",
            "Service unavailable",
            "The database dependency is unavailable.",
        ) from exc
    return Ready()
