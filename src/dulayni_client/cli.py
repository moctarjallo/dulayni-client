# cli.py
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
import click
from rich.console import Console
from rich.markdown import Markdown

from .client import DulayniClient
from .exceptions import DulayniClientError, DulayniConnectionError, DulayniTimeoutError

console = Console()


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, "r") as f:
                return json.load(f)
        else:
            console.print(
                f"[yellow]Config file {config_path} not found, using server defaults[/yellow]"
            )
            return {}
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing config file {config_path}: {e}[/red]")
        return {}
    except Exception as e:
        console.print(f"[red]Error reading config file {config_path}: {e}[/red]")
        return {}


def merge_config_with_args(config: Dict[str, Any], **cli_args) -> Dict[str, Any]:
    """Merge configuration with CLI arguments, giving priority to CLI args. Only include non-null values."""
    merged = {}

    # Helper function to add non-null values
    def add_if_not_none(key: str, value: Any) -> None:
        if value is not None:
            merged[key] = value

    # Agent configuration - only add if explicitly set
    agent_config = config.get("agent", {})
    add_if_not_none("model", cli_args.get("model") or agent_config.get("model"))
    add_if_not_none(
        "agent_type", cli_args.get("agent_type") or agent_config.get("agent_type")
    )
    add_if_not_none(
        "system_prompt",
        cli_args.get("system_prompt") or agent_config.get("system_prompt"),
    )
    add_if_not_none(
        "startup_timeout",
        cli_args.get("startup_timeout") or agent_config.get("startup_timeout"),
    )
    add_if_not_none(
        "parallel_tool_calls",
        cli_args.get("parallel_tool_calls") or agent_config.get("parallel_tool_calls"),
    )

    # Memory configuration - only add if explicitly set
    memory_config = config.get("memory", {})
    add_if_not_none(
        "memory_db", cli_args.get("memory_db") or memory_config.get("memory_db")
    )
    add_if_not_none("pg_uri", cli_args.get("pg_uri") or memory_config.get("pg_uri"))
    add_if_not_none(
        "thread_id", cli_args.get("thread_id") or memory_config.get("thread_id")
    )

    # MCP servers configuration - only add if exists in config
    mcp_servers = config.get("mcpServers")
    if mcp_servers:
        merged["mcp_servers"] = mcp_servers

    # API configuration - only add if explicitly set
    add_if_not_none("api_url", cli_args.get("api_url") or config.get("api_url"))

    # OpenAI API key handling (special case - can come from env var)
    openai_key = (
        cli_args.get("openai_api_key")
        or config.get("openai_api_key")
        or os.environ.get("OPENAI_API_KEY")
    )
    add_if_not_none("openai_api_key", openai_key)

    # CLI-only arguments
    add_if_not_none("query", cli_args.get("query"))
    add_if_not_none("print_mode", cli_args.get("print_mode"))

    return merged


@click.command()
@click.option(
    "--config",
    "-c",
    default="config/config.json",
    help="Path to configuration JSON file",
)
@click.option(
    "--model",
    "-m",
    type=click.Choice(["gpt-4o", "gpt-4o-mini"]),
    help="Model name (overrides config)",
)
@click.option(
    "--openai_api_key",
    "-k",
    help="OpenAI API key (overrides config and env var)",
)
@click.option(
    "--query", "-q", type=str, required=False, help="Query string for batch mode"
)
@click.option(
    "--memory_db",
    help="Path to SQLite database for conversation memory (overrides config)",
)
@click.option("--pg_uri", help="PostgreSQL URI for memory storage (overrides config)")
@click.option(
    "--startup_timeout",
    "-t",
    type=float,
    help="Timeout for server startup (overrides config)",
)
@click.option(
    "--parallel_tool_calls",
    "-p",
    is_flag=True,
    help="Enable parallel tool calls (overrides config)",
)
@click.option(
    "--agent_type",
    "-a",
    type=click.Choice(["react", "deep_react"]),
    help="Agent type (overrides config)",
)
@click.option(
    "--print_mode",
    default="rich",
    type=click.Choice(["json", "rich"]),
    help="Output format for responses",
)
@click.option(
    "--system_prompt",
    "-s",
    help="Custom system prompt for the agent (overrides config)",
)
@click.option("--api_url", help="URL of the Dulayni API server (overrides config)")
@click.option(
    "--thread_id", help="Thread ID for conversation continuity (overrides config)"
)
def main(**cli_args):
    """Dulayni CLI Client - Interact with dulayni RAG agents via API"""

    # Load configuration file
    config_path = cli_args.pop("config")
    config = load_config(config_path)

    # Merge config with CLI arguments (CLI takes priority), only non-null values
    merged_config = merge_config_with_args(config, **cli_args)

    try:
        # Create client with only the parameters that were explicitly provided
        client_params = {}
        client_param_mapping = {
            "api_url": "api_url",
            "openai_api_key": "openai_api_key",
            "model": "model",
            "agent_type": "agent_type",
            "thread_id": "thread_id",
            "system_prompt": "system_prompt",
            "mcp_servers": "mcp_servers",
            "memory_db": "memory_db",
            "pg_uri": "pg_uri",
            "startup_timeout": "startup_timeout",
            "parallel_tool_calls": "parallel_tool_calls",
        }

        for config_key, client_key in client_param_mapping.items():
            if config_key in merged_config:
                client_params[client_key] = merged_config[config_key]

        client = DulayniClient(**client_params)

    except DulayniClientError as e:
        console.print(f"[red]Configuration Error: {str(e)}[/red]")
        raise click.Abort()

    if merged_config.get("query"):
        # Batch mode
        try:
            if merged_config.get("print_mode") == "json":
                result = client.query_json(merged_config["query"])
                print(json.dumps(result, indent=2))
            else:
                result = client.query(merged_config["query"])
                console.print(Markdown(result))
        except (DulayniConnectionError, DulayniTimeoutError, DulayniClientError) as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            raise click.Abort()
    else:
        # Interactive mode
        console.print(
            "[bold green]Dulayni Client - Interactive mode. Type 'q' to quit.[/bold green]"
        )
        console.print(f"[yellow]Config file: {config_path}[/yellow]")
        console.print(
            f"[yellow]API endpoint: {merged_config.get('api_url', 'server default')}[/yellow]"
        )
        console.print(
            f"[yellow]Agent type: {merged_config.get('agent_type', 'server default')}[/yellow]"
        )
        console.print(
            f"[yellow]Model: {merged_config.get('model', 'server default')}[/yellow]"
        )
        console.print(
            f"[yellow]Thread ID: {merged_config.get('thread_id', 'server default')}[/yellow]"
        )
        console.print(
            f"[yellow]Memory: {merged_config.get('memory_db') or merged_config.get('pg_uri') or 'server default'}[/yellow]"
        )
        console.print(
            f"[yellow]MCP servers: {len(merged_config.get('mcp_servers', {})) if 'mcp_servers' in merged_config else 'server default'} configured[/yellow]"
        )

        # Health check
        console.print("[yellow]Checking server connection...[/yellow]")
        health_status = client.health_check()
        if health_status.get("status") != "healthy":
            console.print(
                f"[red]Warning: Server health check failed - {health_status.get('message', 'Unknown error')}[/red]"
            )
            if health_status.get("error") == "connection_error":
                console.print(
                    "[red]Make sure the dulayni server is running and accessible.[/red]"
                )
        else:
            console.print("[green]✓ Server connection OK[/green]")
            debug_tools = health_status.get("debug_tools")
            if debug_tools is not None:
                console.print(f"[cyan]Debug tools enabled: {debug_tools}[/cyan]")

        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if user_input.strip().lower() == "q":
                    break
                if not user_input.strip():
                    continue

                result = client.query(user_input)
                console.print(Markdown(result))

            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except (
                DulayniConnectionError,
                DulayniTimeoutError,
                DulayniClientError,
            ) as e:
                console.print(f"[red]Error: {str(e)}[/red]")
            except Exception as e:
                console.print(f"[red]Unexpected error: {str(e)}[/red]")


if __name__ == "__main__":
    main()
