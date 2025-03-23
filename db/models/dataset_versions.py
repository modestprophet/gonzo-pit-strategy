from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from db.base import Base


class DatasetVersion(Base):
    __tablename__ = 'dataset_versions'

    dataset_version_id = Column(Integer, primary_key=True)
    dataset_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, nullable=False, default=func.current_timestamp())
    created_by = Column(String(100))
    data_path = Column(String(255))
    record_count = Column(Integer)
    feature_count = Column(Integer)
    preprocessing_steps = Column(ARRAY(Text))

    __table_args__ = (
        UniqueConstraint('dataset_name', 'version', name='uix_dataset_name_version'),
    )

    def __repr__(self):
        return f"<DatasetVersion(dataset_version_id={self.dataset_version_id}, dataset_name='{self.dataset_name}', version='{self.version}')>"