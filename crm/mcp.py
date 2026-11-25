"""Expose the same agent tools as ADK for one CRM workspace."""

import asyncio
import inspect
import json
from functools import wraps

from mcp.server.fastmcp import FastMCP
from lab.tools import crm_tools


def install_mcp(app, workspace, call_log):
    server = FastMCP("crm", stateless_http=True, streamable_http_path="/")

    def logged(tool):
        @wraps(tool)
        async def call(*args, **kwargs):
            result = await asyncio.to_thread(tool, *args, **kwargs)
            arguments = inspect.signature(tool).bind(*args, **kwargs).arguments
            if call_log is None:
                return result
            with call_log.open("a") as log:
                print(
                    json.dumps(
                        {
                            "tool": tool.__name__,
                            "arguments": arguments,
                            "result": result,
                        }
                    ),
                    file=log,
                )
            return result

        return call

    for tool in crm_tools(workspace):
        server.add_tool(logged(tool))
    app.mount(f"/workspaces/{workspace}/mcp", server.streamable_http_app())
    return server
