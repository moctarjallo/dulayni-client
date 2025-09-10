"""FRPC management for tunneling and network access."""
from pathlib import Path
from rich.console import Console

from .docker import DockerManager
from ..templates import FRPC_TOML_TEMPLATE, DOCKERFILE_TEMPLATE, DOCKER_COMPOSE_TEMPLATE


class FRPCManager:
    """Manages FRPC (Fast Reverse Proxy Client) setup and configuration."""

    def __init__(self):
        self.console = Console()
        self.docker_manager = DockerManager()
        self.frpc_dir = Path(".frpc")

    def is_configured(self, identifier: str) -> bool:
        """Check if frpc is already configured for the given identifier (phone number or API key identifier)."""
        frpc_toml = self.frpc_dir / "frpc.toml"
        
        if not frpc_toml.exists():
            return False
        
        try:
            with open(frpc_toml, "r") as f:
                content = f.read()
                # Clean identifier for comparison (remove + and other special chars)
                clean_identifier = identifier.replace("+", "").replace("-", "").replace(" ", "")
                return clean_identifier in content
        except:
            return False

    def setup_frpc(self, identifier: str, host: str) -> bool:
        """Set up frpc configuration and Docker container."""
        self.frpc_dir.mkdir(exist_ok=True)
        
        # Clean identifier for URL (remove + and other special chars)
        clean_identifier = identifier.replace("+", "").replace("-", "").replace(" ", "")
        
        # Generate frpc.toml
        frpc_toml_content = FRPC_TOML_TEMPLATE.format(
            identifier=clean_identifier,
            host=host
        )
        with open(self.frpc_dir / "frpc.toml", "w") as f:
            f.write(frpc_toml_content)
        
        # Generate Dockerfile
        with open(self.frpc_dir / "Dockerfile", "w") as f:
            f.write(DOCKERFILE_TEMPLATE)
        
        # Generate docker-compose.yml
        with open(self.frpc_dir / "docker-compose.yml", "w") as f:
            f.write(DOCKER_COMPOSE_TEMPLATE)
        
        self.console.print(f"[green]Generated frpc configuration for identifier: {identifier}[/green]")
        
        # Build and start the Docker container if Docker is available
        if self.docker_manager.is_available():
            if self.docker_manager.build_and_run_container("dulayni-frpc", str(self.frpc_dir)):
                self.console.print("[green]FRPC Docker container started successfully[/green]")
                return True
            else:
                self.console.print("[yellow]Failed to start FRPC container[/yellow]")
                return False
        else:
            self.console.print("[yellow]Docker is not available. Please install Docker to run the FRPC container.[/yellow]")
            self.console.print("[yellow]You can manually run the container with: docker build -t dulayni-frpc . && docker run --name frpc --network host -d dulayni-frpc[/yellow]")
            return False
