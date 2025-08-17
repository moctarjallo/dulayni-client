import os
from fastmcp import FastMCP

mcp = FastMCP("Dulayni")


@mcp.tool()
def ls(path: str) -> list:
    """Use this tool to physically list all files in given `path`"""
    return os.listdir(path)


def start_server(host: str = "0.0.0.0", port: int = 8003):
    mcp.run(transport="streamable-http", stateless_http=True, host=host, port=port)


if __name__ == "__main__":
    start_server()
