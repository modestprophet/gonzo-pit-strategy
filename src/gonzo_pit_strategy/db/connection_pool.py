"""
Database connection pool management.

This module provides a connection pool for database operations,
using SQLAlchemy's built-in connection pooling.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from gonzo_pit_strategy.config.config import DatabaseConfig

import logging
logger = logging.getLogger(__name__)


class ConnectionPool:
    """SQLAlchemy connection pool manager."""

    def __init__(self, db_config: DatabaseConfig):
        """Initialize connection pool with database configuration.

        Args:
            db_config: Database configuration object
        """
        self.db_config = db_config
        self._engine = None
        self._session_factory = None
        self._create_engine()

    def _create_engine(self) -> None:
        """Create SQLAlchemy engine with connection pool."""
        pool_options = self.db_config.get_pool_options()

        # Create URL object
        db_url = self.db_config.get_db_url()

        logger.info(
            f"Creating database engine for {db_url.drivername} at {db_url.host}:{db_url.port}/{db_url.database}")

        # Create engine with pooling
        self._engine = create_engine(
            db_url,
            poolclass=QueuePool,
            **pool_options,
            echo=False,  # Set to True for SQL query logging (dev only)
        )

        # Create session factory
        self._session_factory = scoped_session(
            sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine
            )
        )
        logger.debug("Database engine and session factory created successfully")

    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine instance.

        Returns:
            SQLAlchemy Engine instance
        """
        return self._engine

    def get_session(self):
        """Get a new SQLAlchemy session.

        Returns:
            SQLAlchemy Session instance

        Important:
            The caller is responsible for closing the session when done.
            Use with a context manager or try/finally block to ensure proper cleanup.
        """
        return self._session_factory()

    def dispose(self) -> None:
        """Dispose of the connection pool.

        Call this method during application shutdown to cleanly close connections.
        """
        if self._engine is not None:
            logger.info("Disposing database connection pool")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
