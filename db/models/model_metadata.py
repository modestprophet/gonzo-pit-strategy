from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func
from db.base import Base


class ModelMetadata(Base):
    __tablename__ = 'model_metadata'

    model_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, nullable=False, default=func.current_timestamp())
    created_by = Column(String(100))
    architecture = Column(Text)
    framework_version = Column(String(50))
    repository_link = Column(String(255))
    tags = Column(ARRAY(Text))
    configuration = Column(JSONB)
    config_source_path = Column(String(255))

    __table_args__ = (
        UniqueConstraint('name', 'version', name='uix_name_version'),
        {'schema': 'f1db'},
    )

    def __repr__(self):
        return f"<ModelMetadata(model_id={self.model_id}, name='{self.name}', version='{self.version}')>"