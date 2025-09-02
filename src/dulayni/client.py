#-> src/dulayni/client.py
import requests
from typing import Optional, Dict, Any, Generator
import json
import sseclient

from .exceptions import (
    DulayniClientError,
    DulayniConnectionError,
    DulayniTimeoutError,
    DulayniAuthenticationError,
)


class DulayniClient:
    """
    A client for interacting with dulayni RAG agents via API.

    This class provides both programmatic access to the dulayni server
    and can be used as a library in other applications.

    The client implements a two-factor authentication flow:
    1. User provides phone number
    2. Backend sends 4-digit verification code via WhatsApp
    3. User enters verification code
    4. Client can then make queries

    Alternatively, provide an Dulayni API key to skip authentication.

    All parameters are optional - if not provided, the server will use
    defaults from its configuration file.

    Args:
        api_url: URL of the Dulayni API server
        phone_number: Phone number for authentication
        dulayni_api_key: Dulayni API key to skip authentication
        model: Model name to use
        agent_type: Type of agent ("react" or "deep_react")
        thread_id: Thread ID for conversation continuity
        system_prompt: Custom system prompt for the agent
        mcp_servers: Dictionary with MCP server configurations
        memory_db: Path to SQLite database for conversation memory
        pg_uri: PostgreSQL URI for memory storage (alternative to SQLite)
        request_timeout: Timeout for API requests in seconds (client-side only)

    Example:
        >>> client = DulayniClient(
        ...     phone_number="+1234567890",
        ...     api_url="http://localhost:8002"
        ... )
        >>> # Authentication happens automatically on first query
        >>> response = client.query("What's 2+2?")
        >>> print(response)
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
        request_timeout: float = 300.0,  # Client-side timeout, not sent to server
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

        Args:
            phone_number: Phone number to send code to. If not provided, uses instance phone_number.

        Returns:
            Dict containing session_id and status

        Raises:
            DulayniAuthenticationError: If phone number is invalid or request fails
            DulayniConnectionError: If unable to connect to server
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

        Args:
            verification_code: 4-digit verification code
            session_id: Session ID from request_verification_code. If not provided, uses stored session_id.

        Returns:
            Dict containing auth_token and status

        Raises:
            DulayniAuthenticationError: If verification fails
            DulayniConnectionError: If unable to connect to server
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

        Args:
            verification_code_callback: Function that prompts user for verification code.
                                      If not provided, will raise an exception with session_id.

        Returns:
            bool: True if authentication successful

        Raises:
            DulayniAuthenticationError: If authentication fails or phone number not set
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
        
        Yields:
            Dict containing message data as it becomes available
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
                    yield json.loads(event.data)

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

        Automatically handles authentication if not already authenticated.

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
                - dulayni_api_key: Override the Dulayni API key for this query

        Returns:
            str: The response from the dulayni agent

        Raises:
            DulayniAuthenticationError: If authentication is required but fails
            DulayniConnectionError: If unable to connect to the server
            DulayniTimeoutError: If the request times out
            DulayniClientError: For other API errors
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

        Args:
            content: The query string to send to the agent
            **kwargs: Additional parameters to override instance values

        Returns:
            Dict[str, Any]: The full JSON response from the server

        Raises:
            DulayniAuthenticationError: If authentication is required but fails
            DulayniConnectionError: If unable to connect to the server
            DulayniTimeoutError: If the request times out
            DulayniClientError: For other API errors
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
        Check if the dulayni server is healthy and reachable using the /health endpoint.

        Returns:
            Dict[str, Any]: Health status response from server, or error info if unreachable
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

        Returns:
            bool: True if server is healthy, False otherwise
        """
        health_status = self.health_check()
        return health_status.get("status") == "healthy"
