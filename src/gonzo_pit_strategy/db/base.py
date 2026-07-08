"""
SQLAlchemy base models and session context management.

This module provides the base model class and session context manager
for database operations.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import Session

from .connection_pool import ConnectionPool

import logging
logger = logging.getLogger(__name__)


Base = declarative_base()


@contextmanager
def db_session(pool: ConnectionPool) -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Yields:
        An SQLAlchemy session

    Example:
        with db_session(pool) as session:
            users = session.query(User).all()
    """
    session = pool.get_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()
