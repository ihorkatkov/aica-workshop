"""Serve the workshop CRM and its existing tools over MCP on one loopback port."""

import argparse
import os
from pathlib import Path

import uvicorn

from crm.server import create_app


def serve(directory, port, workspace):
    os.environ["CRM_URL"] = f"http://127.0.0.1:{port}"
    app = create_app(
        directory / "crm.sqlite",
        mcp_workspace=workspace,
        call_log=directory / "calls.jsonl",
    )
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("port", type=int)
    parser.add_argument("--workspace", default="workshop")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    if (args.directory / "crm.sqlite").exists():
        parser.error("Choose a fresh directory to preserve prior evidence")
    serve(args.directory, args.port, args.workspace)
