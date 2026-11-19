"""Progress towards the next legacy career level's promotion thresholds.

The seeded thresholds are provisional (see docs/open-questions.md). Volumes are
lifetime totals of contract value (product base price) on ACTIVE/RENEWED
contracts; `evaluation_window_months` is intentionally not applied here."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import ProductVersion
from app.modules.commissions.models import Rank
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile

VOLUME_STATUSES = ("ACTIVE", "RENEWED")


@dataclass
class RankProgress:
    current_rank_code: str | None
    current_rank_name: str | None
    next_rank_code: str | None
    next_rank_name: str | None
    is_max_rank: bool
    personal_volume_cents: int
    personal_volume_threshold_cents: int
    group_volume_cents: int
    group_volume_threshold_cents: int


async def volume_for_agents(
    db: AsyncSession,
    *,
    agent_ids: list[uuid.UUID],
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    """Contract value on ACTIVE/RENEWED contracts produced by `agent_ids`.
    Lifetime when `since`/`until` are None; rank evaluation passes a
    calendar-month window."""
    if not agent_ids:
        return 0
    stmt = (
        select(func.coalesce(func.sum(ProductVersion.base_price_cents), 0))
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(
            ContractAttribution.producer_agent_id.in_(agent_ids),
            Contract.status.in_(VOLUME_STATUSES),
        )
    )
    if since is not None:
        stmt = stmt.where(Contract.activated_at >= since)
    if until is not None:
        stmt = stmt.where(Contract.activated_at < until)
    return int((await db.execute(stmt)).scalar_one())


async def get_rank_progress(db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> RankProgress:
    agent = await db.get(AgentProfile, agent_id)
    current_rank = (
        await db.get(Rank, agent.current_rank_id) if agent is not None and agent.current_rank_id else None
    )

    next_rank = None
    if current_rank is not None:
        next_stmt = (
            select(Rank)
            .where(
                Rank.organization_id == organization_id,
                Rank.rule_version == current_rank.rule_version,
                Rank.level > current_rank.level,
            )
            .order_by(Rank.level.asc())
            .limit(1)
        )
        next_rank = (await db.execute(next_stmt)).scalar_one_or_none()

    personal_volume_cents = await volume_for_agents(db, agent_ids=[agent_id])

    # Group volume includes the agent: get_branch() returns the root at depth 0.
    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=agent_id)
    branch_agent_ids = [row["agent_id"] for row in branch] or [agent_id]
    group_volume_cents = await volume_for_agents(db, agent_ids=branch_agent_ids)

    return RankProgress(
        current_rank_code=current_rank.code if current_rank else None,
        current_rank_name=current_rank.name if current_rank else None,
        next_rank_code=next_rank.code if next_rank else None,
        next_rank_name=next_rank.name if next_rank else None,
        is_max_rank=current_rank is not None and next_rank is None,
        personal_volume_cents=personal_volume_cents,
        personal_volume_threshold_cents=next_rank.personal_volume_threshold_cents if next_rank else 0,
        group_volume_cents=group_volume_cents,
        group_volume_threshold_cents=next_rank.group_volume_threshold_cents if next_rank else 0,
    )
