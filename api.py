"""
api.py — FastAPI backend

Exposes:
  GET  /escalations       → list all pending escalations
  POST /escalations       → called by escalation_agent to register a new one
  POST /escalations/{id}/approve  → human approves the reforecast
  POST /escalations/{id}/flag     → human flags for manual review
  GET  /room/events       → full Band room event log (for the demo audit trail)

Run alongside main.py:
    uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
import time

from core.models import EscalationRequest
from core.room import get_room

app = FastAPI(title="FinOps Swarm API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for demo — replace with DB on Day 5+
_escalations: dict[str, dict] = {}


class EscalationRecord(BaseModel):
    id: str
    request: EscalationRequest
    status: Literal["pending", "approved", "flagged"] = "pending"
    created_at: float
    resolved_at: float | None = None
    resolved_by: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "service": "finops-swarm"}


@app.post("/escalations", status_code=201)
async def create_escalation(request: EscalationRequest):
    record_id = f"{request.co_id}-{int(time.time())}"
    _escalations[record_id] = EscalationRecord(
        id=record_id,
        request=request,
        created_at=time.time(),
    ).model_dump()
    return {"id": record_id, "status": "pending"}


@app.get("/escalations")
async def list_escalations():
    return list(_escalations.values())


@app.post("/escalations/{record_id}/approve")
async def approve_escalation(record_id: str, reviewer: str = "finance-controller"):
    if record_id not in _escalations:
        raise HTTPException(status_code=404, detail="Escalation not found")
    _escalations[record_id]["status"] = "approved"
    _escalations[record_id]["resolved_at"] = time.time()
    _escalations[record_id]["resolved_by"] = reviewer
    return {"id": record_id, "status": "approved"}


@app.post("/escalations/{record_id}/flag")
async def flag_escalation(record_id: str, reviewer: str = "finance-controller"):
    if record_id not in _escalations:
        raise HTTPException(status_code=404, detail="Escalation not found")
    _escalations[record_id]["status"] = "flagged"
    _escalations[record_id]["resolved_at"] = time.time()
    _escalations[record_id]["resolved_by"] = reviewer
    return {"id": record_id, "status": "flagged"}


@app.get("/room/events")
async def room_events():
    room = get_room()
    events = await room.get_all_events()
    return {"room_id": room.room_id, "event_count": len(events), "events": events}
