"""Run with uvicorn crm.server:app. This service alone owns the CRM database."""

from contextlib import asynccontextmanager
import os
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from . import stages
from .store import Store
from .server_types import DealAction, ReviewChange, StageProposal

load_dotenv()


def create_app(path=None, *, mcp_workspace="workshop", call_log=None):
    path = path or os.getenv("CRM_DB", ".lab/crm.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        with Store(path) as store:
            try:
                store.require_workspace("workshop")
            except KeyError:
                store.reset("workshop")
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="AICA synthetic CRM", lifespan=lifespan)

    def store():
        with Store(path) as db:
            yield db

    def reader(authorization: str = Header(default="")):
        if authorization not in {
            "Bearer " + os.getenv("CRM_AGENT_TOKEN", "workshop-agent"),
            "Bearer " + os.getenv("CRM_ADMIN_TOKEN", "workshop-human"),
        }:
            raise HTTPException(401, "CRM token required")
        return (
            "human"
            if authorization
            == "Bearer " + os.getenv("CRM_ADMIN_TOKEN", "workshop-human")
            else "agent"
        )

    def human(authorization: str = Header(default="")):
        if authorization != "Bearer " + os.getenv("CRM_ADMIN_TOKEN", "workshop-human"):
            raise HTTPException(403, "Human credential required")

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/health")
    def health():
        return {"status": "ok", "synthetic": True}

    @app.get("/workspaces/{workspace}/deals", dependencies=[Depends(reader)])
    def deals(workspace: str, query: str = "", db=Depends(store)):
        return db.deals(workspace, query)

    @app.get(
        "/workspaces/{workspace}/records/{record_id}", dependencies=[Depends(reader)]
    )
    def record(workspace: str, record_id: str, db=Depends(store)):
        return db.get(workspace, record_id)

    @app.post("/workspaces/{workspace}/deals/{deal_id}/proposals", dependencies=[Depends(reader)])
    def propose(workspace: str, deal_id: str, body: StageProposal, db=Depends(store)):
        return stages.propose(db, workspace, deal_id, body.to_stage, body.rationale)

    @app.get("/workspaces/{workspace}/state", dependencies=[Depends(human)])
    def state(workspace: str, db=Depends(store)):
        return db.state(workspace)

    @app.post("/workspaces/{workspace}/reset", dependencies=[Depends(human)])
    def reset(workspace: str, db=Depends(store)):
        return db.reset(workspace)

    @app.post(
        "/workspaces/{workspace}/deals/{deal_id}/write", dependencies=[Depends(reader)]
    )
    def write(
        workspace: str,
        deal_id: str,
        body: DealAction,
        actor=Depends(reader),
        db=Depends(store),
    ):
        return db.action(workspace, deal_id, body.action, actor=actor)

    @app.post(
        "/workspaces/{workspace}/deals/{deal_id}/review", dependencies=[Depends(human)]
    )
    def review(workspace: str, deal_id: str, body: ReviewChange, db=Depends(store)):
        return db.set_review(
            workspace,
            deal_id,
            body.status,
            valid_until=body.valid_until.isoformat() if body.valid_until else None,
            actor="human",
        )

    from .ui import install_ui

    from .mcp import install_mcp

    mcp = install_mcp(app, mcp_workspace, call_log)
    install_ui(app, store)
    return app


app = create_app()
