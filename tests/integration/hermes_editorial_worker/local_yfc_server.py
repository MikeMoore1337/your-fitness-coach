"""Start the real YFC FastAPI intake contract for a local-only E2E test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

workspace = Path(os.environ["YFC_WORKSPACE"]).resolve()
sys.path.insert(0, str(workspace / "backend"))

# Import every model before create_all so the test database has the same metadata
# as the application. Configuration is supplied by the parent process.
from fitminiapp_api import models  # noqa: F401,E402
from fitminiapp_api.db.base import Base  # noqa: E402
from fitminiapp_api.db.session import SessionLocal, engine  # noqa: E402
from fitminiapp_api.models.news import NewsSource  # noqa: E402

Base.metadata.create_all(bind=engine)
with SessionLocal() as session:
    source_id = os.environ.get("YFC_LOCAL_SOURCE_ID", "journal-one")
    if session.get(NewsSource, source_id) is None:
        session.add(
            NewsSource(
                id=source_id,
                name="Journal One local fixture",
                source_type="primary_research",
                fetch_kind="rss",
                feed_url="https://example.com/feed",
                language="en",
                enabled=True,
                trust_notes="Bounded local fixture only",
                licensing_notes="No external retrieval is performed",
            )
        )
        session.commit()


import uvicorn  # noqa: E402

uvicorn.run(
    "fitminiapp_api.main:app",
    host=os.environ.get("YFC_LOCAL_HOST", "0.0.0.0"),
    port=int(os.environ["YFC_LOCAL_PORT"]),
    log_level="warning",
    access_log=False,
)
