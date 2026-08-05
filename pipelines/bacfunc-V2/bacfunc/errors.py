"""BacFunc exception hierarchy."""

from __future__ import annotations


class BacargError(RuntimeError):
    """Base class for user-facing pipeline failures."""


class ConfigurationError(BacargError):
    """Raised when deployment configuration is invalid."""


class DatabaseConfigurationError(ConfigurationError):
    """Raised when a required database is unavailable or invalid."""


class InputValidationError(BacargError):
    """Raised when sequence input is unsafe or malformed."""


class ExternalToolError(BacargError):
    """Raised when an external command fails."""


class ParseError(BacargError):
    """Raised when an external data file cannot be parsed safely."""
