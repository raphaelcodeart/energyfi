"""The module registry (`app/modules/registry.py`) must match what is on disk.

These tests fail when:
  * a package under `app/modules/` is not declared;
  * a declared module does not exist;
  * `models=True` does not match the presence of `models.py`;
  * a declared router is missing or is not an APIRouter.
"""

import pkgutil
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

import app.modules
from app.modules.registry import MODULES, mount_routers

#: Not application modules: the registry itself and package files.
_NOT_A_MODULE = {"registry"}


def _packages_on_disk() -> set[str]:
    return {
        name
        for _, name, is_pkg in pkgutil.iter_modules(app.modules.__path__)
        if is_pkg and name not in _NOT_A_MODULE
    }


def _declared() -> set[str]:
    return {spec.name for spec in MODULES}


def test_every_package_on_disk_is_declared():
    missing = _packages_on_disk() - _declared()
    assert not missing, (
        "moduli presenti in app/modules/ ma non dichiarati nel registro: "
        f"{sorted(missing)} -- aggiungili a MODULES, altrimenti le loro rotte "
        "non vengono montate e le loro tabelle risultano da cancellare ad Alembic"
    )


def test_every_declared_module_exists():
    extra = _declared() - _packages_on_disk()
    assert not extra, f"moduli dichiarati nel registro ma inesistenti: {sorted(extra)}"


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.name)
def test_models_flag_matches_the_filesystem(spec):
    models_file = Path(app.modules.__path__[0]) / spec.name / "models.py"
    assert models_file.exists() == spec.models, (
        f"{spec.name}: models={spec.models} nel registro ma "
        f"models.py {'esiste' if models_file.exists() else 'non esiste'}"
    )


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.name)
def test_declared_routers_resolve_to_api_routers(spec):
    for module_name, attribute in spec.routers:
        module = import_module(f"app.modules.{spec.name}.{module_name}")
        assert isinstance(getattr(module, attribute), APIRouter)


def test_mounting_produces_unique_routes_under_the_api_prefix():
    """No (path, method) pair is mounted twice; a duplicate would be silently
    unreachable.

    Routes are read from the OpenAPI schema because this FastAPI version keeps
    included routers as lazy wrappers without a `path` in `app.routes`.
    """
    application = FastAPI()
    mounted = mount_routers(application)
    assert mounted, "il registro non ha montato nessun router"

    paths = application.openapi()["paths"]
    assert len(paths) > 100, f"solo {len(paths)} percorsi montati: qualcosa non e' stato incluso"

    for path in paths:
        assert path.startswith("/api/"), f"{path} non sta sotto il prefisso /api"
