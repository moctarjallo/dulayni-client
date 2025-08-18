import os
import sys
import subprocess
import time
import requests
import threading
from pathlib import Path
from typing import Optional

# Default port for the MCP filesystem server
DEFAULT_PORT = 8003

def is_server_running(port: int = DEFAULT_PORT) -> bool:
    """Check if the MCP server is already running."""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=1)
        return response.status_code == 200
    except requests.ConnectionError:
        return False

def start_server(port: int = DEFAULT_PORT, directories: Optional[list] = None):
    """Start the MCP filesystem server in a separate process."""
    if is_server_running(port):
        print(f"MCP filesystem server already running on port {port}")
        return

    # FIXED: Get current directory at runtime, not import time
    if not directories:
        directories = [str(Path.cwd())]
    
    # Build command to start the server
    cmd = [
        sys.executable, 
        "-m", 
        "dulayni_client.mcp.filesystem",
        "--port", str(port)
    ] + directories
    
    # Start the server in a daemon process
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    # Wait briefly for server to start
    time.sleep(0.5)
    
    if is_server_running(port):
        print(f"Started MCP filesystem server on port {port}")
    else:
        print(f"Warning: Server may not have started properly on port {port}")

def stop_server(port: int = DEFAULT_PORT):
    """Stop the MCP filesystem server."""
    try:
        response = requests.post(f"http://localhost:{port}/shutdown", timeout=1)
        if response.status_code == 200:
            print(f"Stopped MCP filesystem server on port {port}")
            return True
    except requests.ConnectionError:
        pass
    return False
