#!/usr/bin/env python3
"""Dulayni CLI Client - Interact with dulayni RAG agents via API."""

import os
import json
import time
import subprocess
import shutil
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
from .frpc_templates import FRPC_TOML_TEMPLATE, DOCKERFILE_TEMPLATE, DOCKER_COMPOSE_TEMPLATE

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

# FRPC management
def get_frpc_dir() -> Path:
    """Get path to frpc directory."""
    return Path(".frpc")

def is_docker_available() -> bool:
    """Check if Docker is available on the system."""
    return shutil.which("docker") is not None

def is_frpc_configured(phone_number: str) -> bool:
    """Check if frpc is already configured for the given phone number."""
    frpc_dir = get_frpc_dir()
    frpc_toml = frpc_dir / "frpc.toml"
    
    if not frpc_toml.exists():
        return False
    
    try:
        with open(frpc_toml, "r") as f:
            content = f.read()
            return phone_number in content
    except:
        return False

def setup_frpc(phone_number: str) -> bool:
    """Set up frpc configuration and Docker container."""
    frpc_dir = get_frpc_dir()
    frpc_dir.mkdir(exist_ok=True)
    
    # Generate frpc.toml
    frpc_toml_content = FRPC_TOML_TEMPLATE.format(phone_number=phone_number.replace('+', ''))
    with open(frpc_dir / "frpc.toml", "w") as f:
        f.write(frpc_toml_content)
    
    # Generate Dockerfile
    with open(frpc_dir / "Dockerfile", "w") as f:
        f.write(DOCKERFILE_TEMPLATE)
    
    # Generate docker-compose.yml
    with open(frpc_dir / "docker-compose.yml", "w") as f:
        f.write(DOCKER_COMPOSE_TEMPLATE)
    
    console.print(f"[green]Generated frpc configuration for phone number: {phone_number}[/green]")
    
    # Build and start the Docker container if Docker is available
    if is_docker_available():
        try:
            # Build the Docker image
            build_result = subprocess.run(
                ["docker", "build", "-t", "dulayni-frpc", "."],
                cwd=frpc_dir,
                capture_output=True,
                text=True
            )
            
            if build_result.returncode != 0:
                console.print(f"[yellow]Docker build failed: {build_result.stderr}[/yellow]")
                return False
            
            # Stop any existing frpc container
            subprocess.run(
                ["docker", "rm", "-f", "frpc"],
                cwd=frpc_dir,
                capture_output=True
            )
            
            # Run the new container
            run_result = subprocess.run(
                ["docker", "run", "--name", "frpc", "--network", "host", "-d", "dulayni-frpc"],
                cwd=frpc_dir,
                capture_output=True,
                text=True
            )
            
            if run_result.returncode == 0:
                console.print("[green]FRPC Docker container started successfully[/green]")
                return True
            else:
                console.print(f"[yellow]Failed to start FRPC container: {run_result.stderr}[/yellow]")
                return False
                
        except Exception as e:
            console.print(f"[yellow]Error managing Docker container: {str(e)}[/yellow]")
            return False
    else:
        console.print("[yellow]Docker is not available. Please install Docker to run the FRPC container.[/yellow]")
        console.print("[yellow]You can manually run the container with: docker build -t dulayni-frpc . && docker run --name frpc --network host -d dulayni-frpc[/yellow]")
        return False


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
    "--phone-number", "-p", required=True, help="Phone number for FRPC configuration"
)
def init(phone_number: str):
    """Initialize FRPC configuration with your phone number."""
    if is_frpc_configured(phone_number):
        console.print("[green]FRPC is already configured with this phone number[/green]")
        return
    
    success = setup_frpc(phone_number)
    if success:
        console.print("[green]FRPC initialization completed successfully[/green]")
    else:
        console.print("[yellow]FRPC initialization completed with warnings[/yellow]")


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
@click.option("--skip-frpc", is_flag=True, help="Skip FRPC container check")
def run(**cli_args):
    """Run a query using the dulayni agent."""
    # Check if FRPC container is running
    skip_frpc = cli_args.pop("skip_frpc", False)
    phone_number = cli_args.get("phone_number")
    
    if not skip_frpc and phone_number and is_docker_available():
        # Check if frpc container is running
        check_result = subprocess.run(
            ["docker", "ps", "--filter", "name=frpc", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        if "frpc" not in check_result.stdout:
            console.print("[yellow]FRPC container is not running. Attempting to start it...[/yellow]")
            if not setup_frpc(phone_number):
                console.print("[yellow]Failed to start FRPC container. Proceeding without it...[/yellow]")
    
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
