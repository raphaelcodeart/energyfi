"""The signed-in person's MAMIX and MamiCash balances, read from Mamify.

Mamify holds the wallets; SOS only reads them (`rag/customer/wallets`, one
read-only call: see mamify/client.py READ_ONLY_PATHS). The person is found
through their place in the copied network: their login → their Digital
Ambassador profile → the Mamify customer it mirrors. Someone not in the
network (an admin, a customer without a Mamify account) gets
`connected: false` and the dashboard says so instead of showing a fake zero.

Answers are kept in memory for CACHE_SECONDS per Mamify customer, so opening
the home page again does not spend Mamify's call allowance.
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CACHE_SECONDS = 120

_cache: dict[tuple[uuid.UUID, str], tuple[float, dict]] = {}


def _cents(value) -> int | None:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _empty(provider: str = "Mamify") -> dict:
    return {
        "connected": False, "provider": provider, "account": None,
        "mamix_cents": None, "mamicash_cents": None,
        "mamicash_personal_cents": None, "mamicash_business_cents": None,
        "updated_at": None, "error": None,
    }


def parse_wallets(answer: dict) -> dict:
    """Mamify's answer → the cents the dashboard shows."""
    mamix = (answer or {}).get("mamix") or {}
    cash = (answer or {}).get("mamicash") or {}
    return {
        "mamix_cents": _cents(mamix.get("balance")),
        "mamicash_cents": _cents(cash.get("balance")),
        "mamicash_personal_cents": _cents(cash.get("personal")),
        "mamicash_business_cents": _cents(cash.get("business")),
    }


async def fetch_balances(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, fresh: bool = False) -> dict:
    from app.foundation.db import utcnow
    from app.modules.mamify import service as mamify_service
    from app.modules.mamify.client import MamifyApiError
    from app.modules.mamify.models import MamifyConfig, MamifyMember
    from app.modules.network.models import AgentProfile

    result = _empty()
    member = (await db.execute(
        select(MamifyMember.mamify_customer_id, MamifyMember.email)
        .join(AgentProfile, AgentProfile.id == MamifyMember.agent_id)
        .where(AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id,
               MamifyMember.organization_id == organization_id)
    )).first()
    if member is None or not member.mamify_customer_id:
        return result
    result["account"] = member.email
    key = (organization_id, str(member.mamify_customer_id))
    hit = _cache.get(key)
    if hit and not fresh and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]

    cfg = (await db.execute(select(MamifyConfig).where(MamifyConfig.organization_id == organization_id))).scalar_one_or_none()
    if cfg is None or not cfg.enabled or not cfg.api_key:
        return result
    try:
        answer = await mamify_service.client_for(cfg).call(
            "plugins/mamify/rag/customer/wallets", {"customer_id": int(member.mamify_customer_id)})
    except (MamifyApiError, ValueError) as exc:
        if hit:  # Mamify is busy or down: the last balances, with their time.
            return {**hit[1], "error": str(exc)}
        return {**result, "error": str(exc)}
    out = {**result, **parse_wallets(answer), "connected": True, "updated_at": utcnow().isoformat()}
    _cache[key] = (time.monotonic(), out)
    return out
