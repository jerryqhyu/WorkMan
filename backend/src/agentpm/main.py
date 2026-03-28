from __future__ import annotations

import argparse
import sys

import uvicorn

from .api import create_app
from .bootstrap import bootstrap_repo
from .config import get_settings
from .mcp_server import run_mcp


settings = get_settings()



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentpm-server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the local API server")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)
    serve.add_argument("--reload", action="store_true")

    mcp = subparsers.add_parser("mcp", help="Run the MCP server")
    mcp.add_argument("--port", type=int, default=settings.mcp_port)
    mcp.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")

    bootstrap = subparsers.add_parser("bootstrap-repo", help="Bootstrap repo files")
    bootstrap.add_argument("path")
    bootstrap.add_argument("--name", default=None)
    return parser



def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        uvicorn.run(
            create_app(),
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=settings.log_level,
        )
        return
    if args.command == "mcp":
        run_mcp(port=args.port, transport=args.transport)
        return
    if args.command == "bootstrap-repo":
        bootstrap_repo(args.path, args.name)
        return
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
