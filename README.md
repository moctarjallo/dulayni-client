# dulayni-client

A CLI client and Python library for interacting with dulayni RAG agents via API.

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/moctarjallo/dulayni-client.git
   cd dulayni-client
   ```

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
   export OPENAI_API_KEY="your_api_key_here"
   ```

## Usage

### As a Library

```python
from dulayni_client import DulayniClient

# Initialize the client
client = DulayniClient(
    openai_api_key="your-api-key",
    api_url="http://localhost:8002/run_agent"
)

# Simple query
response = client.query("What's the weather like?")
print(response)

# Query with custom parameters
response = client.query(
    "Solve this problem",
    model="gpt-4o",
    agent_type="deep_agent"
)

# Get full JSON response
json_response = client.query_json("Tell me a joke")

# Conversation with thread continuity
client.set_thread_id("my_conversation")
client.query("My name is John")
response = client.query("What's my name?")  # Should remember "John"

# Health check
if client.health_check():
    print("Server is running!")
```

### CLI Usage

#### Interactive Mode

Start an interactive REPL:

```bash
dulayni -k $OPENAI_API_KEY
```

#### Batch Query Mode

Run a single query non-interactively:

```bash
dulayni -k $OPENAI_API_KEY -q "What's (3 + 5) x 12?" --print_mode rich
```

### CLI Options

* `-m, --model`: Model name (default: `gpt-4o-mini`)
* `-k, --openai_api_key`: Your OpenAI API key
* `-q, --query`: Query string for batch mode
* `-a, --agent_type`: Agent type (`react` or `deep_agent`, default: `react`)
* `--api_url`: Dulayni server URL (default: `http://localhost:8002/run_agent`)
* `--thread_id`: Thread ID for conversation continuity (default: `default`)
* `--print_mode`: `json` or `rich` output format
* `--system_prompt`: Custom system prompt

## Library API Reference

### DulayniClient

The main client class for interacting with dulayni agents.

#### Constructor Parameters

- `api_url` (str): URL of the Dulayni API server
- `openai_api_key` (str): OpenAI API key for authentication
- `model` (str): Model name to use (default: "gpt-4o-mini")
- `agent_type` (str): Type of agent ("react" or "deep_agent")
- `thread_id` (str): Thread ID for conversation continuity
- `system_prompt` (str): Custom system prompt for the agent
- `request_timeout` (float): Timeout for API requests in seconds

#### Methods

- `query(content: str, **kwargs) -> str`: Execute a query and return response text
- `query_json(content: str, **kwargs) -> dict`: Execute a query and return full JSON
- `health_check() -> bool`: Check if server is reachable
- `set_thread_id(thread_id: str)`: Set thread ID for conversation continuity
- `set_system_prompt(prompt: str)`: Update the system prompt

#### Exceptions

- `DulayniClientError`: Base exception for client errors
- `DulayniConnectionError`: Raised when unable to connect to server
- `DulayniTimeoutError`: Raised when requests time out

## Examples

See the `examples/` directory for more detailed usage examples.

## Requirements

- dulayni server running on the specified API URL
- OpenAI API key
- Python 3.12+

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
