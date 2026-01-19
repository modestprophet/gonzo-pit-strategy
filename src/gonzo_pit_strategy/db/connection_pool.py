"""
Database connection pool management.

This module provides a centralized connection pool for database operations,
using SQLAlchemy's built-in connection pooling.
"""

from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from .config import DatabaseConfig

from gonzo_pit_strategy.log.logger import get_logger
logger = get_logger(__name__)


class ConnectionPool:
    """SQLAlchemy connection pool manager."""

    _instance: Optional['ConnectionPool'] = None
    _engine: Optional[Engine] = None
    _session_factory = None

    def __new__(cls, db_config: Optional[DatabaseConfig] = None):
        """Create singleton instance of ConnectionPool."""
        if cls._instance is None:
            cls._instance = super(ConnectionPool, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        """Initialize connection pool with database configuration.

        Args:
            db_config: Database configuration object
        """
        if self._initialized:
            return

        self.db_config = db_config or DatabaseConfig()
        self._create_engine()
        self._initialized = True

    def _create_engine(self) -> None:
        """Create SQLAlchemy engine with connection pool.

        This method configures the SQLAlchemy engine with the appropriate
        connection pool settings based on the configuration.
        """
        url_dict = self.db_config.get_db_url_dict()
        pool_options = self.db_config.get_pool_options()

        # Create URL object
        db_url = URL.create(**url_dict)

        logger.info(
            f"Creating database engine for {url_dict['drivername']} at {url_dict['host']}:{url_dict['port']}/{url_dict['database']}")

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
        if self._engine is None:
            self._create_engine()
        return self._engine

    def get_session(self):
        """Get a new SQLAlchemy session.

        Returns:
            SQLAlchemy Session instance

        Important:
            The caller is responsible for closing the session when done.
            Use with a context manager or try/finally block to ensure proper cleanup.
        """
        if self._session_factory is None:
            self._create_engine()
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

