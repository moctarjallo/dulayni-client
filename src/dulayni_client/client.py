import requests
from typing import Optional, Dict, Any
import json

from .exceptions import DulayniClientError, DulayniConnectionError, DulayniTimeoutError


class DulayniClient:
    """
    A client for interacting with dulayni RAG agents via API.

    This class provides both programmatic access to the dulayni server
    and can be used as a library in other applications.

    Args:
        api_url: URL of the Dulayni API server
        openai_api_key: OpenAI API key for authentication
        model: Model name to use (default: "gpt-4o-mini")
        agent_type: Type of agent ("react" or "deep_react")
        thread_id: Thread ID for conversation continuity
        system_prompt: Custom system prompt for the agent
        mcp_servers: Either a dictionary with MCP server configurations
                     or None to use no MCP servers
        memory_db: Path to SQLite database for conversation memory
        pg_uri: PostgreSQL URI for memory storage (alternative to SQLite)
        startup_timeout: Timeout for server startup
        parallel_tool_calls: Whether to enable parallel tool calls
        request_timeout: Timeout for API requests in seconds

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
        api_url: str = "http://localhost:8002/run_agent",
        openai_api_key: str = "",
        model: str = "gpt-4o-mini",
        agent_type: str = "react",
        thread_id: str = "default",
        system_prompt: Optional[str] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
        memory_db: str = "memory.sqlite",
        pg_uri: Optional[str] = None,
        startup_timeout: float = 10.0,
        parallel_tool_calls: bool = False,
        request_timeout: float = 30.0,
    ):
        self.api_url = api_url
        self.openai_api_key = openai_api_key
        self.model = model
        self.agent_type = agent_type
        self.thread_id = thread_id
        self.system_prompt = system_prompt or "You are a helpful agent"
        self.mcp_servers = mcp_servers or {}
        self.memory_db = memory_db
        self.pg_uri = pg_uri
        self.startup_timeout = startup_timeout
        self.parallel_tool_calls = parallel_tool_calls
        self.request_timeout = request_timeout

        # Validate inputs
        if not self.openai_api_key:
            raise DulayniClientError("OpenAI API key is required")

        if self.model not in ["gpt-4o", "gpt-4o-mini"]:
            raise DulayniClientError(f"Unsupported model: {self.model}")

        if self.agent_type not in ["react", "deep_react"]:
            raise DulayniClientError(f"Unsupported agent type: {self.agent_type}")

    def query(self, content: str, **kwargs) -> str:
        """
        Execute a query against the dulayni agent.

        Args:
            content: The query string to send to the agent
            **kwargs: Additional parameters to override instance defaults
                - model: Override the model for this query
                - agent_type: Override the agent type for this query
                - system_prompt: Override the system prompt for this query
                - thread_id: Override the thread ID for this query
                - memory_db: Override the memory database for this query
                - mcp_servers: Override the MCP servers config for this query

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
            **kwargs: Additional parameters to override instance defaults

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
        """Build the API payload with instance defaults and overrides."""
        return {
            "agent_type": kwargs.get("agent_type", self.agent_type),
            "role": "user",
            "model": kwargs.get("model", self.model),
            "content": content,
            "system_prompt": kwargs.get("system_prompt", self.system_prompt),
            "thread_id": kwargs.get("thread_id", self.thread_id),
            "memory_db": kwargs.get("memory_db", self.memory_db),
            "pg_uri": kwargs.get("pg_uri", self.pg_uri),
            "mcp_servers": kwargs.get("mcp_servers", self.mcp_servers),
            "startup_timeout": self.startup_timeout,
            "parallel_tool_calls": self.parallel_tool_calls,
        }

    def set_thread_id(self, thread_id: str) -> None:
        """Set the thread ID for conversation continuity."""
        self.thread_id = thread_id

    def set_system_prompt(self, system_prompt: str) -> None:
        """Set a new system prompt."""
        self.system_prompt = system_prompt

    def set_memory_db(self, memory_db: str) -> None:
        """Set the memory database path."""
        self.memory_db = memory_db

    def set_mcp_servers(self, mcp_servers: Dict[str, Any]) -> None:
        """Set the MCP servers configuration dictionary."""
        self.mcp_servers = mcp_servers

    def set_pg_uri(self, pg_uri: str) -> None:
        """Set the PostgreSQL URI for memory storage."""
        self.pg_uri = pg_uri

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
