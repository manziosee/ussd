"""
Admin API — protected by X-Admin-Key header (or ?key= query param for browser).

All routes require:
    X-Admin-Key: <ADMIN_API_KEY from .env>
  OR (for browser / dashboard):
    ?key=<ADMIN_API_KEY>

Returns 401 on wrong key, 503 if ADMIN_API_KEY is not configured.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin_key
from ..database import get_db
from ..models.feedback import Feedback
from ..models.interaction import Interaction
from ..models.market_price import MarketPrice
from ..models.user import User
from ..schemas.ussd import AdminStats, InteractionOut, MarketPriceIn, MarketPriceOut

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_key)],
)


# ── JSON API endpoints ─────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStats, summary="Aggregated platform stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    """Overview of users, queries, token usage, cache performance, and SMS."""
    total_users        = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_interactions = (await db.execute(select(func.count(Interaction.id)))).scalar_one()
    total_tokens       = (await db.execute(select(func.sum(Interaction.tokens_used)))).scalar_one() or 0

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

    cache_rate = (cached_count / total_interactions) if total_interactions else 0.0
    cat_rows   = (
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
            "id":            u.id,
            "phone_number":  u.phone_number,
            "name":          u.name,
            "profession":    u.profession,
            "language":      u.language,
            "sms_opt_out":   u.sms_opt_out,
            "total_queries": u.total_queries,
            "created_at":    u.created_at,
        }
        for u in rows
    ]


# ── Market prices ─────────────────────────────────────────────────────────────

@router.get(
    "/market-prices",
    response_model=list[MarketPriceOut],
    summary="List crop market prices",
)
async def list_market_prices(
    district: str | None = Query(default=None, description="Filter by district"),
    crop:     str | None = Query(default=None, description="Filter by crop name (case-insensitive)"),
    db: AsyncSession = Depends(get_db),
) -> list[MarketPriceOut]:
    q = select(MarketPrice).order_by(MarketPrice.district, MarketPrice.crop)
    if district:
        q = q.where(MarketPrice.district == district.lower())
    if crop:
        q = q.where(MarketPrice.crop.ilike(f"%{crop}%"))
    rows = (await db.execute(q)).scalars().all()
    return list(rows)


@router.put(
    "/market-prices",
    response_model=MarketPriceOut,
    summary="Create or update a crop price (upsert by district + crop)",
)
async def upsert_market_price(
    data: MarketPriceIn = Body(...),
    db: AsyncSession = Depends(get_db),
) -> MarketPriceOut:
    """
    Upsert a market price for a specific district + crop combination.
    If a row already exists, its price/unit/updated_by are updated.
    """
    result = await db.execute(
        select(MarketPrice).where(
            MarketPrice.district == data.district.lower(),
            MarketPrice.crop == data.crop,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.execute(
            update(MarketPrice)
            .where(MarketPrice.id == row.id)
            .values(
                price=data.price,
                currency=data.currency,
                unit=data.unit,
                updated_by=data.updated_by,
                updated_at=func.now(),
            )
        )
        await db.commit()
        await db.refresh(row)
        return row
    new_row = MarketPrice(
        district=data.district.lower(),
        crop=data.crop,
        unit=data.unit,
        price=data.price,
        currency=data.currency,
        updated_by=data.updated_by,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return new_row


@router.post(
    "/market-prices/bulk",
    response_model=list[MarketPriceOut],
    summary="Bulk upsert market prices (create or update multiple at once)",
    status_code=200,
)
async def bulk_upsert_market_prices(
    data: list[MarketPriceIn] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> list[MarketPriceOut]:
    """Upsert a list of market prices in a single request. Idempotent."""
    results: list[MarketPrice] = []
    for item in data:
        result = await db.execute(
            select(MarketPrice).where(
                MarketPrice.district == item.district.lower(),
                MarketPrice.crop == item.crop,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await db.execute(
                update(MarketPrice)
                .where(MarketPrice.id == row.id)
                .values(price=item.price, currency=item.currency, unit=item.unit,
                        updated_by=item.updated_by, updated_at=func.now())
            )
            results.append(row)
        else:
            new_row = MarketPrice(
                district=item.district.lower(),
                crop=item.crop,
                unit=item.unit,
                price=item.price,
                currency=item.currency,
                updated_by=item.updated_by,
            )
            db.add(new_row)
            await db.flush()
            results.append(new_row)
    await db.commit()
    for r in results:
        await db.refresh(r)
    return results


@router.delete(
    "/market-prices/{price_id}",
    summary="Delete a market price entry",
)
async def delete_market_price(
    price_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(MarketPrice).where(MarketPrice.id == price_id))
    row = result.scalar_one_or_none()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Price not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": price_id}


# ── Feedback ───────────────────────────────────────────────────────────────────

@router.get(
    "/feedback",
    summary="Feedback aggregate — helpful vs not-helpful counts per category",
)
async def get_feedback(
    category: str | None = Query(default=None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = select(Feedback.category, Feedback.rating, func.count(Feedback.id).label("cnt"))
    if category:
        q = q.where(Feedback.category == category)
    rows = (await db.execute(q.group_by(Feedback.category, Feedback.rating))).all()

    result: dict[str, dict] = {}
    for r in rows:
        if r.category not in result:
            result[r.category] = {"helpful": 0, "not_helpful": 0, "total": 0}
        if r.rating == 1:
            result[r.category]["helpful"] = r.cnt
        elif r.rating == -1:
            result[r.category]["not_helpful"] = r.cnt
        result[r.category]["total"] += r.cnt

    # Add satisfaction % for each category
    for cat in result:
        total = result[cat]["total"]
        result[cat]["satisfaction_pct"] = (
            round(result[cat]["helpful"] / total * 100, 1) if total else 0.0
        )
    return result


# ── HTML Dashboard ─────────────────────────────────────────────────────────────

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SmartAssist — Admin</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:system-ui,-apple-system,sans-serif;background:#f3f4f6;color:#111}}
    a{{color:#166534;text-decoration:none}}
    header{{background:#166534;color:#fff;padding:1rem 2rem;display:flex;align-items:center;gap:1rem}}
    header h1{{font-size:1.25rem;font-weight:700}}
    header span{{font-size:.8rem;opacity:.75;margin-left:auto}}
    main{{max-width:1140px;margin:2rem auto;padding:0 1rem}}
    .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:2rem}}
    .card{{background:#fff;border-radius:10px;padding:1.1rem 1.3rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    .card .v{{font-size:2rem;font-weight:700;color:#166534;line-height:1.1}}
    .card .l{{font-size:.78rem;color:#6b7280;margin-top:.3rem;text-transform:uppercase;letter-spacing:.04em}}
    .row{{display:grid;grid-template-columns:340px 1fr;gap:1.5rem;margin-bottom:2rem}}
    @media(max-width:750px){{.row{{grid-template-columns:1fr}}}}
    .panel{{background:#fff;border-radius:10px;padding:1.2rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    .panel h2{{font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#6b7280;margin-bottom:1rem}}
    .chart-wrap{{position:relative;height:220px}}
    table{{width:100%;border-collapse:collapse;font-size:.82rem}}
    thead th{{background:#f9fafb;padding:.55rem .7rem;text-align:left;font-size:.75rem;font-weight:600;
              color:#6b7280;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #e5e7eb}}
    tbody td{{padding:.55rem .7rem;border-bottom:1px solid #f3f4f6;vertical-align:top}}
    tbody tr:last-child td{{border:none}}
    .pill{{display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.7rem;font-weight:600}}
    .pill-cache{{background:#dcfce7;color:#166534}}
    .pill-live {{background:#dbeafe;color:#1e40af}}
    .pill-sms  {{background:#fef9c3;color:#854d0e}}
    .trunc{{max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    footer{{text-align:center;padding:2rem;font-size:.75rem;color:#9ca3af}}
  </style>
</head>
<body>
<header>
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M3 3h18v13H3z"/><path d="M8 21h8M12 17v4"/>
  </svg>
  <h1>SmartAssist — Admin Dashboard</h1>
  <span>Refreshed {now} UTC &nbsp;|&nbsp; <a href="/docs" style="color:#86efac">API Docs</a></span>
</header>

<main>
  <!-- ── Stat cards ────────────────────────────────────────────── -->
  <div class="cards">
    <div class="card"><div class="v">{total_users}</div><div class="l">Total Users</div></div>
    <div class="card"><div class="v">{total_interactions}</div><div class="l">Total Queries</div></div>
    <div class="card"><div class="v">{cache_rate}%</div><div class="l">Cache Hit Rate</div></div>
    <div class="card"><div class="v">{total_tokens:,}</div><div class="l">Tokens Used</div></div>
    <div class="card"><div class="v">{sms_count}</div><div class="l">SMS Sent</div></div>
  </div>

  <!-- ── Chart + recent interactions ─────────────────────────── -->
  <div class="row">
    <div class="panel">
      <h2>Queries by Category</h2>
      <div class="chart-wrap">
        <canvas id="catChart"></canvas>
      </div>
    </div>
    <div class="panel">
      <h2>Recent Interactions</h2>
      <table>
        <thead>
          <tr>
            <th>Phone</th><th>Category</th><th>Question</th><th>Type</th><th>Time (UTC)</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </div>

  <!-- ── Users table ──────────────────────────────────────────── -->
  <div class="panel" style="margin-bottom:2rem">
    <h2>Registered Users <span style="font-weight:400;color:#9ca3af">(latest {user_count})</span></h2>
    <table>
      <thead>
        <tr>
          <th>Phone</th><th>Name</th><th>Profession</th><th>Language</th>
          <th>SMS</th><th>Queries</th><th>Joined</th>
        </tr>
      </thead>
      <tbody>
        {users_html}
      </tbody>
    </table>
  </div>
</main>

<footer>
  SmartAssist USSD &nbsp;·&nbsp;
  <a href="/admin/stats">Stats JSON</a> &nbsp;·&nbsp;
  <a href="/admin/interactions">Interactions JSON</a> &nbsp;·&nbsp;
  <a href="/admin/users">Users JSON</a>
</footer>

<script>
(function(){{
  const labels = {cat_labels_json};
  const values = {cat_values_json};
  const colours = ['#166534','#15803d','#16a34a','#22c55e','#4ade80','#86efac'];
  new Chart(document.getElementById('catChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{
        label: 'Queries',
        data: values,
        backgroundColor: colours.slice(0, labels.length),
        borderRadius: 5,
        borderSkipped: false,
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        y: {{ beginAtZero: true, ticks: {{ stepSize: 1, precision: 0 }} }},
        x: {{ grid: {{ display: false }} }}
      }}
    }}
  }});
}})();
</script>
</body>
</html>
"""


def _phone_mask(phone: str) -> str:
    """Partially mask a phone number for display: +2507881****56"""
    if len(phone) <= 6:
        return phone
    return phone[:7] + "****" + phone[-2:]


def _interaction_rows(interactions: list) -> str:
    rows = []
    for i in interactions:
        source = (
            '<span class="pill pill-cache">cache</span>'
            if i.from_cache else
            '<span class="pill pill-live">live AI</span>'
        )
        if i.sms_sent:
            source += ' <span class="pill pill-sms">SMS</span>'
        ts = i.created_at.strftime("%m-%d %H:%M") if i.created_at else "—"
        rows.append(
            f"<tr>"
            f"<td>{_phone_mask(i.phone_number)}</td>"
            f"<td>{i.category}</td>"
            f'<td class="trunc" title="{i.question}">{i.question[:60]}</td>'
            f"<td>{source}</td>"
            f"<td style='white-space:nowrap'>{ts}</td>"
            f"</tr>"
        )
    return "\n".join(rows) if rows else "<tr><td colspan='5' style='color:#9ca3af;text-align:center'>No interactions yet</td></tr>"


def _user_rows(users: list) -> str:
    lang_map = {"en": "English", "rw": "Kinyarwanda"}
    rows = []
    for u in users:
        sms  = "off" if u.sms_opt_out else "on"
        lang = lang_map.get(u.language or "en", u.language or "en")
        joined = u.created_at.strftime("%Y-%m-%d") if u.created_at else "—"
        rows.append(
            f"<tr>"
            f"<td>{_phone_mask(u.phone_number)}</td>"
            f"<td>{u.name or '—'}</td>"
            f"<td>{u.profession or '—'}</td>"
            f"<td>{lang}</td>"
            f"<td>{sms}</td>"
            f"<td>{u.total_queries}</td>"
            f"<td style='white-space:nowrap'>{joined}</td>"
            f"</tr>"
        )
    return "\n".join(rows) if rows else "<tr><td colspan='7' style='color:#9ca3af;text-align:center'>No users yet</td></tr>"


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    summary="Admin HTML dashboard — browser-friendly stats + charts",
)
async def admin_dashboard(db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """
    Server-rendered HTML dashboard with Chart.js category chart, stats cards,
    recent interactions, and user table.

    Access in browser: GET /admin/dashboard?key=<ADMIN_API_KEY>
    """
    # ── Fetch data ────────────────────────────────────────────────────────────
    total_users        = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_interactions = (await db.execute(select(func.count(Interaction.id)))).scalar_one()
    total_tokens       = (await db.execute(select(func.sum(Interaction.tokens_used)))).scalar_one() or 0

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

    cache_rate = round((cached_count / total_interactions * 100) if total_interactions else 0.0, 1)

    cat_rows = (
        await db.execute(
            select(Interaction.category, func.count(Interaction.id).label("cnt"))
            .group_by(Interaction.category)
            .order_by(func.count(Interaction.id).desc())
        )
    ).all()

    recent = (
        await db.execute(
            select(Interaction).order_by(Interaction.created_at.desc()).limit(15)
        )
    ).scalars().all()

    users = (
        await db.execute(
            select(User).order_by(User.created_at.desc()).limit(20)
        )
    ).scalars().all()

    # ── Render ────────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    cat_labels = [r.category.capitalize() for r in cat_rows]
    cat_values = [r.cnt for r in cat_rows]

    html = _DASHBOARD_HTML.format(
        now=now,
        total_users=total_users,
        total_interactions=total_interactions,
        cache_rate=cache_rate,
        total_tokens=total_tokens,
        sms_count=sms_count,
        cat_labels_json=json.dumps(cat_labels),
        cat_values_json=json.dumps(cat_values),
        rows_html=_interaction_rows(recent),
        users_html=_user_rows(users),
        user_count=len(users),
    )
    return HTMLResponse(content=html)
