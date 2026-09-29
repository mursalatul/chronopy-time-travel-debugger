"""
FastAPI backend for ChronoPy.

Endpoints:
  GET  /api/summary               — trace summary metadata
  GET  /api/events                — paginated list of events
  GET  /api/events/{step}         — single event
  GET  /api/frame/{step}          — full frame state at step
  GET  /api/source/{step}         — source lines around step
  GET  /api/var-history/{name}    — all changes to a variable
  GET  /api/causal-chain/{step}/{var} — causal chain for a var
  GET  /api/call-tree             — full flame-chart call tree
  POST /api/search                — find next/prev event matching criteria
  GET  /                          — serve the web UI (index.html)

WebSocket:
  WS   /ws                        — real-time cursor sync
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import orjson
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chronopy.replay.engine import ReplayEngine
from chronopy.tracer.events import EventKind
from chronopy.tracer.store import TraceStore


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def orjson_response(data) -> Response:
    return Response(content=orjson.dumps(data), media_type="application/json")


# ──────────────────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────────────────

def create_app(store: TraceStore) -> FastAPI:
    engine = ReplayEngine(store)
    app    = FastAPI(title="ChronoPy", version="0.1.0")

    # WebSocket connection manager
    connected_clients: list[WebSocket] = []

    async def broadcast(msg: dict):
        dead = []
        for ws in connected_clients:
            try:
                await ws.send_text(orjson.dumps(msg).decode())
            except Exception:
                dead.append(ws)
        for ws in dead:
            connected_clients.remove(ws)

    # ─────────────────────────────────────────────
    # WebSocket
    # ─────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        connected_clients.append(ws)
        # Send current cursor state on connect
        await ws.send_text(orjson.dumps({
            "type": "cursor",
            "data": engine.current_frame_summary(),
        }).decode())
        try:
            while True:
                text = await ws.receive_text()
                msg = json.loads(text)
                action = msg.get("action")
                if action == "jump":
                    engine.jump_to(int(msg["step"]))
                elif action == "forward":
                    engine.step_forward(int(msg.get("n", 1)))
                elif action == "backward":
                    engine.step_backward(int(msg.get("n", 1)))
                elif action == "find_var":
                    step = engine.find_var_change(
                        msg["var"], msg.get("direction", "next")
                    )
                    if step is not None:
                        engine.jump_to(step)
                elif action == "find_exception":
                    step = engine.find_exception(msg.get("direction", "next"))
                    if step is not None:
                        engine.jump_to(step)

                await broadcast({
                    "type": "cursor",
                    "data": engine.current_frame_summary(),
                })
        except WebSocketDisconnect:
            connected_clients.remove(ws)

    # ─────────────────────────────────────────────
    # REST API
    # ─────────────────────────────────────────────

    @app.get("/api/summary")
    def get_summary():
        return orjson_response(store.summary())

    @app.get("/api/events")
    def get_events(start: int = 0, limit: int = 200):
        end = min(start + limit, len(store))
        events = [ev.to_dict() for ev in store.iter_events(start, end)]
        return orjson_response({
            "events": events,
            "total":  len(store),
            "start":  start,
            "end":    end,
        })

    @app.get("/api/events/{step}")
    def get_event(step: int):
        ev = store.get(step)
        if ev is None:
            raise HTTPException(404, "step not found")
        return orjson_response(ev.to_dict())

    @app.get("/api/frame/{step}")
    def get_frame(step: int):
        ev = store.get(step)
        if ev is None:
            raise HTTPException(404, "step not found")
        engine.jump_to(step)
        return orjson_response(engine.current_frame_summary())

    @app.get("/api/source/{step}")
    def get_source(step: int, context: int = 10):
        ev = store.get(step)
        if ev is None:
            raise HTTPException(404, "step not found")
        lines = store.get_source(ev.frame.filename)
        lo = max(0, ev.lineno - context - 1)
        hi = min(len(lines), ev.lineno + context)
        return orjson_response({
            "filename":    ev.frame.filename,
            "lineno":      ev.lineno,
            "start_line":  lo + 1,
            "lines":       lines[lo:hi],
        })

    @app.get("/api/source-full")
    def get_full_source(filename: str):
        lines = store.get_source(filename)
        return orjson_response({"filename": filename, "lines": lines})

    @app.get("/api/var-history/{name}")
    def get_var_history(name: str):
        return orjson_response(store.var_history(name))

    @app.get("/api/vars")
    def get_all_vars():
        return orjson_response(store.all_var_names())

    @app.get("/api/causal-chain/{step}/{var}")
    def get_causal_chain(step: int, var: str):
        chain = store.causal_chain(step, var)
        return orjson_response(chain)

    @app.get("/api/call-tree")
    def get_call_tree():
        return orjson_response(engine.call_tree())

    class SearchRequest(BaseModel):
        query:     str
        direction: str = "next"   # "next" | "prev"
        kind:      Optional[str] = None
        var:       Optional[str] = None

    @app.post("/api/search")
    def search(req: SearchRequest):
        step = None
        if req.var:
            step = engine.find_var_change(req.var, req.direction)
        elif req.kind:
            try:
                kind = EventKind[req.kind.upper()]
                step = (
                    engine.next_event_of_kind(kind)
                    if req.direction == "next"
                    else engine.prev_event_of_kind(kind)
                )
            except KeyError:
                raise HTTPException(400, f"Unknown kind: {req.kind}")
        if step is not None:
            engine.jump_to(step)
            return orjson_response({"found": True, "step": step, **engine.current_frame_summary()})
        return orjson_response({"found": False})

    # ─────────────────────────────────────────────
    # Serve Web UI
    # ─────────────────────────────────────────────

    ui_dir = Path(__file__).parent.parent / "ui"

    @app.get("/")
    def serve_ui():
        index_path = ui_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text())
        return HTMLResponse("<h1>ChronoPy UI not found</h1>", status_code=404)

    # Serve static assets (JS, CSS) from the ui directory
    if ui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

    return app
