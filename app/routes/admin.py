"""
Admin API — protected by X-Admin-Key header.

All routes require:
    X-Admin-Key: <ADMIN_API_KEY from .env>

Returns 401 on wrong key, 503 if ADMIN_API_KEY is not configured.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin_key
from ..database import get_db
from ..models.interaction import Interaction
from ..models.user import User
from ..schemas.ussd import AdminStats, InteractionOut

log = logging.getLogger(__name__)

# Every route in this router automatically requires a valid admin key
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_key)],
)


@router.get("/stats", response_model=AdminStats, summary="Aggregated platform stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    """Overview of users, queries, token usage, cache performance, and SMS."""

    total_users       = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_interactions = (await db.execute(select(func.count(Interaction.id)))).scalar_one()
    total_tokens      = (await db.execute(select(func.sum(Interaction.tokens_used)))).scalar_one() or 0

    cached_count = (
        await db.execute(
            select(func.count(Interaction.id)).where(Interaction.from_cache == True)  # noqa: E712
        )
    ).scalar_one()
    sms_count = (
        await db.execute(
            select(func.count(Interaction.id)).where(Interaction.sms_sent == True)  # noqa: E712
        )
    ).scalar_one()

    cache_rate   = (cached_count / total_interactions) if total_interactions else 0.0
    cat_rows     = (
        await db.execute(
            select(Interaction.category, func.count(Interaction.id).label("cnt"))
            .group_by(Interaction.category)
        )
    ).all()

    return AdminStats(
        total_users=total_users,
        total_interactions=total_interactions,
        total_tokens_used=total_tokens,
        cache_hit_rate=round(cache_rate, 3),
        sms_sent=sms_count,
        interactions_by_category={r.category: r.cnt for r in cat_rows},
    )


@router.get(
    "/interactions",
    response_model=list[InteractionOut],
    summary="Recent interactions (paginated)",
)
async def list_interactions(
    limit:    Annotated[int, Query(ge=1, le=200)] = 50,
    offset:   Annotated[int, Query(ge=0)]         = 0,
    category: str | None = Query(default=None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
) -> list[InteractionOut]:
    q = select(Interaction).order_by(Interaction.created_at.desc()).limit(limit).offset(offset)
    if category:
        q = q.where(Interaction.category == category)
    rows = (await db.execute(q)).scalars().all()
    return list(rows)


@router.get("/users", summary="Registered users (paginated)")
async def list_users(
    limit:  Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)]         = 0,
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return [
        {
            "id":           u.id,
            "phone_number": u.phone_number,
            "name":         u.name,
            "profession":   u.profession,
            "language":     u.language,
            "total_queries": u.total_queries,
            "created_at":   u.created_at,
        }
        for u in rows
    ]
