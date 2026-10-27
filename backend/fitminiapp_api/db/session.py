from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.performance import install_sql_metrics

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = (
    {"check_same_thread": False}
    if is_sqlite
    else {"application_name": settings.db_application_name}
)
engine_options = (
    {}
    if is_sqlite
    else {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }
)
engine = create_engine(
    settings.database_url,
    future=True,
    connect_args=connect_args,
    **engine_options,
)
install_sql_metrics(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_session_context():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
