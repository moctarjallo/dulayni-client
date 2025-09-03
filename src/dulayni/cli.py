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
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .client import DulayniClient
from .exceptions import (
    DulayniClientError,
    DulayniConnectionError,
    DulayniTimeoutError,
    DulayniAuthenticationError,
)
from .mcp.start import start_server, stop_server, DEFAULT_PORT
from .project.initializer import ProjectInitializer
from .project.validator import ProjectValidator
from .config.manager import ConfigManager
from .auth.authenticator import AuthenticationManager
from .infrastructure.docker import DockerManager
from .infrastructure.frpc import FRPCManager

console = Console()


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    return ConfigManager.load_config(config_path)


def merge_config_with_args(config: Dict[str, Any], **cli_args) -> Dict[str, Any]:
    """Merge configuration with CLI arguments, giving priority to CLI args."""
    return ConfigManager.merge_config_with_args(config, **cli_args)


@click.group()
def cli():
    """Dulayni CLI Client - Interact with dulayni RAG agents via API."""
    pass


@cli.command()
@click.option(
    "--phone-number", "-p", help="Phone number for WhatsApp authentication and FRPC configuration"
)
@click.option(
    "--dulayni-key", "-k", help="Dulayni API key (alternative to phone authentication)"
)
@click.option(
    "--auth-method",
    type=click.Choice(["whatsapp", "dulayni"]),
    help="Choose authentication method"
)
def init(phone_number: Optional[str], dulayni_key: Optional[str], auth_method: Optional[str]):
    """Initialize dulayni project in current directory with Git, config, and authentication setup."""
    initializer = ProjectInitializer()
    initializer.initialize_project(phone_number, dulayni_key, auth_method)


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
@click.option("--dulayni-api-key", help="Dulayni API key (override config)")
@click.option("--stream", is_flag=True, help="Enable streaming mode")
def run(stream: bool, **cli_args):
    """Run a query using the dulayni agent."""

    # Check if project is initialized
    if not ProjectValidator.is_project_initialized():
        console.print("[red]Error: Project not initialized.[/red]")
        console.print("[yellow]Please run '[bold cyan]dulayni init[/bold cyan]' first to initialize your project.[/yellow]")
        raise click.Abort()

    # Load configuration file first
    config_path = cli_args.pop("config")
    config = load_config(config_path)

    # Merge config with CLI arguments
    merged_config = merge_config_with_args(config, **cli_args)

    # Check authentication methods
    phone_number = merged_config.get("phone_number")
    dulayni_key = merged_config.get("dulayni_api_key")

    if not phone_number and not dulayni_key:
        console.print("[red]Error: No authentication method found in configuration.[/red]")
        console.print("[yellow]Please run '[bold cyan]dulayni init[/bold cyan]' first to set up authentication.[/yellow]")
        raise click.Abort()

    # Determine which authentication method to use
    using_dulayni = bool(dulayni_key)

    if using_dulayni:
        console.print("[cyan]Using Dulayni API key authentication[/cyan]")
    else:
        console.print(f"[cyan]Using WhatsApp authentication with phone: {phone_number}[/cyan]")

    # Handle FRPC setup (only for WhatsApp auth)
    skip_frpc = cli_args.pop("skip_frpc", False)
    if not using_dulayni and not skip_frpc and phone_number and DockerManager.is_available():
        frpc_manager = FRPCManager()
        # Check if frpc container is running
        if not frpc_manager.docker_manager.is_container_running("frpc"):
            console.print("[yellow]FRPC container is not running. Attempting to start it...[/yellow]")
            if not frpc_manager.setup_frpc(phone_number, host="157.230.76.226"):
                console.print("[yellow]Failed to start FRPC container. Proceeding without it...[/yellow]")

    # Start MCP filesystem server in background (only if not using Dulayni with custom MCP)
    proc = start_server(port=DEFAULT_PORT)

    try:
        # Create client with only the parameters that were explicitly provided
        client_params = {}
        client_param_mapping = {
            "api_url": "api_url",
            "phone_number": "phone_number",
            "dulayni_api_key": "dulayni_api_key",
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

        # Handle authentication based on method
        auth_manager = AuthenticationManager()
        if using_dulayni:
            # Dulayni API key - no session management needed
            auth_manager.handle_dulayni_authentication()
        else:
            # WhatsApp authentication - handle session management
            if not auth_manager.handle_whatsapp_authentication(client, phone_number):
                raise click.Abort()

        # Handle query execution
        if merged_config.get("query"):
            # Batch mode
            try:
                if stream:
                    # Enhanced streaming mode
                    console.print("[cyan]Enhanced streaming mode enabled[/cyan]")
                    console.print(Panel(
                        "[bold green]🚀 Starting query execution...[/bold green]",
                        border_style="green"
                    ))

                    for message in client.query_stream(merged_config["query"]):
                        if message.get("type") == "message" and message.get("content"):
                            if merged_config.get("print_mode") == "json":
                                print(json.dumps(message, indent=2))
                            else:
                                console.print(Panel(
                                    Markdown(message["content"]),
                                    title="[bold green]🤖 Assistant Response[/bold green]",
                                    border_style="green",
                                    padding=(1, 2)
                                ))
                else:
                    # Non-streaming mode
                    if merged_config.get("print_mode") == "json":
                        result = client.query_json(merged_config["query"])
                        print(json.dumps(result, indent=2))
                    else:
                        result = client.query(merged_config["query"])
                        console.print(Panel(
                            Markdown(result),
                            title="[bold green]🤖 Assistant Response[/bold green]",
                            border_style="green",
                            padding=(1, 2)
                        ))
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
                Panel(
                    "[bold green]Dulayni Client - Interactive Mode[/bold green]\n"
                    "[yellow]Type 'q' to quit, 'clear' to clear screen[/yellow]",
                    border_style="green"
                )
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

            if using_dulayni:
                console.print("[yellow]Authentication: Dulayni API key[/yellow]")
            else:
                console.print(f"[yellow]Authentication: WhatsApp ({phone_number})[/yellow]")

            console.print(
                f"[yellow]Memory: {merged_config.get('memory_db') or merged_config.get('pg_uri') or 'server default'}[/yellow]"
            )
            console.print(
                f"[yellow]MCP servers: {len(merged_config.get('mcp_servers', {})) if 'mcp_servers' in merged_config else 'server default'} configured[/yellow]"
            )
            console.print(
                f"[yellow]Streaming mode: {'enabled' if stream else 'disabled'}[/yellow]"
            )

            # Health check
            console.print("[yellow]Checking server connection...[/yellow]")
            health_status = client.health_check()
            if health_status.get("status") != "healthy":
                console.print(
                    Panel(
                        f"[red]Warning: Server health check failed - {health_status.get('message', 'Unknown error')}[/red]",
                        title="[bold red]⚠️  Server Warning[/bold red]",
                        border_style="red"
                    )
                )
                if health_status.get("error") == "connection_error":
                    console.print(
                        "[red]Make sure the dulayni server is running and accessible.[/red]"
                    )
            else:
                console.print(Panel(
                    "[green]✓ Server connection OK[/green]",
                    border_style="green"
                ))
                debug_tools = health_status.get("debug_tools")
                if debug_tools is not None:
                    console.print(f"[cyan]Debug tools enabled: {debug_tools}[/cyan]")

            while True:
                try:
                    user_input = console.input("[bold blue]💬 > [/bold blue]")
                    if user_input.strip().lower() == "q":
                        break
                    if user_input.strip().lower() == "clear":
                        console.clear()
                        continue
                    if not user_input.strip():
                        continue

                    if stream:
                        # Enhanced streaming mode with tool execution display
                        console.print(Panel(
                            f"[bold blue]Processing: {user_input}[/bold blue]",
                            border_style="blue"
                        ))

                        full_response = ""
                        for message in client.query_stream(user_input):
                            if message.get("type") == "message" and message.get("content"):
                                full_response = message["content"]
                                console.print(Panel(
                                    Markdown(full_response),
                                    title="[bold green]🤖 Assistant Response[/bold green]",
                                    border_style="green",
                                    padding=(1, 2)
                                ))
                    else:
                        # Non-streaming mode
                        result = client.query(user_input)
                        console.print(Panel(
                            Markdown(result),
                            title="[bold green]🤖 Assistant Response[/bold green]",
                            border_style="green",
                            padding=(1, 2)
                        ))

                except KeyboardInterrupt:
                    console.print("\n[yellow]👋 Goodbye![/yellow]")
                    break
                except (
                    DulayniConnectionError,
                    DulayniTimeoutError,
                    DulayniClientError,
                    DulayniAuthenticationError,
                ) as e:
                    console.print(Panel(
                        f"[red]Error: {str(e)}[/red]",
                        title="[bold red]❌ Error[/bold red]",
                        border_style="red"
                    ))
                except Exception as e:
                    console.print(Panel(
                        f"[red]Unexpected error: {str(e)}[/red]",
                        title="[bold red]❌ Unexpected Error[/bold red]",
                        border_style="red"
                    ))

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
    """Clear authentication session (WhatsApp auth only)."""
    auth_manager = AuthenticationManager()
    auth_manager.logout()
    console.print("[green]Logged out successfully[/green]")
    console.print("[yellow]Note: This only affects WhatsApp authentication sessions.[/yellow]")
    console.print("[yellow]Dulayni API key configurations are not affected.[/yellow]")


@cli.command()
def status():
    """Show current project authentication status."""
    if not ProjectValidator.is_project_initialized():
        console.print("[red]Project not initialized. Run 'dulayni init' first.[/red]")
        return

    config = load_config("config/config.json")
    phone_number = config.get("phone_number")
    dulayni_key = config.get("dulayni_api_key")

    console.print("[bold green]Dulayni Project Status[/bold green]")
    console.print(f"Project directory: {Path.cwd()}")
    console.print(f"Config file: {'✓' if Path('config/config.json').exists() else '✗'}")

    if dulayni_key:
        console.print("[green]✓ Dulayni API key configured[/green]")
        console.print("Authentication method: Dulayni API key")
    elif phone_number:
        console.print(f"[green]✓ WhatsApp authentication configured ({phone_number})[/green]")
        console.print("Authentication method: WhatsApp verification")

        # Check session status
        session_manager = AuthenticationManager().session_manager
        session_data = session_manager.load_session()
        if session_manager.is_session_valid(session_data) and session_data.get("phone_number") == phone_number:
            console.print("[green]✓ Valid authentication session found[/green]")
        else:
            console.print("[yellow]⚠ No valid authentication session (will need to verify on next run)[/yellow]")

        # Check FRPC status
        if DockerManager.is_available():
            frpc_manager = FRPCManager()
            if frpc_manager.docker_manager.is_container_running("frpc"):
                console.print("[green]✓ FRPC container is running[/green]")
            else:
                console.print("[yellow]⚠ FRPC container is not running[/yellow]")
        else:
            console.print("[yellow]⚠ Docker not available for FRPC[/yellow]")
    else:
        console.print("[red]✗ No authentication method configured[/red]")


if __name__ == "__main__":
    cli()
