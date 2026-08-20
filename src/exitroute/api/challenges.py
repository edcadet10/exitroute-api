"""Public, link-free daily puzzle projection of verified route graphs."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from exitroute.api.deps import SessionDep
from exitroute.domain.graph import RouteGraph
from exitroute.errors import not_found, unprocessable
from exitroute.models import ChallengeAssignment, Route, RouteRevision
from exitroute.schemas import ChallengeScoring, DailyChallenge

router = APIRouter(prefix="/v1/challenges", tags=["challenges"])


def _eligible_revision(session: SessionDep, revision: RouteRevision) -> bool:
    route = session.get(Route, revision.route_id)
    return bool(
        route is not None
        and route.current_revision_id == revision.id
        and revision.publication_state == "published"
        and revision.trust_state == "verified"
        and revision.review_due_at is not None
        and revision.review_due_at > datetime.now(UTC)
    )


def _choose_revision(
    session: SessionDep, challenge_date: date
) -> tuple[ChallengeAssignment, RouteRevision]:
    assignment = session.get(ChallengeAssignment, challenge_date)
    if assignment is not None:
        revision = session.get(RouteRevision, assignment.revision_id)
        assert revision is not None
        if _eligible_revision(session, revision):
            return assignment, revision
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(challenge_date.toordinal())))
        assignment = session.get(ChallengeAssignment, challenge_date)
        if assignment is not None:
            revision = session.get(RouteRevision, assignment.revision_id)
            assert revision is not None
            if _eligible_revision(session, revision):
                return assignment, revision
    if assignment is not None:
        session.delete(assignment)
        session.flush()
    candidates = list(
        session.scalars(
            select(RouteRevision)
            .join(Route, Route.id == RouteRevision.route_id)
            .where(
                Route.current_revision_id == RouteRevision.id,
                RouteRevision.publication_state == "published",
                RouteRevision.trust_state == "verified",
                RouteRevision.review_due_at > datetime.now(UTC),
            )
            .order_by(RouteRevision.id)
        )
    )
    if not candidates:
        raise not_found("challenge_unavailable", "No verified route is available for this date.")
    seed = hashlib.sha256(challenge_date.isoformat().encode()).digest()
    revision = candidates[int.from_bytes(seed[:8], "big") % len(candidates)]
    assignment = ChallengeAssignment(challenge_date=challenge_date, revision_id=revision.id)
    try:
        with session.begin_nested():
            session.add(assignment)
            session.flush()
    except IntegrityError:
        assignment = session.get(ChallengeAssignment, challenge_date)
        assert assignment is not None
        revision = session.get(RouteRevision, assignment.revision_id)
        assert revision is not None
    return assignment, revision


@router.get("/daily", operation_id="getDailyChallenge", response_model=DailyChallenge)
def get_daily_challenge(
    session: SessionDep,
    response: Response,
    challenge_date: Annotated[date | None, Query(alias="date")] = None,
) -> DailyChallenge:
    today = datetime.now(UTC).date()
    selected_date = challenge_date or today
    if not today - timedelta(days=30) <= selected_date <= today + timedelta(days=1):
        raise unprocessable(
            "challenge_date_out_of_range",
            "date must be within the previous 30 days or tomorrow.",
        )
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
    assignment, revision = _choose_revision(session, selected_date)
    expires_at = datetime.combine(selected_date + timedelta(days=1), time.min, tzinfo=UTC)
    graph = RouteGraph.model_validate(revision.graph)
    return DailyChallenge(
        id=assignment.public_id,
        date=selected_date,
        title="Find the lowest-friction exit",
        graph=graph,
        scoring=ChallengeScoring(par_effort=revision.friction["effort_score"]),
        expires_at=expires_at,
    )
