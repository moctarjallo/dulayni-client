# dulayni-client

A CLI client and Python library for interacting with dulayni RAG agents via API.

---

## Installation

1. **Clone the repository**:

    ```bash
   git clone https://github.com/moctarjallo/dulayni-client.git
   cd dulayni-client
    ````

2. **Ensure Python 3.12 is installed**:

   ```bash
   python --version  # should output 3.12.x
   ```

3. **Create a virtual environment & install dependencies**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

4. **Set environment variables**:

   ```bash
   export PHONE_NUMBER="+1234567890"
   ```

---

## Authentication Flow

The dulayni-client implements a secure two-factor authentication system:

1. **Request Verification**: Client sends phone number to `/auth` endpoint
2. **Receive Code**: Server sends 4-digit verification code via WhatsApp
3. **Verify Code**: Client submits the code to `/verify` endpoint
4. **Get Token**: Server returns authentication token for API access
5. **Make Queries**: All subsequent queries include the auth token

---

## Usage

### As a Library

```python
from dulayni import DulayniClient

# Initialize the client
client = DulayniClient(
    phone_number="+1234567890",
    api_url="http://localhost:8002"
)

# Authenticate (will prompt for verification code)
def get_verification_code():
    return input("Enter 4-digit verification code: ")

client.request_verification_code()
code = get_verification_code()
client.verify_code(code)

# Now you can make queries
response = client.query("What's the weather like?")
print(response)

# Alternative: handle authentication manually
client = DulayniClient(phone_number="+1234567890")
auth_result = client.request_verification_code()
print(f"Verification code sent! Session ID: {auth_result['session_id']}")

# User receives code via WhatsApp, then:
verification_code = "1234"  # Code from WhatsApp
client.verify_code(verification_code)

# Query with custom parameters
response = client.query(
    "Solve this problem",
    model="gpt-4o",
    agent_type="deep_react"
)

# Get full JSON response
json_response = client.query_json("Tell me a joke")

# Health check with detailed status
health_status = client.health_check()
print("Server status:", health_status)

# Simple health check
if client.is_healthy():
    print("Server is running!")

# Conversation with thread continuity
client.set_thread_id("my_conversation")
client.query("My name is John")
response = client.query("What's my name?")  # Should remember "John"
```

---

### CLI Usage

The CLI handles the authentication flow automatically by prompting for the verification code.

#### Interactive Mode

Start an interactive REPL:

```bash
dulayni-client -p "+1234567890"
```

The client will:

* Send a verification code to your WhatsApp
* Prompt you to enter the 4-digit code
* Start the interactive session once authenticated

#### Batch Query Mode

Run a single query non-interactively:

```bash
dulayni-client -p "+1234567890" -q "What's (3 + 5) x 12?" --print_mode rich
```

The authentication flow will complete before executing the query.

---

### CLI Options

* `-m, --model`: Model name (default: `gpt-4o-mini`)
* `-p, --phone-number`: Your phone number for authentication (**required**)
* `-q, --query`: Query string for batch mode
* `-a, --agent_type`: Agent type (`react` or `deep_react`, default: `react`)
* `--api_url`: Dulayni server URL (default: `http://localhost:8002/run_agent`)
* `--thread_id`: Thread ID for conversation continuity (default: `default`)
* `--print_mode`: Output format (`json` or `rich`)
* `--system_prompt`: Custom system prompt

---

## Library API Reference

### `DulayniClient`

The main client class for interacting with dulayni agents.

#### Constructor Parameters

* `api_url (str)`: URL of the Dulayni API server (without `/run_agent` suffix)
* `phone_number (str)`: Phone number for authentication
* `model (str)`: Model name to use (default: `"gpt-4o-mini"`)
* `agent_type (str)`: Type of agent (`"react"` or `"deep_react"`)
* `thread_id (str)`: Thread ID for conversation continuity
* `system_prompt (str)`: Custom system prompt for the agent
* `mcp_servers (dict)`: MCP server configurations
* `memory_db (str)`: Path to SQLite database for conversation memory
* `pg_uri (str)`: PostgreSQL URI for memory storage
* `request_timeout (float)`: Timeout for API requests in seconds

#### Methods

**Authentication**

* `request_verification_code(phone_number: str = None) -> dict`
* `verify_code(verification_code: str, session_id: str = None) -> dict`
* `authenticate(verification_code_callback = None) -> bool`

**Query**

* `query(content: str, **kwargs) -> str`
* `query_json(content: str, **kwargs) -> dict`

**Utility**

* `health_check() -> dict`
* `is_healthy() -> bool`
* `set_thread_id(thread_id: str)`
* `set_system_prompt(prompt: str)`
* `set_phone_number(phone_number: str)`

#### Exceptions

* `DulayniClientError` – Base exception for client errors
* `DulayniConnectionError` – Raised when unable to connect to server
* `DulayniTimeoutError` – Raised when requests time out
* `DulayniAuthenticationError` – Raised when authentication fails or is required

---

## Examples

See the `examples/` directory for more detailed usage examples.

---

## Requirements

* dulayni server running on the specified API URL
* Phone number for authentication
* Python 3.12+

---

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Format code:

```bash
black src/ tests/
ruff check src/ tests/
```
