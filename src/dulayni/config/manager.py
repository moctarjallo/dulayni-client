"""Configuration file management and utilities."""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Handles configuration file operations and management."""
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    
                    # Handle Dulayni API key from file
                    if "dulayni_api_key_file" in config:
                        key_file_path = config["dulayni_api_key_file"]
                        key_file = Path(key_file_path)
                        if key_file.exists():
                            config["dulayni_api_key"] = key_file.read_text().strip()
                    
                    return config
            else:
                return {}
        except json.JSONDecodeError:
            return {}
        except Exception:
            return {}

    @staticmethod
    def merge_config_with_args(config: Dict[str, Any], **cli_args) -> Dict[str, Any]:
        """Merge configuration with CLI arguments, giving priority to CLI args."""
        merged = {}

        def add_if_not_none(key: str, value: Any) -> None:
            if value is not None:
                merged[key] = value

        # Agent configuration
        agent_config = config.get("agent", {})
        add_if_not_none("model", cli_args.get("model") or agent_config.get("model"))
        add_if_not_none(
            "agent_type", cli_args.get("agent_type") or agent_config.get("agent_type")
        )
        add_if_not_none(
            "system_prompt",
            cli_args.get("system_prompt") or agent_config.get("system_prompt"),
        )

        # Memory configuration
        memory_config = config.get("memory", {})
        add_if_not_none(
            "memory_db", cli_args.get("memory_db") or memory_config.get("memory_db")
        )
        add_if_not_none("pg_uri", cli_args.get("pg_uri") or memory_config.get("pg_uri"))
        add_if_not_none(
            "thread_id", cli_args.get("thread_id") or memory_config.get("thread_id")
        )

        # MCP servers configuration
        mcp_servers = config.get("mcpServers")
        if mcp_servers:
            merged["mcp_servers"] = mcp_servers

        # API configuration
        add_if_not_none("api_url", cli_args.get("api_url") or config.get("api_url"))

        # Authentication configuration
        add_if_not_none("phone_number", config.get("phone_number"))
        add_if_not_none("dulayni_api_key", cli_args.get("dulayni_api_key") or config.get("dulayni_api_key"))

        # CLI-only arguments
        add_if_not_none("query", cli_args.get("query"))
        add_if_not_none("print_mode", cli_args.get("print_mode"))

        return merged

    @staticmethod
    def get_phone_number_from_config(config_path: str = "config/config.json") -> Optional[str]:
        """Extract phone number from existing config file."""
        config = ConfigManager.load_config(config_path)
        return config.get("phone_number")

    @staticmethod
    def get_dulayni_key_from_config(config_path: str = "config/config.json") -> Optional[str]:
        """Extract Dulayni API key from config or key file."""
        config = ConfigManager.load_config(config_path)
        # Check if key is directly in config
        if "dulayni_api_key" in config:
            return config["dulayni_api_key"]
        # Check if key file is specified
        key_file_path = config.get("dulayni_api_key_file")
        if key_file_path:
            key_file = Path(key_file_path)
            if key_file.exists():
                return key_file.read_text().strip()
        return None

    @staticmethod
    def has_authentication_method(config_path: str = "config/config.json") -> bool:
        """Check if project has either phone number or Dulayni API key configured."""
        return bool(
            ConfigManager.get_phone_number_from_config(config_path) or 
            ConfigManager.get_dulayni_key_from_config(config_path)
        )