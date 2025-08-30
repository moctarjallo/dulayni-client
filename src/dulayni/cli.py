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

RELAY_HOST = "157.230.76.226"

console = Console()

# Default .gitignore content
DEFAULT_GITIGNORE = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Logs
*.log

# Dulayni specific
.frpc/
memory.sqlite
session.json
.dulayni_key
"""

# Default config template
DEFAULT_CONFIG_TEMPLATE = """{{
  "phone_number": "{phone_number}",
  "api_url": "https://dulayni.kajande.com/run_agent",
  
  "agent": {{
    "model": "gpt-4o-mini",
    "agent_type": "deep_react",
    "system_prompt": "You are a helpful assistant for customer support tasks.",
    "startup_timeout": 30.0,
    "parallel_tool_calls": true
  }},
  
  "memory": {{
    "memory_db": "memory.sqlite",
    "pg_uri": null,
    "thread_id": "devops"
  }},
  
  "mcpServers": {{
    "local": {{
      "url": "http://{phone_number_clean}.{relay_host}.nip.io/mcp",
      "transport": "streamable_http"
    }}
  }}
}}"""

# Config template for Dulayni API key usage
DULAYNI_CONFIG_TEMPLATE = """{{
  "dulayni_api_key_file": ".dulayni_key",
  "api_url": "https://dulayni.kajande.com/run_agent",
  
  "agent": {{
    "model": "gpt-4o-mini",
    "agent_type": "deep_react",
    "system_prompt": "You are a helpful assistant for customer support tasks.",
    "startup_timeout": 30.0,
    "parallel_tool_calls": true
  }},
  
  "memory": {{
    "memory_db": "memory.sqlite",
    "pg_uri": null,
    "thread_id": "default"
  }},
  
  "mcpServers": {{
    "filesystem": {{
      "url": "http://localhost:8080/mcp",
      "transport": "streamable_http"
    }}
  }}
}}"""


def is_project_initialized() -> bool:
    """Check if the current directory is already initialized as a dulayni project."""
    config_file = Path("config/config.json")
    return config_file.exists()


def get_phone_number_from_config() -> Optional[str]:
    """Extract phone number from existing config file."""
    config_file = Path("config/config.json")
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                return config.get("phone_number")
        except (json.JSONDecodeError, IOError):
            pass
    return None


def get_dulayni_key_from_config() -> Optional[str]:
    """Extract Dulayni API key from config or key file."""
    config_file = Path("config/config.json")
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                # Check if key is directly in config
                if "dulayni_api_key" in config:
                    return config["dulayni_api_key"]
                # Check if key file is specified
                key_file_path = config.get("dulayni_api_key_file")
                if key_file_path:
                    key_file = Path(key_file_path)
                    if key_file.exists():
                        return key_file.read_text().strip()
        except (json.JSONDecodeError, IOError):
            pass
    return None


def has_authentication_method() -> bool:
    """Check if project has either phone number or Dulayni API key configured."""
    return bool(get_phone_number_from_config() or get_dulayni_key_from_config())


def initialize_git_repository():
    """Initialize Git repository if not already initialized."""
    if Path(".git").exists():
        console.print("[yellow]Git repository already exists[/yellow]")
        return True
    
    try:
        result = subprocess.run(
            ["git", "init"],
            capture_output=True,
            text=True,
            cwd="."
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Initialized Git repository[/green]")
            return True
        else:
            console.print(f"[red]Failed to initialize Git repository: {result.stderr}[/red]")
            return False
            
    except FileNotFoundError:
        console.print("[yellow]Git not found. Skipping Git initialization.[/yellow]")
        return True  # Don't fail the whole process if Git isn't available


def create_gitignore():
    """Create or update .gitignore file."""
    gitignore_path = Path(".gitignore")
    
    if gitignore_path.exists():
        # Read existing content
        with open(gitignore_path, "r") as f:
            existing_content = f.read()
        
        # Check if .frpc/ is already in there
        if ".frpc/" not in existing_content or ".dulayni_key" not in existing_content:
            with open(gitignore_path, "a") as f:
                if ".frpc/" not in existing_content:
                    f.write("\n# Dulayni specific\n.frpc/\nmemory.sqlite\nsession.json\n")
                if ".dulayni_key" not in existing_content:
                    f.write(".dulayni_key\n")
            console.print("[green]✓ Updated existing .gitignore file[/green]")
        else:
            console.print("[yellow].gitignore already contains dulayni entries[/yellow]")
    else:
        # Create new .gitignore
        with open(gitignore_path, "w") as f:
            f.write(DEFAULT_GITIGNORE)
        console.print("[green]✓ Created .gitignore file[/green]")


def create_config_file(phone_number: Optional[str] = None, use_dulayni: bool = False):
    """Create the config/config.json file."""
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / "config.json"
    
    if use_dulayni:
        config_content = DULAYNI_CONFIG_TEMPLATE
        console.print(f"[green]✓ Created config file for Dulayni API key usage: {config_file}[/green]")
    else:
        # Clean phone number for URL (remove + and other special chars)
        phone_number_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "")
        
        config_content = DEFAULT_CONFIG_TEMPLATE.format(
            phone_number=phone_number,
            phone_number_clean=phone_number_clean,
            relay_host=RELAY_HOST
        )
        console.print(f"[green]✓ Created config file for WhatsApp authentication: {config_file}[/green]")
    
    with open(config_file, "w") as f:
        f.write(config_content)


def prompt_for_phone_number() -> str:
    """Interactively prompt user for phone number."""
    while True:
        phone_number = console.input("[bold yellow]Enter your phone number (with country code, e.g., +1234567890): [/bold yellow]")
        phone_number = phone_number.strip()
        
        if not phone_number:
            console.print("[red]Phone number cannot be empty[/red]")
            continue
        
        if not phone_number.startswith("+"):
            console.print("[red]Phone number must include country code (start with +)[/red]")
            continue
        
        # Basic validation - should have at least 7 digits after the +
        digits_only = ''.join(c for c in phone_number[1:] if c.isdigit())
        if len(digits_only) < 7:
            console.print("[red]Phone number appears to be too short[/red]")
            continue
        
        return phone_number


def prompt_for_dulayni_key() -> str:
    """Interactively prompt user for Dulayni API key."""
    while True:
        api_key = console.input("[bold yellow]Enter your Dulayni API key: [/bold yellow]", password=True)
        api_key = api_key.strip()
        
        if not api_key:
            console.print("[red]API key cannot be empty[/red]")
            continue
        
        # Basic validation - should start with sk-
        if not api_key.startswith("sk-"):
            console.print("[red]Dulayni API keys typically start with 'sk-'[/red]")
            if not click.confirm("Continue anyway?"):
                continue
        
        return api_key


def save_dulayni_key(api_key: str):
    """Save Dulayni API key to .dulayni_key file."""
    key_file = Path(".dulayni_key")
    key_file.write_text(api_key)
    key_file.chmod(0o600)  # Make it readable only by owner
    console.print("[green]✓ Dulayni API key saved to .dulayni_key[/green]")


# Session management functions (unchanged)
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


# FRPC management functions (unchanged)
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

def setup_frpc(phone_number: str, host: str) -> bool:
    """Set up frpc configuration and Docker container."""
    frpc_dir = get_frpc_dir()
    frpc_dir.mkdir(exist_ok=True)
    
    # Generate frpc.toml
    frpc_toml_content = FRPC_TOML_TEMPLATE.format(phone_number=phone_number.replace('+', ''), host=host)
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
                config = json.load(f)
                
                # Handle Dulayni API key from file
                if "dulayni_api_key_file" in config:
                    key_file_path = config["dulayni_api_key_file"]
                    key_file = Path(key_file_path)
                    if key_file.exists():
                        config["dulayni_api_key"] = key_file.read_text().strip()
                
                return config
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

    # Authentication configuration
    add_if_not_none("phone_number", config.get("phone_number"))
    add_if_not_none("dulayni_api_key", cli_args.get("dulayni_api_key") or config.get("dulayni_api_key"))

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
    
    console.print("[bold green]Initializing dulayni project...[/bold green]")
    
    # Check if already initialized
    if is_project_initialized():
        if has_authentication_method():
            existing_phone = get_phone_number_from_config()
            existing_key = get_dulayni_key_from_config()
            
            if existing_phone:
                console.print(f"[yellow]Project already initialized with WhatsApp authentication (phone: {existing_phone})[/yellow]")
            elif existing_key:
                console.print("[yellow]Project already initialized with Dulayni API key authentication[/yellow]")
            
            if click.confirm("Do you want to re-initialize?"):
                pass  # Continue with re-initialization
            else:
                console.print("[yellow]Initialization cancelled[/yellow]")
                return
        else:
            console.print("[yellow]Project config found but no authentication method. Continuing with initialization...[/yellow]")
    
    # Determine authentication method
    use_dulayni = False
    
    if auth_method == "dulayni":
        use_dulayni = True
    elif auth_method == "whatsapp":
        use_dulayni = False
    elif dulayni_key:
        use_dulayni = True
    elif phone_number:
        use_dulayni = False
    else:
        # Ask user to choose
        console.print("\n[bold]Choose authentication method:[/bold]")
        console.print("1. WhatsApp verification (requires phone number)")
        console.print("2. Dulayni API key (no phone verification needed)")
        
        while True:
            choice = console.input("[bold yellow]Choose method (1 or 2): [/bold yellow]")
            if choice == "1":
                use_dulayni = False
                break
            elif choice == "2":
                use_dulayni = True
                break
            else:
                console.print("[red]Please enter 1 or 2[/red]")
    
    try:
        # Initialize Git repository
        console.print("\n[bold]Step 1: Setting up Git repository[/bold]")
        initialize_git_repository()
        create_gitignore()
        
        # Create config file based on authentication method
        console.print("\n[bold]Step 2: Creating configuration[/bold]")
        
        if use_dulayni:
            # Dulayni API key authentication
            if not dulayni_key:
                dulayni_key = prompt_for_dulayni_key()
            
            save_dulayni_key(dulayni_key)
            create_config_file(use_dulayni=True)
            
            console.print("[cyan]Using Dulayni API key authentication[/cyan]")
            
            # Skip FRPC setup for Dulayni
            console.print("\n[bold]Step 3: FRPC setup[/bold]")
            console.print("[yellow]Skipping FRPC setup (not needed for Dulayni authentication)[/yellow]")
            
            # Skip WhatsApp authentication
            console.print("\n[bold]Step 4: Authentication[/bold]")
            console.print("[green]✓ Dulayni API key configured[/green]")
            
        else:
            # WhatsApp authentication
            if not phone_number:
                phone_number = prompt_for_phone_number()
            
            console.print(f"[cyan]Using WhatsApp authentication with phone number: {phone_number}[/cyan]")
            create_config_file(phone_number=phone_number)
            
            # Set up FRPC
            console.print("\n[bold]Step 3: Setting up FRPC[/bold]")
            if is_frpc_configured(phone_number):
                console.print("[green]FRPC is already configured[/green]")
            else:
                setup_frpc(phone_number, host=RELAY_HOST)
            
            # Perform WhatsApp authentication
            console.print("\n[bold]Step 4: Authentication[/bold]")
            console.print(f"[yellow]Requesting verification code for {phone_number}...[/yellow]")
            
            # Create a temporary client for authentication
            client = DulayniClient(phone_number=phone_number)
            
            try:
                client.request_verification_code()
                code = console.input("[bold yellow]Enter 4-digit verification code: [/bold yellow]")
                verify_result = client.verify_code(code)
                
                # Save session data
                save_session({
                    "phone_number": phone_number,
                    "auth_token": verify_result.get("auth_token"),
                    "expiry_time": time.time() + 24 * 60 * 60  # 24 hours
                })
                
                console.print("[green]✓ Authentication successful[/green]")
                
            except DulayniAuthenticationError as e:
                console.print(f"[red]Authentication failed: {str(e)}[/red]")
                console.print("[yellow]Project files created but authentication incomplete.[/yellow]")
                console.print("[yellow]You can run 'dulayni run' later to authenticate.[/yellow]")
        
        # Summary
        console.print("\n[bold green]✓ Dulayni project initialization complete![/bold green]")
        console.print("\n[bold]What was created:[/bold]")
        console.print("• Git repository (if not already present)")
        console.print("• .gitignore file with dulayni entries")
        console.print("• config/config.json with your settings")
        
        if use_dulayni:
            console.print("• .dulayni_key file (secure API key storage)")
        else:
            console.print("• .frpc/ directory with tunnel configuration")
            console.print("• Authentication session (if successful)")
        
        console.print("\n[bold]Next steps:[/bold]")
        console.print("• Run '[bold cyan]dulayni run[/bold cyan]' to start interactive mode")
        console.print("• Run '[bold cyan]dulayni run -q \"your query\"[/bold cyan]' for batch queries")
        console.print("• Edit config/config.json to customize your settings")
        
    except Exception as e:
        console.print(f"[red]Initialization failed: {str(e)}[/red]")
        raise click.Abort()


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
def run(**cli_args):
    """Run a query using the dulayni agent."""
    
    # Check if project is initialized
    if not is_project_initialized():
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
    if not using_dulayni and not skip_frpc and phone_number and is_docker_available():
        # Check if frpc container is running
        check_result = subprocess.run(
            ["docker", "ps", "--filter", "name=frpc", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        if "frpc" not in check_result.stdout:
            console.print("[yellow]FRPC container is not running. Attempting to start it...[/yellow]")
            if not setup_frpc(phone_number, host=RELAY_HOST):
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
        if using_dulayni:
            # Dulayni API key - no session management needed
            console.print("[green]Using Dulayni API key (no session management needed)[/green]")
        else:
            # WhatsApp authentication - handle session management
            session_data = load_session()
            
            if is_session_valid(session_data) and session_data.get("phone_number") == phone_number:
                # Use existing session
                client.set_auth_token(session_data["auth_token"])
                console.print("[green]Using existing authentication session[/green]")
            else:
                # Start new authentication flow
                console.print(
                    f"[yellow]Requesting verification code for {phone_number}...[/yellow]"
                )
                try:
                    client.request_verification_code()
                    code = console.input("[bold yellow]Enter 4-digit verification code: [/bold yellow]")
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

        # Handle query execution
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
    """Clear authentication session (WhatsApp auth only)."""
    clear_session()
    console.print("[green]Logged out successfully[/green]")
    console.print("[yellow]Note: This only affects WhatsApp authentication sessions.[/yellow]")
    console.print("[yellow]Dulayni API key configurations are not affected.[/yellow]")


@cli.command()
def status():
    """Show current project authentication status."""
    if not is_project_initialized():
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
        session_data = load_session()
        if is_session_valid(session_data) and session_data.get("phone_number") == phone_number:
            console.print("[green]✓ Valid authentication session found[/green]")
        else:
            console.print("[yellow]⚠ No valid authentication session (will need to verify on next run)[/yellow]")
        
        # Check FRPC status
        if is_docker_available():
            check_result = subprocess.run(
                ["docker", "ps", "--filter", "name=frpc", "--format", "{{.Names}}"],
                capture_output=True,
                text=True
            )
            if "frpc" in check_result.stdout:
                console.print("[green]✓ FRPC container is running[/green]")
            else:
                console.print("[yellow]⚠ FRPC container is not running[/yellow]")
        else:
            console.print("[yellow]⚠ Docker not available for FRPC[/yellow]")
    else:
        console.print("[red]✗ No authentication method configured[/red]")


if __name__ == "__main__":
    cli()
