"""
Database connection management.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import config
from .app_models import AppBase
from .models import CorpusBase

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that provides a transactional session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Create corpus tables and enable required extensions.

    Application metadata is managed separately by Alembic (or ``init_app_db``
    for disposable local/test databases).
    """
    engine = get_engine()

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    CorpusBase.metadata.create_all(engine)
    logger.info("Corpus database initialized")


def init_app_db() -> None:
    """Create application metadata tables without touching corpus data."""
    AppBase.metadata.create_all(get_engine())
    logger.info("Application metadata database initialized")


def drop_corpus_tables() -> None:
    """Drop only replaceable scientific corpus tables."""
    engine = get_engine()
    CorpusBase.metadata.drop_all(engine)
    logger.warning("Corpus tables dropped; application metadata was preserved")


def drop_all() -> None:
    """Backward-compatible safe alias for the historical corpus reset."""
    drop_corpus_tables()
