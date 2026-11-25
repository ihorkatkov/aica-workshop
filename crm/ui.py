"""Local human console. Browser credentials are separate from agent API tokens."""

import hashlib
import hmac
from pathlib import Path
import secrets
import time
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from . import stages
from .server_types import DealAction, ResetDataset, ReviewChange, StageDecision


def install_ui(app, store):
    secret = secrets.token_bytes(32)
    workspace = "workshop"

    def sign(value):
        return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()

    def browser(request: Request):
        token = request.cookies.get("aica_human", "")
        try:
            value, signature = token.rsplit(".", 1)
            timestamp = int(value.split(":", 1)[0])
            valid = (
                hmac.compare_digest(signature, sign(value))
                and 0 <= time.time() - timestamp < 28800
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(
                401, "Open the CRM page again to renew your local session."
            )
        if request.method != "GET":
            if request.headers.get("origin") != str(request.base_url).rstrip(
                "/"
            ) or not hmac.compare_digest(
                request.headers.get("x-csrf-token", ""), token
            ):
                raise HTTPException(403, "Use the CRM page to perform this action.")

    @app.get("/", response_class=HTMLResponse)
    def console(request: Request):
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Open the local CRM directly.")
        value = f"{int(time.time())}:{secrets.token_urlsafe(24)}"
        token = value + "." + sign(value)
        html = (
            (Path(__file__).parent / "console.html")
            .read_text()
            .replace("__CSRF__", token)
        )
        response = HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
            },
        )
        response.set_cookie(
            "aica_human",
            token,
            httponly=True,
            samesite="strict",
            max_age=28800,
            path="/ui",
            secure=request.url.scheme == "https",
        )
        return response

    @app.get("/ui/state", dependencies=[Depends(browser)])
    def state(db=Depends(store)):
        return db.state(workspace)

    @app.post("/ui/reset", dependencies=[Depends(browser)])
    def reset(body: ResetDataset | None = None, db=Depends(store)):
        return db.reset(workspace, body.dataset if body else "kickoff")

    @app.post("/ui/proposals/{proposal_id}/decision", dependencies=[Depends(browser)])
    def decide(proposal_id: str, body: StageDecision, db=Depends(store)):
        try:
            return stages.decide(db, workspace, proposal_id, body)
        except NotImplementedError:
            raise HTTPException(
                501, "Stage decisions have not been implemented in this CRM."
            ) from None

    @app.post("/ui/deals/{deal_id}/write", dependencies=[Depends(browser)])
    def write(deal_id: str, body: DealAction, db=Depends(store)):
        return db.action(workspace, deal_id, body.action, actor="human")

    @app.post("/ui/deals/{deal_id}/review", dependencies=[Depends(browser)])
    def review(deal_id: str, body: ReviewChange, db=Depends(store)):
        return db.set_review(
            workspace,
            deal_id,
            body.status,
            valid_until=body.valid_until.isoformat() if body.valid_until else None,
            actor="human",
        )
