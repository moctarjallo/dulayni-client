"""Docker utilities for managing containers."""

import shutil
import subprocess


class DockerManager:
    """Manages Docker operations for dulayni infrastructure."""

    @staticmethod
    def is_available() -> bool:
        """Check if Docker is available on the system."""
        return shutil.which("docker") is not None

    def build_and_run_container(self, name: str, build_dir: str, network_mode: str = "host") -> bool:
        """Build and run a Docker container."""
        try:
            # Build the Docker image
            build_result = subprocess.run(
                ["docker", "build", "-t", name, "."],
                cwd=build_dir,
                capture_output=True,
                text=True
            )
            
            if build_result.returncode != 0:
                return False
            
            # Stop any existing container
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True
            )
            
            # Run the new container
            run_result = subprocess.run(
                ["docker", "run", "--name", name, f"--network", network_mode, "-d", name],
                capture_output=True,
                text=True
            )
            
            return run_result.returncode == 0
                
        except Exception:
            return False

    def is_container_running(self, container_name: str) -> bool:
        """Check if a container is running."""
        try:
            check_result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True
            )
            return container_name in check_result.stdout
        except Exception:
            return False