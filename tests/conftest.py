"""Pytest fixtures.

Each test gets a FastAPI ``TestClient`` bound to a throwaway SQLite file so the
suite never touches the real ``clause_ledger.db``. We point the config at a temp
path *before* importing the app module (whose ``create_app`` bootstraps the DB).
"""

import importlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["CLAUSE_LEDGER_DB"] = db_path

    # Reload config + modules so they pick up the temp DB path.
    import app.config as config_module

    importlib.reload(config_module)
    import app.database as database_module

    importlib.reload(database_module)
    import app.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client

    os.remove(db_path)
    os.environ.pop("CLAUSE_LEDGER_DB", None)
