import ast
import requests
from typing import Optional, Dict, Any, Generator
import json
import sseclient
import time
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown
import re

from .exceptions import (
    DulayniClientError,
    DulayniConnectionError,
    DulayniTimeoutError,
    DulayniAuthenticationError,
)


class ToolExecutionDisplay:
    def __init__(self):
        self.console = Console()
        self.active_tools = {}
        self.live_displays = {}
        
    def start_tool(self, tool_name, tool_call_id, input_args):
        """Display tool execution start with a spinner"""
        self.active_tools[tool_call_id] = {
            "name": tool_name,
            "start_time": time.time(),
            "spinner": Spinner("dots", text=f"Executing {tool_name} on {input_args}..."),
        }

        # Create a panel for the tool execution
        panel = Panel(
            self.active_tools[tool_call_id]["spinner"],
            title=f"[bold blue]🛠️  Executing {tool_name}[/bold blue]",
            subtitle=f"Started at {time.strftime('%H:%M:%S')}",
            border_style="blue",
            padding=(1, 2),
        )

        # Start a live display for this tool
        self.live_displays[tool_call_id] = Live(
            panel, console=self.console, refresh_per_second=10
        )
        self.live_displays[tool_call_id].start()
        
    def end_tool(self, tool_name, tool_call_id, output, execution_time):
        """Display tool execution completion"""
        if tool_call_id in self.active_tools:
            # Stop the live display
            if tool_call_id in self.live_displays:
                self.live_displays[tool_call_id].stop()
                del self.live_displays[tool_call_id]

            # Format the output
            output_content = self._format_output(output)

            # Create completion panel
            completion_panel = Panel(
                output_content,
                title=f"[bold green]✅ Completed {tool_name}[/bold green]",
                subtitle=f"Execution time: {execution_time:.2f}s",
                border_style="green",
                padding=(1, 2),
            )

            self.console.print(completion_panel)
            del self.active_tools[tool_call_id]

    def _format_output(self, output):
        """Format the tool output appropriately"""
        if not output:
            return Text("No output", style="italic")

        # Try to detect and format JSON
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group())
                formatted_json = json.dumps(json_data, indent=2)
                return Syntax(formatted_json, "json", theme="monokai", line_numbers=True)
            except Exception:
                pass

        # Try to detect code blocks
        code_match = re.search(r"```(\w+)?\s*(.*?)```", output, re.DOTALL)
        if code_match:
            language = code_match.group(1) or "text"
            code_content = code_match.group(2).strip()
            return Syntax(code_content, language, theme="monokai", line_numbers=True)

        # Default to text with markdown rendering
        try:
            return Markdown(output)
        except Exception:
            return Text(output)

    def update_todos(self, todos_content):
        """Display todos in a formatted table with status indicators."""
        if not todos_content:
            return

        try:
            # Parse the todos JSON
            todos = ast.literal_eval(todos_content)

            if not todos:
                return

            # Create a table for todos
            table = Table(
                title="📋 Task List",
                show_header=True,
                header_style="bold magenta",
                box=None,
                padding=(0, 1),
                show_lines=True,
            )
            table.add_column("Status", style="cyan", justify="center", width=10)
            table.add_column("Task", style="white", no_wrap=False)

            # Add todos to table with appropriate status indicators
            for todo in todos:
                if not isinstance(todo, dict):
                    continue

                status = todo.get("status", "pending")
                task_content = todo.get("content", "Unknown task")

                # Format based on status
                if status == "completed":
                    status_icon = "[green]✅[/green]"
                    task_style = "dim"
                elif status == "in_progress":
                    status_icon = "[blue]🔄[/blue]"
                    task_style = "bold blue"
                else:  # pending
                    status_icon = "[yellow]⏳[/yellow]"
                    task_style = "yellow"

                table.add_row(
                    status_icon, f"[{task_style}]{task_content}[/{task_style}]"
                )

            # Add summary
            completed = sum(
                1
                for todo in todos
                if isinstance(todo, dict) and todo.get("status") == "completed"
            )
            in_progress = sum(
                1
                for todo in todos
                if isinstance(todo, dict) and todo.get("status") == "in_progress"
            )
            pending = sum(
                1
                for todo in todos
                if isinstance(todo, dict) and todo.get("status") == "pending"
            )

            summary_text = (
                f"[green]✅ {completed} completed[/green] | "
                f"[blue]🔄 {in_progress} in progress[/blue] | "
                f"[yellow]⏳ {pending} pending[/yellow]"
            )

            panel = Panel(
                table,
                title="[bold yellow]Task Management[/bold yellow]",
                subtitle=summary_text,
                border_style="yellow",
                padding=(1, 1),
            )
            self.console.print(panel)

        except Exception as e:
            # Silently fail on todos parsing errors
            self.console.print(f"[yellow]Could not parse todos: {e}[/yellow]")


class DulayniClient:
    """
    A client for interacting with dulayni RAG agents via API.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        phone_number: Optional[str] = None,
        dulayni_api_key: Optional[str] = None,
        model: Optional[str] = None,
        agent_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
        memory_db: Optional[str] = None,
        pg_uri: Optional[str] = None,
        request_timeout: float = 300.0,
    ):
        # Set API URL default, but remove /run_agent suffix for flexibility
        if api_url:
            self.base_url = api_url.rstrip("/").replace("/run_agent", "")
        else:
            self.base_url = "http://localhost:8002"

        self.api_url = f"{self.base_url}/run_agent"
        self.stream_api_url = f"{self.base_url}/run_agent_stream"
        self.auth_url = f"{self.base_url}/auth"
        self.verify_url = f"{self.base_url}/verify"

        # Store all parameters as-is (including None values)
        self.phone_number = phone_number
        self.dulayni_api_key = dulayni_api_key
        self.model = model
        self.agent_type = agent_type
        self.thread_id = thread_id
        self.system_prompt = system_prompt
        self.mcp_servers = mcp_servers
        self.memory_db = memory_db
        self.pg_uri = pg_uri
        self.request_timeout = request_timeout

        # Authentication state
        self.is_authenticated = False
        self.auth_token = None
        self.verification_session_id = None

        # Tool execution display
        self.tool_display = ToolExecutionDisplay()

    def set_auth_token(self, auth_token: str):
        """Set authentication token manually."""
        self.auth_token = auth_token
        self.is_authenticated = bool(auth_token)

    def set_dulayni_api_key(self, dulayni_api_key: str):
        """Set Dulayni API key manually."""
        self.dulayni_api_key = dulayni_api_key
        # If Dulayni API key is provided, skip authentication
        if dulayni_api_key:
            self.is_authenticated = True

    def request_verification_code(
        self, phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Request a verification code to be sent via WhatsApp.
        """
        # Skip if Dulayni API key is provided
        if self.dulayni_api_key:
            return {
                "status": "skipped",
                "message": "Dulayni API key provided, skipping WhatsApp authentication",
                "session_id": ""
            }

        phone = phone_number or self.phone_number
        if not phone:
            raise DulayniAuthenticationError(
                "Phone number is required for authentication"
            )

        payload = {"phone_number": phone}

        try:
            response = requests.post(
                self.auth_url, json=payload, timeout=self.request_timeout
            )
            response.raise_for_status()

            result = response.json()
            self.verification_session_id = result.get("session_id")

            # Update phone number if provided
            if phone_number:
                self.phone_number = phone_number

            return result

        except requests.exceptions.ConnectionError:
            raise DulayniConnectionError(
                f"Could not connect to dulayni server at {self.auth_url}. "
                "Make sure the server is running."
            )
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    raise DulayniAuthenticationError(
                        f"Authentication failed: {error_data.get('message', str(e))}"
                    )
                except json.JSONDecodeError:
                    pass
            raise DulayniAuthenticationError(f"Authentication request failed: {str(e)}")

    def verify_code(
        self, verification_code: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify the 4-digit code received via WhatsApp.
        """
        # Skip if Dulayni API key is provided
        if self.dulayni_api_key:
            return {
                "status": "skipped",
                "message": "Dulayni API key provided, skipping WhatsApp authentication",
                "auth_token": None
            }

        session = session_id or self.verification_session_id
        if not session:
            raise DulayniAuthenticationError(
                "No verification session. Call request_verification_code() first."
            )

        payload = {"session_id": session, "verification_code": verification_code}

        try:
            response = requests.post(
                self.verify_url, json=payload, timeout=self.request_timeout
            )
            response.raise_for_status()

            result = response.json()
            self.auth_token = result.get("auth_token")
            self.is_authenticated = bool(self.auth_token)

            return result

        except requests.exceptions.ConnectionError:
            raise DulayniConnectionError(
                f"Could not connect to dulayni server at {self.verify_url}. "
                "Make sure the server is running."
            )
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    raise DulayniAuthenticationError(
                        f"Verification failed: {error_data.get('message', str(e))}"
                    )
                except json.JSONDecodeError:
                    pass
            raise DulayniAuthenticationError(f"Verification request failed: {str(e)}")

    def authenticate(self, verification_code_callback=None) -> bool:
        """
        Complete authentication flow: request code and verify it.
        """
        # Skip if Dulayni API key is provided
        if self.dulayni_api_key:
            self.is_authenticated = True
            return True

        if not self.phone_number:
            raise DulayniAuthenticationError(
                "Phone number must be set before authentication"
            )

        # Request verification code
        auth_result = self.request_verification_code()

        if verification_code_callback:
            # Interactive flow
            code = verification_code_callback()
            verify_result = self.verify_code(code)
            return self.is_authenticated
        else:
            # Non-interactive - caller needs to handle verification separately
            raise DulayniAuthenticationError(
                f"Verification code sent to {self.phone_number}. "
                f"Call verify_code() with the 4-digit code. Session ID: {auth_result.get('session_id')}"
            )

    def query_stream(self, content: str, **kwargs) -> Generator[Dict[str, Any], None, None]:
        """
        Execute a query against the dulayni agent with streaming response.
        """
        # Check authentication - allow either Dulayni key or WhatsApp auth
        if not self.is_authenticated and not self.dulayni_api_key:
            raise DulayniAuthenticationError(
                "Authentication required. Call authenticate() or verify_code() first, or provide Dulayni API key."
            )

        payload = self._build_payload(content, **kwargs)
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            # Use the streaming endpoint
            response = requests.post(
                self.stream_api_url,
                json=payload,
                headers=headers,
                timeout=self.request_timeout,
                stream=True
            )

            # Handle authentication errors
            if response.status_code == 401:
                self.is_authenticated = False
                self.auth_token = None
                raise DulayniAuthenticationError(
                    "Authentication expired. Please authenticate again."
                )

            response.raise_for_status()
            
            # Parse Server-Sent Events
            client = sseclient.SSEClient(response)
            for event in client.events():
                if event.data:
                    data = json.loads(event.data)
                    
                    # Handle different event types
                    if data.get("type") == "tool_start":
                        self.tool_display.start_tool(
                            data["tool_name"], 
                            data["tool_call_id"],
                            data.get("input", {})
                        )
                    elif data.get("type") == "tool_end":
                        self.tool_display.end_tool(
                            data["tool_name"], 
                            data["tool_call_id"],
                            data.get("output", ""),
                            data.get("execution_time", 0)
                        )
                    elif data.get("type") == "todos_update":
                        self.tool_display.update_todos(data.get("content", ""))
                    elif data.get("type") == "message":
                        yield data

        except requests.exceptions.ConnectionError:
            raise DulayniConnectionError(
                f"Could not connect to dulayni server at {self.base_url}. "
                "Make sure the server is running."
            )
        except requests.exceptions.Timeout:
            raise DulayniTimeoutError(
                "Request timed out. The query may be taking too long to process."
            )
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 401:
                # Already handled above
                pass
            else:
                raise DulayniClientError(f"API Error: {str(e)}")

    def query(self, content: str, **kwargs) -> str:
        """
        Execute a query against the dulayni agent.
        """
        # Check authentication - allow either Dulayni key or WhatsApp auth
        if not self.is_authenticated and not self.dulayni_api_key:
            raise DulayniAuthenticationError(
                "Authentication required. Call authenticate() or verify_code() first, or provide Dulayni API key."
            )

        payload = self._build_payload(content, **kwargs)

        try:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.request_timeout,
            )

            # Handle authentication errors
            if response.status_code == 401:
                self.is_authenticated = False
                self.auth_token = None
                raise DulayniAuthenticationError(
                    "Authentication expired. Please authenticate again."
                )

            response.raise_for_status()
            return response.json().get("response", "")

        except requests.exceptions.ConnectionError:
            raise DulayniConnectionError(
                f"Could not connect to dulayni server at {self.api_url}. "
                "Make sure the server is running."
            )
        except requests.exceptions.Timeout:
            raise DulayniTimeoutError(
                "Request timed out. The query may be taking too long to process."
            )
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 401:
                # Already handled above
                pass
            else:
                raise DulayniClientError(f"API Error: {str(e)}")

    def query_json(self, content: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a query and return the full JSON response.
        """
        # Check authentication - allow either Dulayni key or WhatsApp auth
        if not self.is_authenticated and not self.dulayni_api_key:
            raise DulayniAuthenticationError(
                "Authentication required. Call authenticate() or verify_code() first, or provide Dulayni API key."
            )

        payload = self._build_payload(content, **kwargs)

        try:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.request_timeout,
            )

            # Handle authentication errors
            if response.status_code == 401:
                self.is_authenticated = False
                self.auth_token = None
                raise DulayniAuthenticationError(
                    "Authentication expired. Please authenticate again."
                )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError:
            raise DulayniConnectionError(
                f"Could not connect to dulayni server at {self.api_url}. "
                "Make sure the server is running."
            )
        except requests.exceptions.Timeout:
            raise DulayniTimeoutError(
                "Request timed out. The query may be taking too long to process."
            )
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 401:
                # Already handled above
                pass
            else:
                raise DulayniClientError(f"API Error: {str(e)}")

    def _build_payload(self, content: str, **kwargs) -> Dict[str, Any]:
        """Build the API payload, only including non-null parameters."""
        # Start with required fields
        payload = {
            "role": "user",  # Always required
            "content": content,  # Always required
        }

        # Add optional fields only if they are not None
        # Priority: kwargs > instance values
        optional_fields = [
            "agent_type",
            "model",
            "system_prompt",
            "thread_id",
            "memory_db",
            "pg_uri",
            "mcp_servers",
            "dulayni_api_key",
        ]

        for field in optional_fields:
            # Check kwargs first, then instance values
            value = kwargs.get(field)
            if value is None:
                value = getattr(self, field)

            # Only add to payload if not None
            if value is not None:
                payload[field] = value

        return payload

    def set_thread_id(self, thread_id: Optional[str]) -> None:
        """Set the thread ID for conversation continuity."""
        self.thread_id = thread_id

    def set_system_prompt(self, system_prompt: Optional[str]) -> None:
        """Set a new system prompt."""
        self.system_prompt = system_prompt

    def set_memory_db(self, memory_db: Optional[str]) -> None:
        """Set the memory database path."""
        self.memory_db = memory_db

    def set_mcp_servers(self, mcp_servers: Optional[Dict[str, Any]]) -> None:
        """Set the MCP servers configuration dictionary."""
        self.mcp_servers = mcp_servers

    def set_pg_uri(self, pg_uri: Optional[str]) -> None:
        """Set the PostgreSQL URI for memory storage."""
        self.pg_uri = pg_uri

    def set_model(self, model: Optional[str]) -> None:
        """Set the model name."""
        self.model = model

    def set_agent_type(self, agent_type: Optional[str]) -> None:
        """Set the agent type."""
        self.agent_type = agent_type

    def set_phone_number(self, phone_number: Optional[str]) -> None:
        """Set the phone number for authentication."""
        self.phone_number = phone_number
        # Reset authentication state when phone number changes
        self.is_authenticated = False
        self.auth_token = None
        self.verification_session_id = None

    def health_check(self) -> Dict[str, Any]:
        """
        Check if the dulayni server is healthy and reachable.
        """
        try:
            # Use the server's health endpoint
            health_url = f"{self.base_url}/health"
            response = requests.get(health_url, timeout=5.0)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "error": "connection_error",
                "message": f"Could not connect to dulayni server at {self.base_url}",
            }
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "error": "timeout",
                "message": "Health check request timed out",
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": "request_error",
                "message": f"Health check failed: {str(e)}",
            }

    def is_healthy(self) -> bool:
        """
        Simple boolean check if server is healthy.
        """
        health_status = self.health_check()
        return health_status.get("status") == "healthy"
