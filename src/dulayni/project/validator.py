"""Project validation utilities."""

from pathlib import Path
from ..config.manager import ConfigManager


class ProjectValidator:
    """Validates dulayni project state and configuration."""

    @staticmethod
    def is_project_initialized() -> bool:
        """Check if the current directory is already initialized as a dulayni project."""
        config_file = Path("config/config.json")
        return config_file.exists()

    @staticmethod
    def is_project_initialized_with_auth() -> bool:
        """Check if project is initialized and has authentication configured."""
        return (ProjectValidator.is_project_initialized() and 
                ConfigManager.has_authentication_method())