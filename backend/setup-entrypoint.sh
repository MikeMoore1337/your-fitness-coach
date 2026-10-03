#!/usr/bin/env bash
set -e

python - <<'PY'
import time
from sqlalchemy import create_engine, text
from fitminiapp_api.core.config import settings

for attempt in range(60):
    try:
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready")
        break
    except Exception as exc:
        print(f"Waiting for database ({attempt + 1}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit("Database did not become ready in time")
PY

PGOPTIONS="${YFC_MIGRATION_PGOPTIONS:-}" alembic upgrade head
python -m fitminiapp_api.services.seed
