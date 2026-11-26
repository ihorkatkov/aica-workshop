"""Thin HTTP tools. All validation and writes happen in the CRM service."""

import os
from urllib.parse import quote
import httpx
from . import config


def request(workspace, method, path, *, human=False, **kwargs):
    token = (
        os.getenv("CRM_ADMIN_TOKEN", "workshop-human")
        if human
        else os.getenv("CRM_AGENT_TOKEN", "workshop-agent")
    )
    url = os.getenv("CRM_URL", "http://127.0.0.1:8001").rstrip("/")
    response = httpx.request(
        method,
        f"{url}/workspaces/{quote(workspace, safe='')}/{path}",
        headers={"Authorization": "Bearer " + token},
        timeout=15,
        **kwargs,
    )
    if not human and response.status_code in (404, 422):
        return {
            "status": "rejected",
            "code": f"CRM_{response.status_code}",
            "message": response.json().get("detail"),
            "next_step": "Search deals and use the exact CRM ID and supported action.",
        }
    response.raise_for_status()
    return response.json()


def crm_tools(workspace):
    tools = []

    def tool(function):
        tools.append(function)
        return function

    @tool
    def search_deals(query: str = "") -> list[dict]:
        """Search deals by company, site, ID or status. Empty query lists all deals."""
        return request(workspace, "GET", "deals", params={"query": query})

    @tool
    def get_record(record_id: str) -> dict:
        """Read a deal (D-), company (C-), contact (P-), or saved stage proposal (PR-) by ID."""
        return request(workspace, "GET", f"records/{quote(record_id, safe='')}")

    @tool
    def write_deal(deal_id: str, action: str) -> dict:
        """Apply schedule_kickoff or request_review_update to the specified deal."""
        return request(
            workspace,
            "POST",
            f"deals/{quote(deal_id, safe='')}/write",
            json={"action": action},
        )

    return tools
