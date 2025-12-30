"""
Unified logging system for the pit strategy project

Supports two output types:
- Console logging (stdout)
- File logging (in logs directory)

Configure via config/logging.json
"""

import logging
import os
import sys
from typing import Dict, Any, Optional

from config.config import config


class Logger:
    """Central logger that can output to console and file."""

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

    def debug(self, message: str, component: Optional[str] = None,
             user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a debug message.

        Args:
            message: Log message
            component: Optional component name (ignored)
            user_id: Optional user ID (ignored)
            correlation_id: Optional correlation ID (ignored)
        """
        self._logger.debug(message)

    def info(self, message: str, component: Optional[str] = None,
            user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log an info message.

        Args:
            message: Log message
            component: Optional component name (ignored)
            user_id: Optional user ID (ignored)
            correlation_id: Optional correlation ID (ignored)
        """
        self._logger.info(message)

    def warning(self, message: str, component: Optional[str] = None,
               user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a warning message.

        Args:
            message: Log message
            component: Optional component name (ignored)
            user_id: Optional user ID (ignored)
            correlation_id: Optional correlation ID (ignored)
        """
        self._logger.warning(message)

    def error(self, message: str, exc_info: bool = False, component: Optional[str] = None,
             user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log an error message.

        Args:
            message: Log message
            exc_info: Whether to include exception info
            component: Optional component name (ignored)
            user_id: Optional user ID (ignored)
            correlation_id: Optional correlation ID (ignored)
        """
        self._logger.error(message, exc_info=exc_info)

    def critical(self, message: str, exc_info: bool = False, component: Optional[str] = None,
                user_id: Optional[int] = None, correlation_id: Optional[str] = None) -> None:
        """Log a critical message.

        Args:
            message: Log message
            exc_info: Whether to include exception info
            component: Optional component name (ignored)
            user_id: Optional user ID (ignored)
            correlation_id: Optional correlation ID (ignored)
        """
        self._logger.critical(message, exc_info=exc_info)


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
