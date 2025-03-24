"""
SQLAlchemy base models and session context management.

This module provides the base model class and session context manager
for database operations.
"""
from contextlib import contextmanager
from typing import Generator, TypeVar

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from .connection_pool import ConnectionPool

from gonzo_pit_strategy.log.logger import get_console_logger
logger = get_console_logger(__name__)


# Create base model class
Base = declarative_base()

# Type variable for models
T = TypeVar('T', bound=Base)


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Yields:
        An SQLAlchemy session

    Example:
        with db_session() as session:
            users = session.query(User).all()
    """
    pool = ConnectionPool()
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

