"""Expose the same agent tools as ADK for one CRM workspace."""

import asyncio
import inspect
import json
from functools import wraps

from httpx import HTTPStatusError
from mcp.server.fastmcp import FastMCP
from lab.tools import crm_tools


def install_mcp(app, workspace, call_log):
    server = FastMCP("crm", stateless_http=True, streamable_http_path="/")

    def logged(tool):
        @wraps(tool)
        async def call(*args, **kwargs):
            if call_log is None:
                return await asyncio.to_thread(tool, *args, **kwargs)
            entry = {
                "tool": tool.__name__,
                "arguments": inspect.signature(tool).bind(*args, **kwargs).arguments,
            }
            try:
                entry["result"] = await asyncio.to_thread(tool, *args, **kwargs)
            except HTTPStatusError as error:
                entry["result"] = {
                    "status": "http_error",
                    "http_status": error.response.status_code,
                    "message": error.response.text,
                }
                raise
            finally:
                if "result" in entry:
                    with call_log.open("a") as log:
                        print(json.dumps(entry), file=log)
            return entry["result"]

        return call

    for tool in crm_tools(workspace):
        server.add_tool(logged(tool))
    app.mount(f"/workspaces/{workspace}/mcp", server.streamable_http_app())
    return server
