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
        agent_type: Type of agent ("react" or "deep_agent")
        thread_id: Thread ID for conversation continuity
        system_prompt: Custom system prompt for the agent
        mcp_servers: Either a file path to MCP servers JSON config (server-side)
                     or a JSON string with MCP server configuration
        memory_db: Path to SQLite database for conversation memory
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
        mcp_servers: str = "config/mcp_servers.json",
        memory_db: str = "memory.sqlite",
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
        self.mcp_servers = mcp_servers
        self.memory_db = memory_db
        self.startup_timeout = startup_timeout
        self.parallel_tool_calls = parallel_tool_calls
        self.request_timeout = request_timeout

        # Validate inputs
        if not self.openai_api_key:
            raise DulayniClientError("OpenAI API key is required")

        if self.model not in ["gpt-4o", "gpt-4o-mini"]:
            raise DulayniClientError(f"Unsupported model: {self.model}")

        if self.agent_type not in ["react", "deep_agent"]:
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
            "mcp_servers_file": kwargs.get("mcp_servers", self.mcp_servers),
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

    def set_mcp_servers(self, mcp_servers: str) -> None:
        """Set the MCP servers configuration (file path or JSON string)."""
        self.mcp_servers = mcp_servers

    def health_check(self) -> bool:
        """
        Check if the dulayni server is healthy and reachable.

        Returns:
            bool: True if server is reachable, False otherwise
        """
        try:
            # Try a simple test query
            self.query("ping", system_prompt="Respond with 'pong'")
            return True
        except (DulayniConnectionError, DulayniTimeoutError, DulayniClientError):
            return False
