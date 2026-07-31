"""Run the Phase 4A MCP gateway as stdio or Streamable HTTP."""

import argparse
import asyncio

from app.observability.metrics import (
    MCP_SERVICE,
    initialize_service_metrics,
    start_prometheus_metrics_server,
)

from .gateway import MCPGateway


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="streamable-http",
    )
    args = parser.parse_args()
    gateway = MCPGateway()
    initialize_service_metrics(MCP_SERVICE)
    if gateway.settings.prometheus_metrics_port:
        start_prometheus_metrics_server(gateway.settings.prometheus_metrics_port)
    if args.transport == "stdio":
        asyncio.run(gateway.run_stdio())
    else:
        asyncio.run(gateway.run_http())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
