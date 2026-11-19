"""Show or change the optional features from the command line.

The same switches as admin → Sistema → Impostazioni → Funzioni
(organizations/service.py::FEATURE_DEFAULTS), for when the dashboard is not
at hand. Every change is written to the audit log.

Usage (inside the api container):
    python -m app.seed.features --organization-name SOSNET                 # show
    python -m app.seed.features --organization-name SOSNET --enable all    # everything on
    python -m app.seed.features --organization-name SOSNET --defaults      # back to the defaults
    python -m app.seed.features --organization-name SOSNET --enable wallet welcome_bonus
    python -m app.seed.features --organization-name SOSNET --disable dropshipping
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.foundation.db import AsyncSessionLocal
from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.registry import load_model_metadata

LABELS = {
    "dropshipping": "Shop dropshipping (CJ, Shopify, AliExpress)",
    "wallet": "Portafoglio SosnetCash",
    "invoice_cashback": "Incassa il cashback (riscatto fatture)",
    "welcome_bonus": "Omaggio di benvenuto",
    "friend_referrals": "Porta un amico",
    "profile_gate": "Profilo obbligatorio al primo accesso",
    "external_wallet": "Saldi MAMIX / CASHBACK (wallet partner)",
}


def _names(values: list[str]) -> list[str]:
    if values == ["all"]:
        return list(organizations_service.FEATURES)
    unknown = [v for v in values if v not in organizations_service.FEATURES]
    if unknown:
        raise SystemExit(f"Funzioni sconosciute: {', '.join(unknown)}. Valide: {', '.join(organizations_service.FEATURES)}, all")
    return values


async def run(organization_name: str, enable: list[str], disable: list[str], defaults: bool) -> int:
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.name == organization_name))).scalars().first()
        if org is None:
            print(f"Organizzazione «{organization_name}» non trovata.", file=sys.stderr)
            return 1
        changes: dict[str, bool] = {}
        if defaults:
            changes.update(organizations_service.FEATURE_DEFAULTS)
        changes.update({name: True for name in _names(enable)} if enable else {})
        changes.update({name: False for name in _names(disable)} if disable else {})
        if changes:
            await organizations_service.update_features(
                db, organization_id=org.id, changes=changes, actor_user_id=None,
            )
        switches = await organizations_service.get_feature_switches(db, organization_id=org.id)
        effective = await organizations_service.get_features(db, organization_id=org.id)
    for name in organizations_service.FEATURES:
        state = "ACCESA" if switches[name] else "spenta"
        note = "" if switches[name] == effective[name] else f"  (inattiva: serve anche «{organizations_service.FEATURE_REQUIRES[name]}»)"
        print(f"  {name:<18} {state:<7} {LABELS.get(name, '')}{note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed.features")
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--enable", nargs="+", default=[], metavar="FUNZIONE")
    parser.add_argument("--disable", nargs="+", default=[], metavar="FUNZIONE")
    parser.add_argument("--defaults", action="store_true", help="riporta tutte le funzioni al valore predefinito")
    args = parser.parse_args(argv)
    load_model_metadata()
    return asyncio.run(run(args.organization_name, args.enable, args.disable, args.defaults))


if __name__ == "__main__":
    sys.exit(main())
