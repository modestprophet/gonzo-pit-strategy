"""
Global logging config for the pit strategy project

Basic stdout logging and postgres logging available.
Adjust logging levels in config/logging.json
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional, Union


class LoggerFactory:
    """Factory for creating different types of loggers."""

    _console_loggers = {}
    _db_loggers = {}
    _config = None

    @classmethod
    def _load_config(cls):
        """Load logging configuration from JSON file."""
        if cls._config is not None:
            return

        config_path = Path(__file__).parents[2] / "config" / "logging.json"
        try:
            with open(config_path, 'r') as f:
                cls._config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback to default config
            cls._config = {
                "console": {
                    "level": "INFO",
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "database": {
                    "level": "INFO",
                    "enabled": True
                }
            }

    @classmethod
    def _get_logger_level(cls, name: str) -> Optional[str]:
        """Get the configured level for a logger, respecting hierarchy.

        Args:
            name: Logger name

        Returns:
            Logging level or None if not specifically configured
        """
        # Check if this exact logger name is configured
        if "loggers" in cls._config and name in cls._config["loggers"]:
            level_name = cls._config["loggers"][name].get("level", None)
            if level_name:
                return getattr(logging, level_name)

        # Check parent loggers (hierarchical)
        parts = name.split('.')
        while parts:
            parts.pop()  # Remove last component
            if not parts:
                break

            parent_name = '.'.join(parts)
            if "loggers" in cls._config and parent_name in cls._config["loggers"]:
                level_name = cls._config["loggers"][parent_name].get("level", None)
                if level_name:
                    return getattr(logging, level_name)

        return None

    @classmethod
    def get_console_logger(cls, name: str) -> logging.Logger:
        """Get a logger that outputs to console.

        Args:
            name: Logger name (typically __name__)

        Returns:
            Configured logger instance
        """
        if name in cls._console_loggers:
            return cls._console_loggers[name]

        cls._load_config()

        # Create logger
        logger = logging.getLogger(name)
        logger.propagate = False  # Prevent double logging

        # Only add handler if not already added
        if not logger.handlers:
            # Configure console handler
            handler = logging.StreamHandler(sys.stdout)
            # Get format from config
            format_str = cls._config["console"].get("format",
                                                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            formatter = logging.Formatter(format_str)
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # Set level from config
        # Set level based on loggers configuration if available, otherwise use console default or INFO
        logger_level = cls._get_logger_level(name)
        if logger_level:
            logger.setLevel(logger_level)
        else:
            # Set level from console config as fallback
            level_name = cls._config["console"].get("level", "INFO")
            logger.setLevel(getattr(logging, level_name))

        cls._console_loggers[name] = logger
        return logger

    @classmethod
    def get_db_logger(cls, name: str, component: Optional[str] = None,
                      user_id: Optional[int] = None) -> Union['DatabaseLogger', 'logging.Logger']:
        """Get a logger that stores entries in the database.

        Args:
            name: Logger name
            component: Optional component name
            user_id: Optional user ID

        Returns:
            DatabaseLogger instance
        """
        key = f"{name}:{component}:{user_id}"
        if key in cls._db_loggers:
            return cls._db_loggers[key]

        cls._load_config()

        if not cls._config["database"].get("enabled", True):
            # If DB logging is disabled, return console logger instead
            return cls.get_console_logger(name)

        # Create DB logger
        db_logger = DatabaseLogger(name, component, user_id)

        logger_level = cls._get_logger_level(name)
        if logger_level:
            db_logger.setLevel(getattr(logging, logger_level))
        else:
            # Set level from console config as fallback
            level_name = cls._config["database"].get("level", "INFO")
            db_logger.setLevel(getattr(logging, level_name))

        cls._db_loggers[key] = db_logger
        return db_logger


class DatabaseLogger:
    """Logger that stores log entries in the database."""

    def __init__(self, name: str, component: Optional[str] = None,
                 user_id: Optional[int] = None):
        self.name = name
        self.component = component
        self.user_id = user_id
        self.level = logging.INFO
        # Also create a console logger as fallback
        self._console_logger = get_console_logger(f"{name}_db")

    def setLevel(self, level):
        """Set the logging level."""
        if isinstance(level, str):
            level = getattr(logging, level)
        self.level = level

    def _log_to_db(self, level: str, message: str, stack_trace: Optional[str] = None,
                   correlation_id: Optional[str] = None):
        """Log a message to the database."""
        try:
            # Import here to avoid circular imports
            from gonzo_pit_strategy.log.db_logger import log_to_database

            log_to_database(
                level=level,
                component=self.component,
                message=message,
                stack_trace=stack_trace,
                user_id=self.user_id,
                correlation_id=correlation_id
            )
        except Exception as e:
            # Fallback to console if DB logging fails
            self._console_logger.error(f"Failed to log to database: {str(e)}")
            self._console_logger.debug(message)

    def debug(self, message: str, correlation_id: Optional[str] = None):
        """Log a debug message."""
        if self.level <= logging.DEBUG:
            self._log_to_db("DEBUG", message, correlation_id=correlation_id)

    def info(self, message: str, correlation_id: Optional[str] = None):
        """Log an info message."""
        if self.level <= logging.INFO:
            self._log_to_db("INFO", message, correlation_id=correlation_id)

    def warning(self, message: str, correlation_id: Optional[str] = None):
        """Log a warning message."""
        if self.level <= logging.WARNING:
            self._log_to_db("WARNING", message, correlation_id=correlation_id)

    def error(self, message: str, stack_trace: Optional[str] = None,
              correlation_id: Optional[str] = None):
        """Log an error message."""
        if self.level <= logging.ERROR:
            self._log_to_db("ERROR", message, stack_trace, correlation_id)

    def critical(self, message: str, stack_trace: Optional[str] = None,
                 correlation_id: Optional[str] = None):
        """Log a critical message."""
        if self.level <= logging.CRITICAL:
            self._log_to_db("CRITICAL", message, stack_trace, correlation_id)


# These functions are the primary interface for getting loggers
def get_console_logger(name: str) -> logging.Logger:
    """Get a console logger."""
    return LoggerFactory.get_console_logger(name)


def get_db_logger(name: str,
                  component: Optional[str] = None,
                  user_id: Optional[int] = None) -> Union['DatabaseLogger', 'logging.Logger']:
    """Get a database logger."""
    return LoggerFactory.get_db_logger(name, component, user_id)