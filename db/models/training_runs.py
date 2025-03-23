from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from db.base import Base


class TrainingRun(Base):
    __tablename__ = 'training_runs'

    run_id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey('model_metadata.model_id', ondelete='CASCADE'), nullable=False)
    dataset_version_id = Column(Integer, ForeignKey('dataset_versions.dataset_version_id'))
    start_time = Column(DateTime, nullable=False, default=func.current_timestamp())
    end_time = Column(DateTime)
    status = Column(String(20))
    epochs_completed = Column(Integer, default=0)
    early_stopping = Column(Boolean, default=False)
    environment_id = Column(String(100))

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')"),
    )

    def __repr__(self):
        return f"<TrainingRun(run_id={self.run_id}, model_id={self.model_id}, status='{self.status}')>"