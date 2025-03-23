from sqlalchemy import Column, Integer, String, Text, DateTime, CheckConstraint, Index
from sqlalchemy.sql import func
from db.base import Base


class ApplicationLog(Base):
    __tablename__ = 'application_logs'

    log_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=func.current_timestamp())
    level = Column(String(10), nullable=False)
    component = Column(String(100))
    message = Column(Text, nullable=False)
    stack_trace = Column(Text)
    user_id = Column(Integer)
    correlation_id = Column(String(100))
    created_at = Column(DateTime, nullable=False, default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')"),
        Index('idx_app_logs_timestamp', timestamp),
        Index('idx_app_logs_level', level),
    )

    def __repr__(self):
        return f"<ApplicationLog(log_id={self.log_id}, timestamp='{self.timestamp}', level='{self.level}')>"