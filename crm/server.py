"""Run with uvicorn crm.server:app. This service alone owns the CRM database."""

from contextlib import asynccontextmanager
import os
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from .store import Store
from .server_types import ReviewChange

load_dotenv()


class Action(BaseModel):
    action: Literal["schedule_kickoff", "request_review_update"]


def create_app(path=None):
    path = path or os.getenv("CRM_DB", ".lab/crm.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        with Store(path) as store:
            try:
                store.require_workspace("workshop")
            except KeyError:
                store.reset("workshop")
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

    @app.get("/workspaces/{workspace}/state", dependencies=[Depends(human)])
    def state(workspace: str, db=Depends(store)):
        return db.state(workspace)

    @app.post("/workspaces/{workspace}/reset", dependencies=[Depends(human)])
    def reset(workspace: str, db=Depends(store)):
        return db.reset(workspace)

    @app.post(
        "/workspaces/{workspace}/deals/{deal_id}/write", dependencies=[Depends(reader)]
    )
    def write(workspace: str, deal_id: str, body: Action, db=Depends(store)):
        return db.action(workspace, deal_id, body.action, direct=True)

    @app.post(
        "/workspaces/{workspace}/deals/{deal_id}/propose",
        dependencies=[Depends(reader)],
    )
    def propose(workspace: str, deal_id: str, body: Action, db=Depends(store)):
        return db.action(workspace, deal_id, body.action)

    @app.get("/workspaces/{workspace}/proposals/{pid}", dependencies=[Depends(human)])
    def proposal(workspace: str, pid: str, db=Depends(store)):
        return db.proposal(workspace, pid)

    @app.post(
        "/workspaces/{workspace}/proposals/{pid}/approve", dependencies=[Depends(human)]
    )
    def approve(workspace: str, pid: str, db=Depends(store)):
        return db.approve(workspace, pid)

    @app.post(
        "/workspaces/{workspace}/proposals/{pid}/promote", dependencies=[Depends(human)]
    )
    def promote(workspace: str, pid: str, db=Depends(store)):
        return db.promote(workspace, pid)

    @app.post(
        "/workspaces/{workspace}/deals/{deal_id}/review", dependencies=[Depends(human)]
    )
    def review(workspace: str, deal_id: str, body: ReviewChange, db=Depends(store)):
        return db.set_review(workspace, deal_id, body.status)

    from .ui import install_ui

    install_ui(app, store)
    return app


app = create_app()
