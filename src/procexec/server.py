"""FastMCP server setup and configuration for ProcExecMCP."""

import os
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP


@dataclass
class ServerConfig:
    """Server configuration from environment variables.

    Attributes:
        timeout_ms: Command timeout in milliseconds
        max_output_bytes: Maximum output size in bytes
        blocked_paths: List of paths to block access to
        enable_process_kill: Whether to enable the kill_process tool
    """

    timeout_ms: int = 30000  # Default 30 seconds
    max_output_bytes: int = 10 * 1024 * 1024  # Default 10MB
    blocked_paths: list[str] | None = None
    enable_process_kill: bool = True

    @classmethod
    def from_environment(cls) -> "ServerConfig":
        """Load configuration from environment variables.

        Environment Variables:
            PROCEXEC_TIMEOUT: Timeout in milliseconds (1000-300000)
            PROCEXEC_MAX_OUTPUT: Max output size in bytes (1024-104857600)
            PROCEXEC_BLOCKED_PATHS: Comma-separated list of blocked paths
            PROCEXEC_ENABLE_KILL: Enable process termination ("true"/"false")

        Returns:
            ServerConfig instance with values from environment

        Raises:
            ValueError: If configuration values are out of valid range
        """
        timeout_ms = int(os.getenv("PROCEXEC_TIMEOUT", "30000"))
        max_output = int(os.getenv("PROCEXEC_MAX_OUTPUT", str(10 * 1024 * 1024)))
        blocked = os.getenv("PROCEXEC_BLOCKED_PATHS", "").split(",")
        blocked_paths = [p.strip() for p in blocked if p.strip()]
        enable_kill = os.getenv("PROCEXEC_ENABLE_KILL", "true").lower() == "true"

        # Validation
        if timeout_ms < 1000 or timeout_ms > 300000:
            raise ValueError("PROCEXEC_TIMEOUT must be between 1000 and 300000 ms")
        if max_output < 1024 or max_output > 100 * 1024 * 1024:
            raise ValueError("PROCEXEC_MAX_OUTPUT must be between 1KB and 100MB")

        return cls(
            timeout_ms=timeout_ms,
            max_output_bytes=max_output,
            blocked_paths=blocked_paths if blocked_paths else None,
            enable_process_kill=enable_kill,
        )


# Initialize FastMCP server with structured output configuration
mcp = FastMCP("ProcExecMCP")

# Load configuration from environment variables
config = ServerConfig.from_environment()
