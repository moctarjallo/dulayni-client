"""Session management for authentication persistence."""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional


class SessionManager:
    """Manages authentication session persistence."""

    def __init__(self):
        self.session_file = Path.home() / ".dulayni" / "session.json"

    def load_session(self) -> Optional[Dict[str, Any]]:
        """Load session data from file."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return None

    def save_session(self, session_data: Dict[str, Any]) -> None:
        """Save session data to file."""
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.session_file, "w") as f:
            json.dump(session_data, f)

    def clear_session(self) -> None:
        """Clear session data."""
        if self.session_file.exists():
            self.session_file.unlink()

    def is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """Check if session is still valid."""
        if not session_data or not session_data.get("auth_token"):
            return False
        
        # Check if token has expired (assuming 24 hour expiry)
        expiry_time = session_data.get("expiry_time", 0)
        return time.time() < expiry_time