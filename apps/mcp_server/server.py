"""Run the Phase 4A MCP gateway as stdio or Streamable HTTP."""

import argparse
import asyncio

from .gateway import MCPGateway


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="streamable-http")
    args = parser.parse_args()
    gateway = MCPGateway()
    if args.transport == "stdio":
        asyncio.run(gateway.run_stdio())
    else:
        asyncio.run(gateway.run_http())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
