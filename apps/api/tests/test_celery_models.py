"""The worker imports only app.celery_app: every model must be reachable
from there, or a flush fails with NoReferencedTableError (it happened on the
first real Mamify sync). Checked in a fresh interpreter, because the test
session itself has already imported everything."""

import subprocess
import sys
from pathlib import Path

CODE = """
import app.celery_app
from sqlalchemy.orm import configure_mappers
from app.foundation.db import Base
configure_mappers()
for name in ("sn_commercial_roles", "sn_mamify_members", "sn_aff_operations"):
    assert name in Base.metadata.tables, name
print("ok")
"""


def test_worker_sees_every_model():
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-c", CODE], cwd=root, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().endswith("ok")
