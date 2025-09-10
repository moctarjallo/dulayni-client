# Default .gitignore content
DEFAULT_GITIGNORE = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Logs
*.log

# Dulayni specific
.frpc/
memory.sqlite
session.json
.dulayni_key
"""

# Default config template
DEFAULT_CONFIG_TEMPLATE = """{{
  "phone_number": "{phone_number}",
  "api_url": "http://dulayni.kajande.com:8002",
  
  "agent": {{
    "model": "gpt-4o-mini",
    "agent_type": "deep_react",
    "system_prompt": "You are a helpful assistant for customer support tasks.",
    "startup_timeout": 30.0,
    "parallel_tool_calls": true
  }},
  
  "memory": {{
    "memory_db": "memory.sqlite",
    "pg_uri": null,
    "thread_id": "{phone_number_clean}"
  }},
  
  "mcpServers": {{
    "local": {{
      "url": "http://{phone_number_clean}.{relay_host}.nip.io/mcp",
      "transport": "streamable_http"
    }}
  }}
}}"""

# Config template for Dulayni API key usage
DULAYNI_CONFIG_TEMPLATE = """{{
  "dulayni_api_key_file": ".dulayni_key",
  "api_url": "http://0.0.0.0:8002",
  
  "agent": {{
    "model": "gpt-5-mini",
    "agent_type": "deep_react",
    "system_prompt": "You are a helpful assistant for customer support tasks.",
    "startup_timeout": 30.0,
    "parallel_tool_calls": true
  }},
  
  "memory": {{
    "memory_db": "memory.sqlite",
    "pg_uri": null,
    "thread_id": "{api_key_number}"
  }},
  
  "mcpServers": {{
    "filesystem": {{
      "url": "http://{api_key_number}.{relay_host}.nip.io/mcp",
      "transport": "streamable_http"
    }}
  }}
}}"""
