"""Runtime configuration.

Values are read from environment variables so the same code can back both the
running service and the isolated test suite. Nothing here is secret; the file
only centralises defaults so the rest of the code never hard-codes paths/ports.
"""

from __future__ import annotations

import os

# The port the service listens on is fixed by the product spec.
HOST = os.getenv("CLAUSE_LEDGER_HOST", "0.0.0.0")
PORT = int(os.getenv("CLAUSE_LEDGER_PORT", "18103"))

# SQLite database location. Tests point this at a temporary file.
DB_PATH = os.getenv(
    "CLAUSE_LEDGER_DB",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "clause_ledger.db"),
)

API_PREFIX = "/api/v1"
