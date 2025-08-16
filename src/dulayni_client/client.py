# client.py
import requests
from typing import Optional, Dict, Any
import json

from .exceptions import DulayniClientError, DulayniConnectionError, DulayniTimeoutError


class DulayniClient:
    """
    A client for interacting with dulayni RAG agents via API.

    This class provides both programmatic access to the dulayni server
    and can be used as a library in other applications.

    All parameters are optional - if not provided, the server will use
    defaults from its configuration file.

    Args:
        api_url: URL of the Dulayni API server
        openai_api_key: OpenAI API key for authentication
        model: Model name to use
        agent_type: Type of agent ("react" or "deep_react")
        thread_id: Thread ID for conversation continuity
        system_prompt: Custom system prompt for the agent
        mcp_servers: Dictionary with MCP server configurations
        memory_db: Path to SQLite database for conversation memory
        pg_uri: PostgreSQL URI for memory storage (alternative to SQLite)
        startup_timeout: Timeout for server startup
        parallel_tool_calls: Whether to enable parallel tool calls
        request_timeout: Timeout for API requests in seconds (client-side only)

    Example:
        >>> client = DulayniClient(
        ...     openai_api_key="your-key-here",
        ...     api_url="http://localhost:8002/run_agent"
        ... )
        >>> response = client.query("What's 2+2?")
        >>> print(response)
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        model: Optional[str] = None,
        agent_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
        memory_db: Optional[str] = None,
        pg_uri: Optional[str] = None,
        startup_timeout: Optional[float] = None,
        parallel_tool_calls: Optional[bool] = None,
        request_timeout: float = 30.0,  # Client-side timeout, not sent to server
    ):
        # Only set API URL default here since it's required for client functionality
        self.api_url = api_url or "http://localhost:8002/run_agent"

        # Store all parameters as-is (including None values)
        self.openai_api_key = openai_api_key
        self.model = model
        self.agent_type = agent_type
        self.thread_id = thread_id
        self.system_prompt = system_prompt
        self.mcp_servers = mcp_servers
        self.memory_db = memory_db
        self.pg_uri = pg_uri
        self.startup_timeout = startup_timeout
        self.parallel_tool_calls = parallel_tool_calls
        self.request_timeout = request_timeout

    def query(self, content: str, **kwargs) -> str:
        """
        Execute a query against the dulayni agent.

        Args:
            content: The query string to send to the agent
            **kwargs: Additional parameters to override instance values
                - model: Override the model for this query
                - agent_type: Override the agent type for this query
                - system_prompt: Override the system prompt for this query
                - thread_id: Override the thread ID for this query
                - memory_db: Override the memory database for this query
                - mcp_servers: Override the MCP servers config for this query
                - pg_uri: Override the PostgreSQL URI for this query
                - startup_timeout: Override the startup timeout for this query
                - parallel_tool_calls: Override parallel tool calls setting

        Returns:
            str: The response from the dulayni agent

        Raises:
            DulayniConnectionError: If unable to connect to the server
            DulayniTimeoutError: If the request times out
            DulayniClientError: For other API errors
        """
        payload = self._build_payload(content, **kwargs)

        try:
            response = requests.post(
                self.api_url, json=payload, timeout=self.request_timeout
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
            raise DulayniClientError(f"API Error: {str(e)}")

    def query_json(self, content: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a query and return the full JSON response.

        Args:
            content: The query string to send to the agent
            **kwargs: Additional parameters to override instance values

        Returns:
            Dict[str, Any]: The full JSON response from the server

        Raises:
            DulayniConnectionError: If unable to connect to the server
            DulayniTimeoutError: If the request times out
            DulayniClientError: For other API errors
        """
        payload = self._build_payload(content, **kwargs)

        try:
            response = requests.post(
                self.api_url, json=payload, timeout=self.request_timeout
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
            "startup_timeout",
            "parallel_tool_calls",
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

    def set_parallel_tool_calls(self, parallel_tool_calls: Optional[bool]) -> None:
        """Set the parallel tool calls setting."""
        self.parallel_tool_calls = parallel_tool_calls

    def set_startup_timeout(self, startup_timeout: Optional[float]) -> None:
        """Set the startup timeout."""
        self.startup_timeout = startup_timeout

    def health_check(self) -> Dict[str, Any]:
        """
        Check if the dulayni server is healthy and reachable using the /health endpoint.

        Returns:
            Dict[str, Any]: Health status response from server, or error info if unreachable
        """
        try:
            # Use the server's health endpoint
            health_url = self.api_url.replace("/run_agent", "/health")
            response = requests.get(health_url, timeout=5.0)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "error": "connection_error",
                "message": f"Could not connect to dulayni server at {self.api_url}",
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

        Returns:
            bool: True if server is healthy, False otherwise
        """
        health_status = self.health_check()
        return health_status.get("status") == "healthy"
