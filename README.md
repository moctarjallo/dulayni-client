# dulayni-client

A CLI client for interacting with dulayni RAG agents via API.

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/your_org/dulayni-client.git
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

### Interactive Mode

Start an interactive REPL:

```bash
dulayni-client -k $OPENAI_API_KEY
```

### Batch Query Mode

Run a single query non-interactively:

```bash
dulayni-client -k $OPENAI_API_KEY -q "What's (3 + 5) x 12?" --print_mode rich
```

### Options

* `-m, --model`: Model name (default: `gpt-4o-mini`)
* `-k, --openai_api_key`: Your OpenAI API key
* `-q, --query`: Query string for batch mode
* `-a, --agent_type`: Agent type (`react` or `deep_agent`, default: `react`)
* `--api_url`: Dulayni server URL (default: `http://localhost:8002/run_agent`)
* `--thread_id`: Thread ID for conversation continuity (default: `default`)
* `--print_mode`: `json` or `rich` output format
* `--system_prompt`: Custom system prompt

## Requirements

- dulayni server running on the specified API URL
- OpenAI API key
- Python 3.12+
