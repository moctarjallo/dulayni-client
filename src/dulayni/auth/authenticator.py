"""Authentication management for different authentication methods."""

import time
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel

from .session import SessionManager
from ..exceptions import DulayniAuthenticationError, DulayniPaymentRequiredError


class AuthenticationManager:
    """Manages authentication workflows for different authentication methods."""

    def __init__(self):
        self.session_manager = SessionManager()
        self.console = Console()

    def handle_whatsapp_authentication(self, client, phone_number: str) -> bool:
        """Handle WhatsApp authentication workflow with session management."""
        session_data = self.session_manager.load_session()
        
        if (self.session_manager.is_session_valid(session_data) and 
            session_data.get("phone_number") == phone_number):
            # Use existing session
            client.set_auth_token(session_data["auth_token"])
            self.console.print("[green]Using existing authentication session[/green]")
            
            # Check balance after authentication
            try:
                balance_info = client.get_balance()
                self.console.print(f"[cyan]Account balance: {balance_info['balance']:.2f}[/cyan]")
                
                # Check if balance is sufficient
                if balance_info['balance'] < 50.0:
                    self.console.print("[yellow]Warning: Low balance (below than 50.0). Consider topping up your account.[/yellow]")
                    
            except DulayniPaymentRequiredError as e:
                self.console.print(Panel(
                    f"[red]Insufficient balance![/red]\n\n"
                    f"Current balance: {e.payment_info.get('current_balance', 0):.2f}\n"
                    f"Request cost: {e.payment_info.get('required_balance', 0):.2f}\n\n"
                    f"Please top up your account at: [blue][link={e.payment_info['payment_url']}]{e.payment_info['payment_url']}[/link][/blue]",
                    title="[bold red]⚠️  Payment Required[/bold red]",
                    border_style="red"
                ))
                # Continue with authentication but warn user
                self.console.print("[yellow]Authentication successful, but you need to top up to use the service.[/yellow]")
            except Exception as e:
                self.console.print(f"[yellow]Could not check balance: {str(e)}[/yellow]")
                
            return True
        else:
            # Start new authentication flow
            self.console.print(
                f"[yellow]Requesting verification code for {phone_number}...[/yellow]"
            )
            try:
                client.request_verification_code()
                code = self.console.input("[bold yellow]Enter 4-digit verification code: [/bold yellow]")
                verify_result = client.verify_code(code)
                
                # Save session data (assuming 24 hour expiry)
                self.session_manager.save_session({
                    "phone_number": phone_number,
                    "auth_token": verify_result.get("auth_token"),
                    "expiry_time": time.time() + 24 * 60 * 60  # 24 hours
                })
                
                # Check balance after successful authentication
                try:
                    balance_info = client.get_balance()
                    self.console.print(f"[cyan]Account balance: {balance_info['balance']:.2f}[/cyan]")
                    
                    # Check if balance is sufficient
                    if balance_info['balance'] < 50.0:
                        self.console.print("[yellow]Warning: Low balance (below than 50.0). Consider topping up your account.[/yellow]")
                        
                except DulayniPaymentRequiredError as e:
                    self.console.print(Panel(
                        f"[red]Insufficient balance![/red]\n\n"
                        f"Current balance: {e.payment_info.get('current_balance', 0):.2f}\n"
                        f"Request cost: {e.payment_info.get('required_balance', 0):.2f}\n\n"
                        f"Please top up your account at: [blue][link={e.payment_info['payment_url']}]{e.payment_info['payment_url']}[/link][/blue]",
                        title="[bold red]⚠️  Payment Required[/bold red]",
                        border_style="red"
                    ))
                    # Continue with authentication but warn user
                    self.console.print("[yellow]Authentication successful, but you need to top up to use the service.[/yellow]")
                except Exception as e:
                    self.console.print(f"[yellow]Could not check balance: {str(e)}[/yellow]")
                
                self.console.print("[green]✓ Authentication successful[/green]")
                return True
            except DulayniAuthenticationError as e:
                self.console.print(f"[red]Authentication failed: {str(e)}[/red]")
                return False

    def handle_dulayni_authentication(self) -> bool:
        """Handle Dulayni API key authentication (no session needed)."""
        self.console.print("[green]Using Dulayni API key (no session management needed)[/green]")
        self.console.print("[yellow]Note: API key users don't have billing accounts[/yellow]")
        return True

    def logout(self):
        """Clear authentication session (WhatsApp auth only)."""
        self.session_manager.clear_session()
        self.console.print("[green]Authentication session cleared[/green]")
