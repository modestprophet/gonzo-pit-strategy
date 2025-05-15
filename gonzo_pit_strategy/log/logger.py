"""
Unified logging system for the pit strategy project

Supports three output types:
- Console logging (stdout)
- File logging (in logs directory)
- Database logging (postgres)

Configure via config/logging.json
"""

import json
import logging
import os
import sys
import traceback
from typing import Dict, Optional, Any

from config.config import config


class Logger:
    """Central logger that can output to console, file, and/or database."""

    def __init__(self, name: str, config_name: str = "logging"):
        """Initialize a logger with the given name.

        Args:
            name: Logger name (usually __name__)
            config_name: Name of the configuration to use
        """
        self.name = name
        self.config = config.get_config(config_name)
        self._logger = logging.getLogger(name)
        self._setup_logger()

    def _setup_logger(self) -> None:
        """Configure the logger based on configuration settings."""
        # Clear any existing handlers
        if self._logger.handlers:
            self._logger.handlers.clear()

        self._logger.propagate = False

        # Get logger-specific settings or fall back to default
        logger_config = self._get_logger_config()

        # Set log level
        level_name = logger_config.get("level", "INFO")
        self._logger.setLevel(getattr(logging, level_name))

        # Add handlers based on type
        log_types = logger_config.get("type", ["console"])
        if not isinstance(log_types, list):
            log_types = [log_types]

        for log_type in log_types:
            if log_type == "console":
                self._add_console_handler(logger_config)
            elif log_type == "file":
                self._add_file_handler(logger_config)
            elif log_type == "database":
                # Database handler is special - we'll handle it in the logging methods
                pass

    def _get_logger_config(self) -> Dict[str, Any]:
        """Get configuration for this specific logger.

        Returns:
            Logger configuration dict
        """
        # Start with global defaults
        result = {
            "level": self.config.get("level", "INFO"),
            "type": self.config.get("type", ["console"]),
            "format": self.config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        }

        # Check for logger-specific settings
        loggers_config = self.config.get("loggers", {})

        # Check for exact match
        if self.name in loggers_config:
            # Update with logger-specific settings
            result.update(loggers_config[self.name])
            return result

        # Check for parent loggers (hierarchical)
        parts = self.name.split('.')
        while len(parts) > 1:
            parts.pop()  # Remove last component
            parent_name = '.'.join(parts)
            if parent_name in loggers_config:
                result.update(loggers_config[parent_name])
                return result

        return result

    def _add_console_handler(self, logger_config: Dict[str, Any]) -> None:
        """Add console handler to the logger.

        Args:
            logger_config: Configuration for this logger
        """
        handler = logging.StreamHandler(sys.stdout)
        format_str = logger_config.get("format",
                                      "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        formatter = logging.Formatter(format_str)
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def _add_file_handler(self, logger_config: Dict[str, Any]) -> None:
        """Add file handler to the logger.

        Args:
            logger_config: Configuration for this logger
        """
        # Create logs directory if it doesn't exist
        logs_dir = config.get_path("logs")
        os.makedirs(logs_dir, exist_ok=True)

        # Configure file handler
        # filename = self.name.replace('.', '_')
        # log_file = logger_config.get("file", f"{filename}.log")
        log_file = logger_config.get("file", f"logfile.log")
        file_path = logs_dir / log_file

        handler = logging.FileHandler(file_path)
        format_str = logger_config.get("format",
                                      "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        formatter = logging.Formatter(format_str)
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def _should_log_to_db(self, logger_config: Dict[str, Any], level: int) -> bool:
        """Check if this message should be logged to the database.

        Args:
            logger_config: Configuration for this logger
            level: Log level of the message

        Returns:
            True if the message should be logged to the database
        """
        log_types = logger_config.get("type", ["console"])
        if not isinstance(log_types, list):
            log_types = [log_types]

        if "database" not in log_types:
            return False

        # Check database-specific level if available
        db_config = self.config.get("database", {})
        if not db_config.get("enabled", True):
            return False

        db_level_name = db_config.get("level", logger_config.get("level", "INFO"))
        db_level = getattr(logging, db_level_name)

        return level >= db_level

    def _log_to_db(self, level_name: str, message: str, stack_trace: Optional[str] = None,
                  component: Optional[str] = None, user_id: Optional[int] = None,
                  correlation_id: Optional[str] = None) -> None:
        """Log a message to the database.

        Args:
            level_name: Log level name
            message: Log message
            stack_trace: Optional stack trace for errors
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        try:
            # Import here to avoid circular imports
            from gonzo_pit_strategy.log.db_logger import log_to_database

            log_to_database(
                level=level_name,
                message=message,
                component=component or self.name,
                stack_trace=stack_trace,
                user_id=user_id,
                correlation_id=correlation_id
            )
        except Exception as e:
            # If database logging fails, log to console as fallback
            fallback_logger = logging.getLogger(f"{self.name}_db_fallback")
            if not fallback_logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                fallback_logger.addHandler(handler)
                fallback_logger.setLevel(logging.ERROR)

            fallback_logger.error(f"Failed to log to database: {str(e)}")
            fallback_logger.error(f"Original message: {message}")

    def debug(self, message: str, component: Optional[str] = None,
             user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a debug message.

        Args:
            message: Log message
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        self._logger.debug(message)

        # Check if we should also log to database
        logger_config = self._get_logger_config()
        if self._should_log_to_db(logger_config, logging.DEBUG):
            self._log_to_db("DEBUG", message, component=component,
                           user_id=user_id, correlation_id=correlation_id)

    def info(self, message: str, component: Optional[str] = None,
            user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log an info message.

        Args:
            message: Log message
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        self._logger.info(message)

        # Check if we should also log to database
        logger_config = self._get_logger_config()
        if self._should_log_to_db(logger_config, logging.INFO):
            self._log_to_db("INFO", message, component=component,
                           user_id=user_id, correlation_id=correlation_id)

    def warning(self, message: str, component: Optional[str] = None,
               user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a warning message.

        Args:
            message: Log message
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        self._logger.warning(message)

        # Check if we should also log to database
        logger_config = self._get_logger_config()
        if self._should_log_to_db(logger_config, logging.WARNING):
            self._log_to_db("WARNING", message, component=component,
                           user_id=user_id, correlation_id=correlation_id)

    def error(self, message: str, exc_info: bool = False, component: Optional[str] = None,
             user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log an error message.

        Args:
            message: Log message
            exc_info: Whether to include exception info
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        self._logger.error(message, exc_info=exc_info)

        # Check if we should also log to database
        logger_config = self._get_logger_config()
        if self._should_log_to_db(logger_config, logging.ERROR):
            stack_trace = traceback.format_exc() if exc_info and sys.exc_info()[0] else None
            self._log_to_db("ERROR", message, stack_trace=stack_trace,
                           component=component, user_id=user_id,
                           correlation_id=correlation_id)

    def critical(self, message: str, exc_info: bool = False, component: Optional[str] = None,
                user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a critical message.

        Args:
            message: Log message
            exc_info: Whether to include exception info
            component: Optional component name
            user_id: Optional user ID
            correlation_id: Optional correlation ID for request tracing
        """
        self._logger.critical(message, exc_info=exc_info)

        # Check if we should also log to database
        logger_config = self._get_logger_config()
        if self._should_log_to_db(logger_config, logging.CRITICAL):
            stack_trace = traceback.format_exc() if exc_info and sys.exc_info()[0] else None
            self._log_to_db("CRITICAL", message, stack_trace=stack_trace,
                           component=component, user_id=user_id,
                           correlation_id=correlation_id)


# Convenience function to get a logger
def get_logger(name: str, config_name: str = "logging") -> Logger:
    """Get a logger for the specified name.

    Args:
        name: Logger name (usually __name__)
        config_name: Name of the configuration to use

    Returns:
        Configured logger instance
    """
    return Logger(name, config_name)


def get_db_logger(name: str, component: Optional[str] = None, config_name: str = "logging") -> Logger:
    """Get a logger configured for database logging.

    This creates a logger that's specifically set up to log to the database.

    Args:
        name: Logger name (usually __name__)
        component: Optional component name to use in log entries
        config_name: Name of the configuration to use

    Returns:
        Configured logger instance with database logging enabled
    """
    logger = Logger(name, config_name)
    # Force database logging for this logger
    logger.config.setdefault("loggers", {})
    logger.config["loggers"].setdefault(name, {})
    logger.config["loggers"][name]["type"] = ["console", "database"]
    logger._setup_logger()  # Re-setup with new config
    return logger
