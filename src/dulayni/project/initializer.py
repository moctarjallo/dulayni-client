"""Project initialization utilities."""

from pathlib import Path
import time
from typing import Optional
from rich.console import Console
import click

from dulayni.exceptions import DulayniAuthenticationError
from dulayni.project.validator import ProjectValidator

from ..config.manager import ConfigManager
from ..config.templates import DEFAULT_CONFIG_TEMPLATE, DULAYNI_CONFIG_TEMPLATE
from ..infrastructure.git import GitManager
from ..infrastructure.frpc import FRPCManager
from ..auth.authenticator import AuthenticationManager

RELAY_HOST = "157.230.76.226"

class ProjectInitializer:
    """Handles dulayni project initialization."""

    def __init__(self):
        self.console = Console()
        self.git_manager = GitManager()
        self.frpc_manager = FRPCManager()
        self.auth_manager = AuthenticationManager()
        self.config_manager = ConfigManager()

    def prompt_for_phone_number(self) -> str:
        """Interactively prompt user for phone number."""
        while True:
            phone_number = self.console.input("[bold yellow]Enter your phone number (with country code, e.g., +1234567890): [/bold yellow]")
            phone_number = phone_number.strip()
            
            if not phone_number:
                self.console.print("[red]Phone number cannot be empty[/red]")
                continue
            
            if not phone_number.startswith("+"):
                self.console.print("[red]Phone number must include country code (start with +)[/red]")
                continue
            
            # Basic validation - should have at least 7 digits after the +
            digits_only = ''.join(c for c in phone_number[1:] if c.isdigit())
            if len(digits_only) < 7:
                self.console.print("[red]Phone number appears to be too short[/red]")
                continue
            
            return phone_number

    def prompt_for_dulayni_key(self) -> str:
        """Interactively prompt user for Dulayni API key."""
        while True:
            api_key = self.console.input("[bold yellow]Enter your Dulayni API key: [/bold yellow]", password=True)
            api_key = api_key.strip()
            
            if not api_key:
                self.console.print("[red]API key cannot be empty[/red]")
                continue
            
            # Basic validation - should start with sk-
            if not api_key.startswith("sk-"):
                self.console.print("[red]Dulayni API keys typically start with 'sk-'[/red]")
                if not click.confirm("Continue anyway?"):
                    continue
            
            return api_key

    def save_dulayni_key(self, api_key: str):
        """Save Dulayni API key to .dulayni_key file."""
        key_file = Path(".dulayni_key")
        key_file.write_text(api_key)
        key_file.chmod(0o600)  # Make it readable only by owner
        self.console.print("[green]✓ Dulayni API key saved to .dulayni_key[/green]")

    def create_config_file(self, phone_number: Optional[str] = None, use_dulayni: bool = False):
        """Create the config/config.json file."""
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        
        config_file = config_dir / "config.json"
        
        if use_dulayni:
            config_content = DULAYNI_CONFIG_TEMPLATE
            self.console.print(f"[green]✓ Created config file for Dulayni API key usage: {config_file}[/green]")
        else:
            # Clean phone number for URL (remove + and other special chars)
            phone_number_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "")
            
            config_content = DEFAULT_CONFIG_TEMPLATE.format(
                phone_number=phone_number,
                phone_number_clean=phone_number_clean,
                relay_host=RELAY_HOST
            )
            self.console.print(f"[green]✓ Created config file for WhatsApp authentication: {config_file}[/green]")
        
        with open(config_file, "w") as f:
            f.write(config_content)

    def initialize_project(self, phone_number: Optional[str], dulayni_key: Optional[str], auth_method: Optional[str]):
        """Initialize dulayni project with all necessary components."""
        
        self.console.print("[bold green]Initializing dulayni project...[/bold green]")
        
        # Check if already initialized
        if ProjectValidator.is_project_initialized():
            if ProjectValidator.is_project_initialized_with_auth():
                existing_phone = self.config_manager.get_phone_number_from_config()
                existing_key = self.config_manager.get_dulayni_key_from_config()
                
                if existing_phone:
                    self.console.print(f"[yellow]Project already initialized with WhatsApp authentication (phone: {existing_phone})[/yellow]")
                elif existing_key:
                    self.console.print("[yellow]Project already initialized with Dulayni API key authentication[/yellow]")
                
                if click.confirm("Do you want to re-initialize?"):
                    pass  # Continue with re-initialization
                else:
                    self.console.print("[yellow]Initialization cancelled[/yellow]")
                    return
            else:
                self.console.print("[yellow]Project config found but no authentication method. Continuing with initialization...[/yellow]")
        
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
            self.console.print("\n[bold]Choose authentication method:[/bold]")
            self.console.print("1. WhatsApp verification (requires phone number)")
            self.console.print("2. Dulayni API key (no phone verification needed)")
            
            while True:
                choice = self.console.input("[bold yellow]Choose method (1 or 2): [/bold yellow]")
                if choice == "1":
                    use_dulayni = False
                    break
                elif choice == "2":
                    use_dulayni = True
                    break
                else:
                    self.console.print("[red]Please enter 1 or 2[/red]")
        
        try:
            # Initialize Git repository
            self.console.print("\n[bold]Step 1: Setting up Git repository[/bold]")
            self.git_manager.initialize_repository()
            self.git_manager.create_gitignore()
            
            # Create config file based on authentication method
            self.console.print("\n[bold]Step 2: Creating configuration[/bold]")
            
            if use_dulayni:
                # Dulayni API key authentication
                if not dulayni_key:
                    dulayni_key = self.prompt_for_dulayni_key()
                
                self.save_dulayni_key(dulayni_key)
                self.create_config_file(use_dulayni=True)
                
                self.console.print("[cyan]Using Dulayni API key authentication[/cyan]")
                
                # Skip FRPC setup for Dulayni
                self.console.print("\n[bold]Step 3: FRPC setup[/bold]")
                self.console.print("[yellow]Skipping FRPC setup (not needed for Dulayni authentication)[/yellow]")
                
                # Skip WhatsApp authentication
                self.console.print("\n[bold]Step 4: Authentication[/bold]")
                self.console.print("[green]✓ Dulayni API key configured[/green]")
                
            else:
                # WhatsApp authentication
                if not phone_number:
                    phone_number = self.prompt_for_phone_number()
                
                self.console.print(f"[cyan]Using WhatsApp authentication with phone number: {phone_number}[/cyan]")
                self.create_config_file(phone_number=phone_number)
                
                # Set up FRPC
                self.console.print("\n[bold]Step 3: Setting up FRPC[/bold]")
                if self.frpc_manager.is_configured(phone_number):
                    self.console.print("[green]FRPC is already configured[/green]")
                else:
                    self.frpc_manager.setup_frpc(phone_number, host=RELAY_HOST)
                
                # Perform WhatsApp authentication
                self.console.print("\n[bold]Step 4: Authentication[/bold]")
                self.console.print(f"[yellow]Requesting verification code for {phone_number}...[/yellow]")
                
                # Create a temporary client for authentication
                from ..client import DulayniClient
                client = DulayniClient(phone_number=phone_number)
                
                try:
                    client.request_verification_code()
                    code = self.console.input("[bold yellow]Enter 4-digit verification code: [/bold yellow]")
                    verify_result = client.verify_code(code)
                    
                    # Save session data
                    self.auth_manager.session_manager.save_session({
                        "phone_number": phone_number,
                        "auth_token": verify_result.get("auth_token"),
                        "expiry_time": time.time() + 24 * 60 * 60  # 24 hours
                    })
                    
                    self.console.print("[green]✓ Authentication successful[/green]")
                    
                except DulayniAuthenticationError as e:
                    self.console.print(f"[red]Authentication failed: {str(e)}[/red]")
                    self.console.print("[yellow]Project files created but authentication incomplete.[/yellow]")
                    self.console.print("[yellow]You can run 'dulayni run' later to authenticate.[/yellow]")
            
            # Summary
            self.console.print("\n[bold green]✓ Dulayni project initialization complete![/bold green]")
            self.console.print("\n[bold]What was created:[/bold]")
            self.console.print("• Git repository (if not already present)")
            self.console.print("• .gitignore file with dulayni entries")
            self.console.print("• config/config.json with your settings")
            
            if use_dulayni:
                self.console.print("• .dulayni_key file (secure API key storage)")
            else:
                self.console.print("• .frpc/ directory with tunnel configuration")
                self.console.print("• Authentication session (if successful)")
            
            self.console.print("\n[bold]Next steps:[/bold]")
            self.console.print("• Run '[bold cyan]dulayni run[/bold cyan]' to start interactive mode")
            self.console.print("• Run '[bold cyan]dulayni run -q \"your query\"[/bold cyan]' for batch queries")
            self.console.print("• Edit config/config.json to customize your settings")
            
        except Exception as e:
            self.console.print(f"[red]Initialization failed: {str(e)}[/red]")
            raise click.Abort()