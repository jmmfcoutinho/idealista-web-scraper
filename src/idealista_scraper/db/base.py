"""SQLAlchemy base and engine configuration.

This module provides the SQLAlchemy declarative base, engine factory,
and session factory for the Idealista scraper database.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Callable


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class for all ORM models."""

    pass


def create_engine_from_url(url: str) -> Engine:
    """Create a SQLAlchemy engine from a database URL.

    Automatically creates the directory for SQLite databases if it
    doesn't exist.

    Args:
        url: Database connection URL (e.g., "sqlite:///./data/idealista.db").

    Returns:
        A configured SQLAlchemy Engine instance.
    """
    # For SQLite, ensure the directory exists
    if url.startswith("sqlite:///"):
        # Extract path from sqlite:///path format
        db_path_str = url.replace("sqlite:///", "")
        # Handle relative paths (./path or path)
        if db_path_str.startswith("./"):
            db_path_str = db_path_str[2:]
        db_path = Path(db_path_str)
        if db_path.parent != Path(".") and db_path.parent != Path(""):
            db_path.parent.mkdir(parents=True, exist_ok=True)

    return create_engine(url, echo=False)


def get_session_factory(url: str) -> Callable[[], Session]:
    """Create a session factory for the given database URL.

    Args:
        url: Database connection URL.

    Returns:
        A sessionmaker instance that can be called to create new sessions.
    """
    engine = create_engine_from_url(url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(url: str) -> None:
    """Create all tables for the configured database URL if they do not exist.

    This function creates the database schema based on all models that
    inherit from Base.

    Args:
        url: Database connection URL.
    """
    # Import models to ensure they are registered with Base
    from idealista_scraper.db import models  # noqa: F401

    engine = create_engine_from_url(url)
    Base.metadata.create_all(engine)
