#!/usr/bin/env python3
"""Dulayni CLI Client - Interact with dulayni RAG agents via API."""

import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
import click
from rich.console import Console
from rich.markdown import Markdown

from .client import DulayniClient
from .exceptions import (
    DulayniClientError,
    DulayniConnectionError,
    DulayniTimeoutError,
    DulayniAuthenticationError,
)
from .mcp.start import start_server, stop_server, DEFAULT_PORT

console = Console()

# Session management
def get_session_path() -> Path:
    """Get path to session file."""
    return Path.home() / ".dulayni" / "session.json"

def load_session() -> Optional[Dict[str, Any]]:
    """Load session data from file."""
    session_file = get_session_path()
    if session_file.exists():
        try:
            with open(session_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return None

def save_session(session_data: Dict[str, Any]) -> None:
    """Save session data to file."""
    session_file = get_session_path()
    session_file.parent.mkdir(parents=True, exist_ok=True)
    with open(session_file, "w") as f:
        json.dump(session_data, f)

def clear_session() -> None:
    """Clear session data."""
    session_file = get_session_path()
    if session_file.exists():
        session_file.unlink()

def is_session_valid(session_data: Dict[str, Any]) -> bool:
    """Check if session is still valid."""
    if not session_data or not session_data.get("auth_token"):
        return False
    
    # Check if token has expired (assuming 24 hour expiry)
    expiry_time = session_data.get("expiry_time", 0)
    return time.time() < expiry_time


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

    # Phone number handling
    phone_number = (
        cli_args.get("phone_number")
        or config.get("phone_number")
        or os.environ.get("PHONE_NUMBER")
    )
    add_if_not_none("phone_number", phone_number)

    # CLI-only arguments
    add_if_not_none("query", cli_args.get("query"))
    add_if_not_none("print_mode", cli_args.get("print_mode"))

    return merged


@click.group()
def cli():
    """Dulayni CLI Client - Interact with dulayni RAG agents via API."""
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    default="config/config.json",
    help="Path to configuration JSON file",
)
@click.option(
    "--model", "-m", type=click.Choice(["gpt-4o", "gpt-4o-mini"]), help="Model name"
)
@click.option(
    "--phone-number", "-p", required=True, help="Phone number for authentication"
)
@click.option("--query", "-q", type=str, help="Query string for batch mode")
@click.option("--memory_db", help="Path to SQLite database for conversation memory")
@click.option("--pg_uri", help="PostgreSQL URI for memory storage")
@click.option(
    "--agent_type", "-a", type=click.Choice(["react", "deep_react"]), help="Agent type"
)
@click.option(
    "--print_mode",
    default="rich",
    type=click.Choice(["json", "rich"]),
    help="Output format",
)
@click.option("--system_prompt", "-s", help="Custom system prompt for the agent")
@click.option("--api_url", help="URL of the Dulayni API server")
@click.option("--thread_id", help="Thread ID for conversation continuity")
def run(**cli_args):
    """Run a query using the dulayni agent."""
    # Start MCP filesystem server in background
    proc = start_server(port=DEFAULT_PORT)

    try:
        # Load configuration file
        config_path = cli_args.pop("config")
        config = load_config(config_path)

        # Merge config with CLI arguments
        merged_config = merge_config_with_args(config, **cli_args)

        # Check for existing valid session
        session_data = load_session()
        phone_number = merged_config.get("phone_number")
        
        # Create client with only the parameters that were explicitly provided
        client_params = {}
        client_param_mapping = {
            "api_url": "api_url",
            "phone_number": "phone_number",
            "model": "model",
            "agent_type": "agent_type",
            "thread_id": "thread_id",
            "system_prompt": "system_prompt",
            "mcp_servers": "mcp_servers",
            "memory_db": "memory_db",
            "pg_uri": "pg_uri",
        }

        for config_key, client_key in client_param_mapping.items():
            if config_key in merged_config:
                client_params[client_key] = merged_config[config_key]

        client = DulayniClient(**client_params)

        if is_session_valid(session_data) and session_data.get("phone_number") == phone_number:
            # Use existing session
            client.set_auth_token(session_data["auth_token"])
            console.print("[green]Using existing authentication session[/green]")
        else:
            # Start new authentication flow
            if not phone_number:
                console.print(
                    "[red]Error: Phone number is required. Use --phone-number or set PHONE_NUMBER environment variable[/red]"
                )
                raise click.Abort()

            # Handle authentication
            def prompt_for_verification_code():
                return console.input(
                    "[bold yellow]Enter 4-digit verification code: [/bold yellow]"
                )

            # Authenticate user
            console.print(
                f"[yellow]Requesting verification code for {phone_number}...[/yellow]"
            )
            try:
                client.request_verification_code()
                code = prompt_for_verification_code()
                verify_result = client.verify_code(code)
                
                # Save session data (assuming 24 hour expiry)
                save_session({
                    "phone_number": phone_number,
                    "auth_token": verify_result.get("auth_token"),
                    "expiry_time": time.time() + 24 * 60 * 60  # 24 hours
                })
                
                console.print("[green]✓ Authentication successful[/green]")
            except DulayniAuthenticationError as e:
                console.print(f"[red]Authentication failed: {str(e)}[/red]")
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
            except (
                DulayniConnectionError,
                DulayniTimeoutError,
                DulayniClientError,
                DulayniAuthenticationError,
            ) as e:
                console.print(f"[red]Error: {str(e)}[/red]")
                raise click.Abort()
        else:
            # Interactive mode
            console.print(
                "[bold green]Dulayni Client - Interactive mode. Type 'q' to quit.[/bold green]"
            )

            # Print configuration info
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
                f"[yellow]Phone number: {merged_config.get('phone_number', 'not set')}[/yellow]"
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
                    DulayniAuthenticationError,
                ) as e:
                    console.print(f"[red]Error: {str(e)}[/red]")
                except Exception as e:
                    console.print(f"[red]Unexpected error: {str(e)}[/red]")

    finally:
        # Always try to stop the MCP server gracefully
        stop_server(port=DEFAULT_PORT)

        # Fallback: kill process if still alive
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=2)
            console.print("[yellow]MCP filesystem server process terminated[/yellow]")


@cli.command()
def logout():
    """Clear authentication session."""
    clear_session()
    console.print("[green]Logged out successfully[/green]")


if __name__ == "__main__":
    cli()
