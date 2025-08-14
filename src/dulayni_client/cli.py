import os
from typing import Optional
import click
from rich.console import Console
from rich.markdown import Markdown

from .client import DulayniClient
from .exceptions import DulayniClientError, DulayniConnectionError, DulayniTimeoutError

console = Console()


@click.command()
@click.option(
    "--model", "-m", default="gpt-4o-mini", type=click.Choice(["gpt-4o", "gpt-4o-mini"])
)
@click.option(
    "--openai_api_key",
    "-k",
    default=lambda: os.environ.get("OPENAI_API_KEY", ""),
    help="OpenAI API key (can also use OPENAI_API_KEY env var)",
)
@click.option("--query", "-q", type=str, required=False)
@click.option(
    "--mcp_servers",
    "-mcp",
    default="config/mcp_servers.json",
    help="Path to MCP servers JSON config file or JSON string",
)
@click.option("--startup_timeout", "-t", default=10.0, type=float)
@click.option("--parallel_tool_calls", "-p", is_flag=True)
@click.option(
    "--agent_type", "-a", default="react", type=click.Choice(["react", "deep_agent"])
)
@click.option("--print_mode", default="rich", type=click.Choice(["json", "rich"]))
@click.option(
    "--system_prompt", "-s", default=None, help="Custom system prompt for the agent"
)
@click.option(
    "--api_url",
    default="http://localhost:8002/run_agent",
    help="URL of the Dulayni API server",
)
@click.option(
    "--memory_db",
    default="memory.sqlite",
    help="Path to SQLite database for conversation memory",
)
@click.option(
    "--thread_id", default="default", help="Thread ID for conversation continuity"
)
def main(
    model: str,
    openai_api_key: str,
    query: Optional[str],
    mcp_servers: str,
    memory_db: str,
    startup_timeout: float,
    parallel_tool_calls: bool,
    agent_type: str,
    print_mode: str,
    system_prompt: Optional[str],
    api_url: str,
    thread_id: str,
):
    """Dulayni CLI Client - Interact with dulayni RAG agents via API"""

    if not openai_api_key:
        console.print(
            "[red]Error: OpenAI API key is required. Set OPENAI_API_KEY environment variable or use -k option.[/red]"
        )
        raise click.Abort()

    try:
        client = DulayniClient(
            api_url=api_url,
            openai_api_key=openai_api_key,
            model=model,
            agent_type=agent_type,
            thread_id=thread_id,
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            memory_db=memory_db,
            startup_timeout=startup_timeout,
            parallel_tool_calls=parallel_tool_calls,
        )
    except DulayniClientError as e:
        console.print(f"[red]Configuration Error: {str(e)}[/red]")
        raise click.Abort()

    if query:
        # Batch mode
        try:
            if print_mode == "json":
                result = client.query_json(query)
                import json

                print(json.dumps(result, indent=2))
            else:
                result = client.query(query)
                console.print(Markdown(result))
        except (DulayniConnectionError, DulayniTimeoutError, DulayniClientError) as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            raise click.Abort()
    else:
        # Interactive mode
        console.print(
            "[bold green]Dulayni Client - Interactive mode. Type 'q' to quit.[/bold green]"
        )
        console.print(f"[yellow]Using API endpoint: {api_url}[/yellow]")
        console.print(f"[yellow]Agent type: {agent_type}[/yellow]")
        console.print(f"[yellow]Model: {model}[/yellow]")
        console.print(f"[yellow]Thread ID: {thread_id}[/yellow]")

        # Health check
        console.print("[yellow]Checking server connection...[/yellow]")
        if not client.health_check():
            console.print(
                "[red]Warning: Unable to connect to server. Commands may fail.[/red]"
            )
        else:
            console.print("[green]✓ Server connection OK[/green]")

        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if user_input.strip().lower() == "q":
                    break
                if not user_input.strip():
                    continue

                result = client.query(user_input)
                console.print(Markdown(result))

            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye![/yellow]")
                break
            except (
                DulayniConnectionError,
                DulayniTimeoutError,
                DulayniClientError,
            ) as e:
                console.print(f"[red]Error: {str(e)}[/red]")
            except Exception as e:
                console.print(f"[red]Unexpected error: {str(e)}[/red]")


if __name__ == "__main__":
    main()
