"""Commercial roles, role history and influencer delegations.

Every write affects future payouts, so each records a before/after audit entry.
"""

import uuid
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import utcnow
from app.modules.audit import service as audit_service
from app.modules.commercial.models import COMMISSION_MODES, CommercialRole, Delegation, SellerRoleHistory
from app.modules.network.models import AgentProfile

#: Initial roles for a new organization: structure only, no amounts. Shares
#: live in Split Plans and everything here is editable from the panel.
DEFAULT_COMMERCIAL_ROLES: list[dict] = [
    {
        "code": "NETWORKER", "name": "Agente digitale / Networker", "sort_order": 10, "is_default": True,
        "commission_mode": "PERCENTAGE", "network_depth": None, "allows_delegation": False,
        "allows_downline": True, "can_close_sales": True,
        "description": "Vende tramite canali digitali e può sviluppare una rete su più livelli.",
    },
    {
        "code": "AGENTE_PAP", "name": "Agente porta a porta", "sort_order": 20,
        "commission_mode": "PERCENTAGE", "network_depth": 2, "allows_delegation": False,
        "allows_downline": False, "can_close_sales": True,
        "description": "Vende direttamente; di norma sopra di lui c'è il Direttore commerciale.",
    },
    {
        "code": "DIRETTORE_COMMERCIALE", "name": "Direttore commerciale", "sort_order": 30,
        "commission_mode": "PERCENTAGE", "network_depth": 2, "allows_delegation": False,
        "allows_downline": True, "can_close_sales": True,
        "description": "Coordina gli agenti e riceve una quota sulle vendite della squadra.",
    },
    {
        "code": "INFLUENCER", "name": "Influencer", "sort_order": 40,
        "commission_mode": "MIXED", "network_depth": None, "allows_delegation": True,
        "allows_downline": True, "can_close_sales": False,
        "description": "Non chiude la vendita: ha delegati che vendono per suo conto.",
    },
    {
        "code": "DELEGATO_INFLUENCER", "name": "Delegato dell'influencer", "sort_order": 50,
        "commission_mode": "PERCENTAGE", "network_depth": None, "allows_delegation": False,
        "allows_downline": False, "can_close_sales": True,
        "description": "Esegue materialmente la vendita nella rete dell'influencer.",
    },
    {
        "code": "PROMOTER", "name": "Promoter (segnalatore)", "sort_order": 60,
        "commission_mode": "REFERRAL_FEE", "network_depth": 0, "allows_delegation": False,
        "allows_downline": False, "can_close_sales": False,
        "description": "Porta una segnalazione e riceve una fee quando si converte; non segue la trattativa.",
    },
]

ROLE_FIELDS = (
    "name", "description", "commission_mode", "network_depth", "allows_delegation",
    "allows_downline", "can_close_sales", "is_default", "is_active", "sort_order",
)


class CommercialRoleError(Exception):
    pass


def _role_dict(role: CommercialRole) -> dict:
    return {f: getattr(role, f) for f in ("code", *ROLE_FIELDS)}


# --- Roles --------------------------------------------------------------------


async def list_roles(db: AsyncSession, *, organization_id: uuid.UUID, include_inactive: bool = True) -> list[CommercialRole]:
    stmt = select(CommercialRole).where(CommercialRole.organization_id == organization_id)
    if not include_inactive:
        stmt = stmt.where(CommercialRole.is_active.is_(True))
    return list((await db.execute(stmt.order_by(CommercialRole.sort_order, CommercialRole.name))).scalars())


async def get_role(db: AsyncSession, *, organization_id: uuid.UUID, role_id: uuid.UUID) -> CommercialRole | None:
    role = await db.get(CommercialRole, role_id)
    return role if role is not None and role.organization_id == organization_id else None


async def default_role(db: AsyncSession, *, organization_id: uuid.UUID) -> CommercialRole | None:
    return (
        await db.execute(
            select(CommercialRole).where(
                CommercialRole.organization_id == organization_id,
                CommercialRole.is_default.is_(True),
                CommercialRole.is_active.is_(True),
            )
        )
    ).scalars().first()


def _check_values(values: dict) -> None:
    if "commission_mode" in values and values["commission_mode"] not in COMMISSION_MODES:
        raise CommercialRoleError("Tipo di remunerazione non valido.")
    depth = values.get("network_depth")
    if depth is not None and (depth < 0 or depth > 50):
        raise CommercialRoleError("La profondità di rete va da 0 a 50 livelli (vuota = senza limite).")


async def _clear_other_defaults(db: AsyncSession, *, organization_id: uuid.UUID, keep_id: uuid.UUID) -> None:
    await db.execute(
        update(CommercialRole)
        .where(CommercialRole.organization_id == organization_id, CommercialRole.id != keep_id)
        .values(is_default=False)
    )


async def create_role(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, values: dict
) -> CommercialRole:
    _check_values(values)
    code = (values.get("code") or "").strip().upper()
    if not code:
        raise CommercialRoleError("Il codice del ruolo è obbligatorio.")
    exists = (
        await db.execute(
            select(CommercialRole.id).where(CommercialRole.organization_id == organization_id, CommercialRole.code == code)
        )
    ).first()
    if exists is not None:
        raise CommercialRoleError(f"Esiste già un ruolo con codice {code}.")
    role = CommercialRole(organization_id=organization_id, code=code, **{f: values[f] for f in ROLE_FIELDS if f in values})
    db.add(role)
    await db.flush()
    if role.is_default:
        await _clear_other_defaults(db, organization_id=organization_id, keep_id=role.id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="commercial_role.created", entity_type="commercial_role", entity_id=str(role.id),
        new_value=_role_dict(role),
    )
    await db.commit()
    await db.refresh(role)
    return role


async def update_role(
    db: AsyncSession, *, organization_id: uuid.UUID, role_id: uuid.UUID, actor_user_id: uuid.UUID | None, values: dict
) -> CommercialRole:
    """The code is immutable because plans and histories reference it.
    Configuration changes affect only future sales."""
    role = await get_role(db, organization_id=organization_id, role_id=role_id)
    if role is None:
        raise CommercialRoleError("Ruolo non trovato.")
    _check_values(values)
    before = _role_dict(role)
    for field in ROLE_FIELDS:
        if field in values:
            setattr(role, field, values[field])
    role.updated_at = utcnow()
    if role.is_default:
        await _clear_other_defaults(db, organization_id=organization_id, keep_id=role.id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="commercial_role.updated", entity_type="commercial_role", entity_id=str(role.id),
        previous_value=before, new_value=_role_dict(role),
    )
    await db.commit()
    await db.refresh(role)
    return role


async def ensure_default_roles(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, CommercialRole]:
    """Idempotent: creates missing initial roles, never alters existing ones."""
    existing = {r.code: r for r in await list_roles(db, organization_id=organization_id)}
    has_default = any(r.is_default for r in existing.values())
    for spec in DEFAULT_COMMERCIAL_ROLES:
        if spec["code"] in existing:
            continue
        values = dict(spec)
        if has_default:
            values["is_default"] = False
        role = CommercialRole(organization_id=organization_id, **values)
        db.add(role)
        existing[role.code] = role
    await db.flush()
    return existing


# --- Role history ---------------------------------------------------------------


async def roles_at(
    db: AsyncSession, *, agent_ids: list[uuid.UUID], at: datetime
) -> dict[uuid.UUID, CommercialRole]:
    """Each member's role at `at`. Members with no role yet at that date get
    their first role, the one they joined with."""
    if not agent_ids:
        return {}
    rows = (
        await db.execute(
            select(SellerRoleHistory, CommercialRole)
            .join(CommercialRole, CommercialRole.id == SellerRoleHistory.role_id)
            .where(SellerRoleHistory.agent_id.in_(agent_ids))
            .order_by(SellerRoleHistory.agent_id, SellerRoleHistory.valid_from)
        )
    ).all()
    result: dict[uuid.UUID, CommercialRole] = {}
    first: dict[uuid.UUID, CommercialRole] = {}
    for history, role in rows:
        first.setdefault(history.agent_id, role)
        if history.valid_from <= at and (history.valid_to is None or history.valid_to > at):
            result[history.agent_id] = role
    for agent_id, role in first.items():
        result.setdefault(agent_id, role)
    return result


async def role_at(db: AsyncSession, *, agent_id: uuid.UUID, at: datetime) -> CommercialRole | None:
    return (await roles_at(db, agent_ids=[agent_id], at=at)).get(agent_id)


async def role_history(db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(SellerRoleHistory, CommercialRole)
            .join(CommercialRole, CommercialRole.id == SellerRoleHistory.role_id)
            .where(SellerRoleHistory.organization_id == organization_id, SellerRoleHistory.agent_id == agent_id)
            .order_by(SellerRoleHistory.valid_from.desc())
        )
    ).all()
    return [
        {
            "id": h.id, "role_id": r.id, "role_code": r.code, "role_name": r.name,
            "valid_from": h.valid_from, "valid_to": h.valid_to, "reason": h.reason,
        }
        for h, r in rows
    ]


async def assign_role(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    role_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    effective_from: datetime | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> SellerRoleHistory:
    """Change the role from `effective_from` (default now) by closing the open
    period and opening a new one; past sales keep their role."""
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise CommercialRoleError("Collaboratore non trovato.")
    role = await get_role(db, organization_id=organization_id, role_id=role_id)
    if role is None:
        raise CommercialRoleError("Ruolo non trovato.")
    if not role.is_active:
        raise CommercialRoleError(f"Il ruolo {role.name} non è attivo.")

    when = effective_from or utcnow()
    current = (
        await db.execute(
            select(SellerRoleHistory)
            .where(SellerRoleHistory.agent_id == agent_id, SellerRoleHistory.valid_to.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    previous_code = None
    if current is not None:
        if current.role_id == role_id:
            raise CommercialRoleError(f"Ha già il ruolo {role.name}.")
        if when <= current.valid_from:
            raise CommercialRoleError(
                "La data del cambio deve essere successiva all'inizio del ruolo attuale: "
                "il passato non si riscrive."
            )
        previous = await db.get(CommercialRole, current.role_id)
        previous_code = previous.code if previous else None
        current.valid_to = when

    history = SellerRoleHistory(
        organization_id=organization_id, agent_id=agent_id, role_id=role_id,
        valid_from=when, reason=reason, changed_by_user_id=actor_user_id,
    )
    db.add(history)
    agent.current_commercial_role_id = role_id
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="commercial_role.assigned", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value={"role": previous_code}, new_value={"role": role.code, "valid_from": when.isoformat()},
        reason=reason,
    )
    if commit:
        await db.commit()
        await db.refresh(history)
    else:
        await db.flush()
    return history


async def ensure_role_for_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent: AgentProfile, role_id: uuid.UUID | None = None
) -> None:
    """Assign the given role, or the organization default, to a new member.
    Does not commit."""
    has_role = (
        await db.execute(select(SellerRoleHistory.id).where(SellerRoleHistory.agent_id == agent.id).limit(1))
    ).first()
    if has_role is not None:
        return
    role = (
        await get_role(db, organization_id=organization_id, role_id=role_id)
        if role_id is not None
        else await default_role(db, organization_id=organization_id)
    )
    if role is None:
        return
    db.add(SellerRoleHistory(
        organization_id=organization_id, agent_id=agent.id, role_id=role.id,
        valid_from=agent.joined_at, reason="Ruolo di ingresso nella rete",
    ))
    agent.current_commercial_role_id = role.id
    await db.flush()


# --- Delegations -----------------------------------------------------------------


async def list_delegations(
    db: AsyncSession, *, organization_id: uuid.UUID, influencer_agent_id: uuid.UUID | None = None
) -> list[dict]:
    stmt = select(Delegation).where(Delegation.organization_id == organization_id)
    if influencer_agent_id is not None:
        stmt = stmt.where(Delegation.influencer_agent_id == influencer_agent_id)
    rows = list((await db.execute(stmt.order_by(Delegation.valid_from.desc()))).scalars())
    ids = {r.influencer_agent_id for r in rows} | {r.delegate_agent_id for r in rows}
    names = dict(
        (await db.execute(select(AgentProfile.id, AgentProfile.display_name).where(AgentProfile.id.in_(ids)))).all()
    ) if ids else {}
    return [
        {
            "id": r.id, "influencer_agent_id": r.influencer_agent_id,
            "influencer_name": names.get(r.influencer_agent_id, "—"),
            "delegate_agent_id": r.delegate_agent_id, "delegate_name": names.get(r.delegate_agent_id, "—"),
            "valid_from": r.valid_from, "valid_to": r.valid_to, "reason": r.reason,
        }
        for r in rows
    ]


async def create_delegation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    influencer_agent_id: uuid.UUID,
    delegate_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    reason: str | None = None,
) -> Delegation:
    if influencer_agent_id == delegate_agent_id:
        raise CommercialRoleError("Una persona non può essere delegata di sé stessa.")
    now = utcnow()
    for agent_id in (influencer_agent_id, delegate_agent_id):
        agent = await db.get(AgentProfile, agent_id)
        if agent is None or agent.organization_id != organization_id:
            raise CommercialRoleError("Collaboratore non trovato.")
    influencer_role = await role_at(db, agent_id=influencer_agent_id, at=now)
    if influencer_role is None or not influencer_role.allows_delegation:
        raise CommercialRoleError("Il ruolo di questa persona non prevede delegati.")
    open_row = (
        await db.execute(
            select(Delegation).where(Delegation.delegate_agent_id == delegate_agent_id, Delegation.valid_to.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if open_row is not None:
        if open_row.influencer_agent_id == influencer_agent_id:
            raise CommercialRoleError("La delega esiste già.")
        open_row.valid_to = now
    delegation = Delegation(
        organization_id=organization_id, influencer_agent_id=influencer_agent_id,
        delegate_agent_id=delegate_agent_id, valid_from=now, created_by_user_id=actor_user_id, reason=reason,
    )
    db.add(delegation)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="delegation.created", entity_type="delegation", entity_id=str(delegation.id),
        previous_value={"influencer_agent_id": str(open_row.influencer_agent_id)} if open_row else None,
        new_value={"influencer_agent_id": str(influencer_agent_id), "delegate_agent_id": str(delegate_agent_id)},
        reason=reason,
    )
    await db.commit()
    await db.refresh(delegation)
    return delegation


async def end_delegation(
    db: AsyncSession, *, organization_id: uuid.UUID, delegation_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Delegation:
    delegation = await db.get(Delegation, delegation_id)
    if delegation is None or delegation.organization_id != organization_id:
        raise CommercialRoleError("Delega non trovata.")
    if delegation.valid_to is not None:
        raise CommercialRoleError("La delega è già chiusa.")
    delegation.valid_to = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="delegation.ended", entity_type="delegation", entity_id=str(delegation.id),
        new_value={"valid_to": delegation.valid_to.isoformat()},
    )
    await db.commit()
    await db.refresh(delegation)
    return delegation


async def delegation_influencer_at(
    db: AsyncSession, *, delegate_agent_id: uuid.UUID, at: datetime
) -> uuid.UUID | None:
    return (
        await db.execute(
            select(Delegation.influencer_agent_id).where(
                Delegation.delegate_agent_id == delegate_agent_id,
                Delegation.valid_from <= at,
                or_(Delegation.valid_to.is_(None), Delegation.valid_to > at),
            )
        )
    ).scalar_one_or_none()
