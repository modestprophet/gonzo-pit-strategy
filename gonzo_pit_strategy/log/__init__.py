"""
Logging module for the Gonzo Pit Strategy app.

This module provides console and file logging capabilities.

Example usage:
    from gonzo_pit_strategy.log import get_logger

    # For simple console logging
    logger = get_logger(__name__)
    logger.info("This is an informational message")
    logger.error("This is an error message")
"""

from .logger import get_logger

__all__ = ['get_logger']