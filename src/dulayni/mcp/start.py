import os
import sys
import subprocess
import time
import socket
import requests
from pathlib import Path
from typing import Optional


# Default port for the MCP filesystem server
DEFAULT_PORT = 8003


def is_server_running(port: int = DEFAULT_PORT) -> bool:
    """Check if the MCP server is already running."""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=1)
        return response.status_code == 200
    except requests.RequestException:
        return False


def is_port_free(port: int) -> bool:
    """Check if a TCP port is free on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def wait_for_server(port: int, timeout: float = 5.0) -> bool:
    """Wait until the server responds as healthy or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if is_server_running(port):
            return True
        time.sleep(0.2)
    return False


def start_server(
    port: int = DEFAULT_PORT, directories: Optional[list] = None
) -> Optional[subprocess.Popen]:
    """
    Start the MCP filesystem server in a separate process.
    Returns the process handle if started, else None.
    """
    if is_server_running(port):
        print(f"MCP filesystem server already running on port {port}")
        return None

    if not is_port_free(port):
        print(f"Error: Port {port} is already in use.")
        return None

    if not directories:
        directories = [str(Path.cwd())]

    # Build command to start the server
    cmd = [
        sys.executable,
        "-m",
        "dulayni.mcp.filesystem",
        "--port",
        str(port),
    ] + directories

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
        )
    except Exception as e:
        print(f"Failed to start MCP filesystem server: {e}")
        return None

    # Wait until the server is ready
    if wait_for_server(port, timeout=5.0):
        print(f"Started MCP filesystem server on port {port}")
        return process
    else:
        print(f"Warning: Server did not become healthy on port {port}")
        # Try to read any error logs
        try:
            out, err = process.communicate(timeout=1)
            if err:
                print("Server error output:", err.decode(errors="ignore"))
        except Exception:
            pass
        return process  # still return it so caller can manage/kill


def stop_server(port: int = DEFAULT_PORT) -> bool:
    """Stop the MCP filesystem server via its shutdown endpoint."""
    try:
        response = requests.post(f"http://localhost:{port}/shutdown", timeout=1)
        if response.status_code == 200:
            print(f"Stopped MCP filesystem server on port {port}")
            return True
    except requests.RequestException:
        pass
    return False
