from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from gonzo_pit_strategy.db.base import Base


class TrainingMetric(Base):
    __tablename__ = 'training_metrics'

    metric_id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('f1db.training_runs.run_id', ondelete='CASCADE'), nullable=False)
    epoch = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=func.current_timestamp())
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    split_type = Column(String(20))

    __table_args__ = (
        CheckConstraint("split_type IN ('TRAIN', 'VALIDATION', 'TEST')"),
        {'schema': 'f1db'},
    )

    def __repr__(self):
        return f"<TrainingMetric(metric_id={self.metric_id}, run_id={self.run_id}, metric_name='{self.metric_name}', metric_value={self.metric_value})>"