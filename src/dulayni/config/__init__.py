"""Configuration management module for dulayni-client."""

from .manager import ConfigManager
from .templates import DEFAULT_CONFIG_TEMPLATE, DULAYNI_CONFIG_TEMPLATE, DEFAULT_GITIGNORE

__all__ = [
    "ConfigManager",
    "DEFAULT_CONFIG_TEMPLATE",
    "DULAYNI_CONFIG_TEMPLATE", 
    "DEFAULT_GITIGNORE"
]