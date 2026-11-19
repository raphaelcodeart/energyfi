"""Declarative registry of application modules.

One entry per module in `MODULES`; adding a module is one line.

  * `name`    — package under `app.modules`.
  * `models`  — whether to import `<name>.models`. This only populates
                `Base.metadata`, but a missing import makes Alembic
                autogenerate propose dropping that module's tables.
  * `routers` — `(module, attribute)` pairs to mount. Most modules expose
                `router.py:router`; `contracts` and `referral` expose two.

Order matters: FastAPI matches routes in mount order, so if two modules ever
share a prefix, this list decides which wins.
"""

from dataclasses import dataclass, field
from importlib import import_module

from fastapi import APIRouter, FastAPI

#: Prefix for every route. nginx sends `/api/*` to the dashboard BFF except
#: the paths it routes here; changing it requires updating nginx.conf too.
API_PREFIX = "/api"


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    models: bool = True
    routers: tuple[tuple[str, str], ...] = (("router", "router"),)


def _m(name: str, *, models: bool = True, routers: tuple[tuple[str, str], ...] | None = None) -> ModuleSpec:
    """Compact ModuleSpec constructor for the list below."""
    return ModuleSpec(name=name, models=models, routers=routers if routers is not None else (("router", "router"),))


#: For modules that expose models and services but no routes.
_MODELS_ONLY: tuple[tuple[str, str], ...] = ()

MODULES: tuple[ModuleSpec, ...] = (
    _m("auth"),
    _m("accounting", models=False),
    _m("network"),
    _m("commercial"),
    _m("leads"),
    _m("referral", routers=(("router", "router"), ("router", "authenticated_router"))),
    _m("contracts", routers=(("router", "router"), ("requests_router", "router"))),
    _m("commissions"),
    _m("affiliate"),
    _m("mamify"),
    _m("customers"),
    _m("catalog"),
    _m("carts"),
    _m("reports", models=False),
    _m("support"),
    _m("documents"),
    _m("notifications"),
    _m("documentation"),
    _m("wallets"),
    _m("external_wallet", models=False),
    _m("partners"),
    _m("invoice_redemptions"),
    _m("orders"),
    _m("imported_products"),
    _m("cj_dropshipping"),
    _m("shopify_dropshipping"),
    _m("aliexpress_dropshipping"),
    _m("sosnet_market"),
    _m("marketplaces"),
    _m("shop_categories"),
    _m("friend_referrals"),
    _m("organizations"),
    _m("integrations", models=False),
    _m("payments"),
    _m("users"),
    # Models only, no routes.
    _m("audit", routers=_MODELS_ONLY),
    _m("outbox", routers=_MODELS_ONLY),
    _m("rbac", routers=_MODELS_ONLY),
)


def load_model_metadata() -> None:
    """Import the `models` of every module that declares one.

    Required wherever the full schema must be visible: the app at startup
    and `alembic/env.py`, where missing tables would be treated as dropped.
    """
    for spec in MODULES:
        if spec.models:
            import_module(f"app.modules.{spec.name}.models")


def mount_routers(app: FastAPI, *, prefix: str = API_PREFIX) -> list[str]:
    """Mount every module's routers in declared order.

    Returns the mounted names so `tests/test_module_registry.py` can check
    the registry against the modules actually on disk.
    """
    mounted: list[str] = []
    for spec in MODULES:
        for module_name, attribute in spec.routers:
            module = import_module(f"app.modules.{spec.name}.{module_name}")
            router = getattr(module, attribute)
            if not isinstance(router, APIRouter):
                raise TypeError(
                    f"app.modules.{spec.name}.{module_name}.{attribute} non e' un APIRouter"
                )
            app.include_router(router, prefix=prefix)
            mounted.append(f"{spec.name}.{module_name}.{attribute}")
    return mounted
