"""Entry point for ProcExecMCP server."""

import sys

from .server import mcp

# Import all tool modules to register @mcp.tool() decorators
from .tools import search, execute, processes  # noqa: F401


def main() -> None:
    """Main entry point for ProcExecMCP server.

    Starts the FastMCP server with stdio transport for MCP protocol communication.
    """
    try:
        # Run FastMCP server with stdio transport (default for MCP)
        mcp.run()
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
