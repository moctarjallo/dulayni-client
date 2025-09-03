"""Git repository management utilities."""

import subprocess
from pathlib import Path
from rich.console import Console

from ..config.templates import DEFAULT_GITIGNORE


class GitManager:
    """Manages Git repository operations for dulayni projects."""

    def __init__(self):
        self.console = Console()

    def initialize_repository(self) -> bool:
        """Initialize Git repository if not already initialized."""
        if Path(".git").exists():
            self.console.print("[yellow]Git repository already exists[/yellow]")
            return True
        
        try:
            result = subprocess.run(
                ["git", "init"],
                capture_output=True,
                text=True,
                cwd="."
            )
            
            if result.returncode == 0:
                self.console.print("[green]✓ Initialized Git repository[/green]")
                return True
            else:
                self.console.print(f"[red]Failed to initialize Git repository: {result.stderr}[/red]")
                return False
                
        except FileNotFoundError:
            self.console.print("[yellow]Git not found. Skipping Git initialization.[/yellow]")
            return True  # Don't fail the whole process if Git isn't available

    def create_gitignore(self):
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
                self.console.print("[green]✓ Updated existing .gitignore file[/green]")
            else:
                self.console.print("[yellow].gitignore already contains dulayni entries[/yellow]")
        else:
            # Create new .gitignore
            with open(gitignore_path, "w") as f:
                f.write(DEFAULT_GITIGNORE)
            self.console.print("[green]✓ Created .gitignore file[/green]")