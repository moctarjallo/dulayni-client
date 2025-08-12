import requests
from typing import Optional
import click
from rich.console import Console
from rich.markdown import Markdown

console = Console()

@click.command()
@click.option("--model", "-m", default="gpt-4o-mini",
              type=click.Choice(["gpt-4o", "gpt-4o-mini"]))
@click.option("--openai_api_key", "-k", required=True, envvar="OPENAI_API_KEY")
@click.option("--query", "-q", type=str, required=False)
@click.option("--path2mcp_servers_file", "-mcp", default="config/mcp_servers.json",
              type=click.Path())
@click.option("--startup_timeout", "-t", default=10.0, type=float)
@click.option("--parallel_tool_calls", "-p", is_flag=True)
@click.option("--agent_type", "-a", default="react",
              type=click.Choice(["react", "deep_agent"]))
@click.option("--print_mode", default="rich",
              type=click.Choice(["json", "rich"]))
@click.option("--system_prompt", "-s", default=None,
              help="Custom system prompt for the agent")
@click.option("--api_url", default="http://localhost:8002/run_agent",
              help="URL of the Dulayni API server")
@click.option("--thread_id", default="default",
              help="Thread ID for conversation continuity")
def main(model: str, openai_api_key: str,
         query: Optional[str],
         path2mcp_servers_file: str,
         startup_timeout: float,
         parallel_tool_calls: bool,
         agent_type: str,
         print_mode: str,
         system_prompt: Optional[str],
         api_url: str,
         thread_id: str):
    """Dulayni CLI Client - Interact with dulayni RAG agents via API"""
    
    effective_system_prompt = system_prompt if system_prompt is not None else "You are a helpful agent"
    
    def run_query(content: str):
        """Use the API to execute the query"""
        payload = {
            "agent_type": agent_type,
            "role": "user",
            "model": model,
            "content": content,
            "system_prompt": effective_system_prompt,
            "thread_id": thread_id,
            "memory_db": "memory.sqlite",
            "mcp_servers_file": path2mcp_servers_file,
            "startup_timeout": startup_timeout,
            "parallel_tool_calls": parallel_tool_calls
        }
        
        try:
            response = requests.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.ConnectionError:
            return f"Connection Error: Could not connect to dulayni server at {api_url}. Make sure the server is running."
        except requests.exceptions.Timeout:
            return "Request timed out. The query may be taking too long to process."
        except requests.exceptions.RequestException as e:
            return f"API Error: {str(e)}"

    if query:
        # Batch mode
        result = run_query(query)
        if print_mode == "json":
            import json
            print(json.dumps({"response": result}, indent=2))
        else:
            console.print(Markdown(result))
    else:
        # Interactive mode
        console.print("[bold green]Dulayni Client - Interactive mode. Type 'q' to quit.[/bold green]")
        console.print(f"[yellow]Using API endpoint: {api_url}[/yellow]")
        console.print(f"[yellow]Agent type: {agent_type}[/yellow]")
        console.print(f"[yellow]Model: {model}[/yellow]")
        console.print(f"[yellow]Thread ID: {thread_id}[/yellow]")
        
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if user_input.strip().lower() == "q":
                    break
                if not user_input.strip():
                    continue
                    
                result = run_query(user_input)
                console.print(Markdown(result))
            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {str(e)}[/red]")

if __name__ == "__main__":
    main()
