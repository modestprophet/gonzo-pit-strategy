# db/repositories/base_repository.py
"""
Base repository interface for database access.

This module provides a generic base repository pattern implementation
for database model operations.
"""

import logging
from typing import TypeVar, Generic, Type, List, Optional, Any

from ..base import Base, db_session

logger = logging.getLogger(__name__)

# Type variable for models
T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    """Base repository implementation for SQLAlchemy models."""

    def __init__(self, model_class: Type[T]):
        """Initialize repository with model class.

        Args:
            model_class: SQLAlchemy model class
        """
        self.model_class = model_class

    def get_by_id(self, id_value: Any) -> Optional[T]:
        """Get entity by its primary key.

        Args:
            id_value: Primary key value

        Returns:
            Entity if found, None otherwise
        """
        with db_session() as session:
            return session.query(self.model_class).get(id_value)

    def get_all(self) -> List[T]:
        """Get all entities.

        Returns:
            List of all entities
        """
        with db_session() as session:
            return session.query(self.model_class).all()

    def create(self, **kwargs) -> T:
        """Create a new entity.

        Args:
            **kwargs: Entity attributes

        Returns:
            Created entity
        """
        with db_session() as session:
            entity = self.model_class(**kwargs)
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity

    def update(self, id_value: Any, **kwargs) -> Optional[T]:
        """Update an entity by its primary key.

        Args:
            id_value: Primary key value
            **kwargs: Entity attributes to update

        Returns:
            Updated entity if found, None otherwise
        """
        with db_session() as session:
            entity = session.query(self.model_class).get(id_value)
            if entity is None:
                return None

            for key, value in kwargs.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)

            session.commit()
            session.refresh(entity)
            return entity

    def delete(self, id_value: Any) -> bool:
        """Delete an entity by its primary key.

        Args:
            id_value: Primary key value

        Returns:
            True if deleted, False if not found
        """
        with db_session() as session:
            entity = session.query(self.model_class).get(id_value)
            if entity is None:
                return False

            session.delete(entity)
            session.commit()
            return True

