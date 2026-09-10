import asyncio
import os
import re
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

if sys.platform == "win32":
    # The default Proactor loop allocates a TCP socket pair for every TestClient
    # portal. The selector loop avoids exhausting the Windows ephemeral socket
    # pool during the parallel local fallback; Linux CI keeps its native loop.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        _selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if _selector_policy is not None:
            asyncio.set_event_loop_policy(_selector_policy())

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url

_WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")
if re.fullmatch(r"[A-Za-z0-9_]+", _WORKER_ID) is None:
    raise RuntimeError(f"unsafe pytest worker id: {_WORKER_ID!r}")

_TEST_DB = ROOT / ".artifacts" / "runtime" / "tests" / "backend" / f"fitmini_pytest-{_WORKER_ID}.db"
_TEST_DB.parent.mkdir(parents=True, exist_ok=True)
_TEST_FRONTEND_DIST = ROOT / ".artifacts" / "runtime" / "tests" / f"frontend-dist-{_WORKER_ID}"
_TEST_FRONTEND_ASSETS = _TEST_FRONTEND_DIST / "assets"
_TEST_FRONTEND_BRAND_ASSETS = _TEST_FRONTEND_ASSETS / "brand"
_TEST_FRONTEND_BRAND_ASSETS.mkdir(parents=True, exist_ok=True)
(_TEST_FRONTEND_DIST / "index.html").write_text(
    '<!doctype html><html><head><link rel="stylesheet" href="/assets/test.css"></head>'
    '<body><div id="root"></div><script src="/assets/test.js"></script></body></html>',
    encoding="utf-8",
)
(_TEST_FRONTEND_ASSETS / "test.css").write_text("#root { display: block; }", encoding="utf-8")
(_TEST_FRONTEND_ASSETS / "test.js").write_text("", encoding="utf-8")
_TEST_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cff0000004010100cdabcaac0000000049454e44ae426082"
)
for _asset_name in ("fitness-logo-v2.png", "favicon-v2.png"):
    (_TEST_FRONTEND_BRAND_ASSETS / _asset_name).write_bytes(_TEST_PNG)
_BASE_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
_WORKER_DATABASE_NAME: str | None = None

if _BASE_TEST_DATABASE_URL:
    _parsed_test_database_url = make_url(_BASE_TEST_DATABASE_URL)
    if _WORKER_ID != "main" and _parsed_test_database_url.get_backend_name() == "postgresql":
        if not _parsed_test_database_url.database:
            raise RuntimeError("PostgreSQL TEST_DATABASE_URL must include a database name")
        _WORKER_DATABASE_NAME = f"{_parsed_test_database_url.database}_{_WORKER_ID}"
        _TEST_DATABASE_URL = _parsed_test_database_url.set(
            database=_WORKER_DATABASE_NAME
        ).render_as_string(hide_password=False)
    elif _WORKER_ID != "main" and _parsed_test_database_url.get_backend_name() == "sqlite":
        database = _parsed_test_database_url.database
        if database and database != ":memory:":
            database_path = Path(database)
            worker_database_path = database_path.with_name(
                f"{database_path.stem}_{_WORKER_ID}{database_path.suffix}"
            )
            _TEST_DATABASE_URL = _parsed_test_database_url.set(
                database=worker_database_path.as_posix()
            ).render_as_string(hide_password=False)
        else:
            _TEST_DATABASE_URL = _BASE_TEST_DATABASE_URL
    else:
        _TEST_DATABASE_URL = _BASE_TEST_DATABASE_URL
else:
    _parsed_test_database_url = None
    _TEST_DATABASE_URL = f"sqlite:///{_TEST_DB.as_posix()}"

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("APP_NAME", "Your Fitness Coach Test")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-thirty-two-characters")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ.setdefault("ENABLE_DEV_AUTH", "true")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("BOT_INTERNAL_TOKEN", "test-token")
os.environ.setdefault("FRONTEND_BASE_URL", "https://app.your-fitness-coach.ru")
os.environ.setdefault("FRONTEND_DIST_DIR", str(_TEST_FRONTEND_DIST))
os.environ["NEWS_INGESTION_ENABLED"] = "false"
os.environ["NEWS_PUBLICATION_ENABLED"] = "false"

from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.base import Base
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.main import app
from fitminiapp_api.services.seed import seed_demo_data

if engine.dialect.name == "sqlite":
    # PostgreSQL sequences do not reuse primary keys after a delete. Make the
    # SQLite fallback follow that lifecycle so update tests cannot collide with
    # loaded ORM identities when a template is rebuilt.
    for _table_name in ("program_template_days", "program_template_exercises"):
        Base.metadata.tables[_table_name].dialect_options["sqlite"]["autoincrement"] = True

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def _admin_database_url(url: URL) -> URL:
    return url.set(database="postgres")


def _create_worker_database() -> None:
    if _WORKER_DATABASE_NAME is None or _parsed_test_database_url is None:
        return
    admin_engine = create_engine(
        _admin_database_url(_parsed_test_database_url),
        isolation_level="AUTOCOMMIT",
    )
    quoted_name = admin_engine.dialect.identifier_preparer.quote(_WORKER_DATABASE_NAME)
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
    finally:
        admin_engine.dispose()


def _drop_worker_database() -> None:
    if _WORKER_DATABASE_NAME is None or _parsed_test_database_url is None:
        return
    admin_engine = create_engine(
        _admin_database_url(_parsed_test_database_url),
        isolation_level="AUTOCOMMIT",
    )
    quoted_name = admin_engine.dialect.identifier_preparer.quote(_WORKER_DATABASE_NAME)
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    _create_worker_database()
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    _drop_worker_database()


def _clear_database() -> None:
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def reset_db(database_schema):
    del database_schema
    limiter.reset()
    _clear_database()
    with get_session_context() as session:
        seed_demo_data(session)
    yield
    _clear_database()


@pytest.fixture()
def client():
    return TestClient(app)
