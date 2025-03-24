"""
Logging module for the Gonzo Pit Strategy app.

This module provides console and database logging capabilities.

Example usage:
    from gonzo_pit_strategy.log import get_console_logger, get_db_logger

    # For simple console logging
    logger = get_console_logger(__name__)
    logger.info("This is an informational message")
    logger.error("This is an error message")

    # For database logging
    db_logger = get_db_logger(__name__, component="data_processing")
    db_logger.info("Started processing data")
    db_logger.error("Failed to process data")
"""

from .logger import get_console_logger, get_db_logger

__all__ = ['get_console_logger', 'get_db_logger']