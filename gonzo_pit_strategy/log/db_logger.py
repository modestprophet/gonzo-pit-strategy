"""
database logging function

defined outside of main logging file to avoid circular imports
when using project logging in the db portions of the codebase
"""

import traceback
from datetime import datetime
from typing import Optional

from db.base import db_session
from db.models.application_logs import ApplicationLog


def log_to_database(
        level: str,
        message: str,
        component: Optional[str] = None,
        stack_trace: Optional[str] = None,
        user_id: Optional[int] = None,
        correlation_id: Optional[str] = None
) -> None:
    """Store a log entry in the database.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        component: Component that generated the log
        stack_trace: Optional stack trace for errors
        user_id: Optional user ID associated with the log
        correlation_id: Optional correlation ID for request tracing
    """
    # Generate stack trace if not provided for errors
    if stack_trace is None and level in ("ERROR", "CRITICAL"):
        stack_trace = ''.join(traceback.format_stack())

    # Create log entry
    log_entry = ApplicationLog(
        timestamp=datetime.now(),
        level=level,
        component=component,
        message=message,
        stack_trace=stack_trace,
        user_id=user_id,
        correlation_id=correlation_id
    )

    # Store in database
    with db_session() as session:
        session.add(log_entry)