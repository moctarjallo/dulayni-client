"""Authentication management for different authentication methods."""

import time
from typing import Dict, Any, Optional
from rich.console import Console

from .session import SessionManager
from ..exceptions import DulayniAuthenticationError


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
                
                self.console.print("[green]✓ Authentication successful[/green]")
                return True
            except DulayniAuthenticationError as e:
                self.console.print(f"[red]Authentication failed: {str(e)}[/red]")
                return False

    def handle_dulayni_authentication(self) -> bool:
        """Handle Dulayni API key authentication (no session needed)."""
        self.console.print("[green]Using Dulayni API key (no session management needed)[/green]")
        return True

    def logout(self):
        """Clear authentication session (WhatsApp auth only)."""
        self.session_manager.clear_session()