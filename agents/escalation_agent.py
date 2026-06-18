"""
Agent 5: escalation_agent

Responsibility: Watch for NarrativeReady events where requires_escalation=True.
Build a structured EscalationRequest and post it to the Band room.
Also calls the FastAPI endpoint so the dashboard immediately shows the card.

This is the ONLY agent that triggers human interaction.
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv

from core.room import get_room
from core.models import (
    NarrativeReadyEvent,
    BudgetImpactEvent,
    ActualsCheckedEvent,
    EscalationRequest,
    EscalationRequestedEvent,
)

load_dotenv()

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = os.getenv("API_PORT", "8000")
AGENT_NAME = "escalation_agent"


async def notify_dashboard(escalation: EscalationRequest):
    """Push escalation to the FastAPI dashboard endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"http://{API_HOST}:{API_PORT}/escalations",
                json=escalation.model_dump(mode="json"),
            )
    except Exception as e:
        print(f"[{AGENT_NAME}] Dashboard notify failed (non-fatal): {e}")


async def process_narrative(room, narrative_payload: dict, actuals_by_co: dict, budget_by_co: dict):
    event = NarrativeReadyEvent(**narrative_payload)
    n = event.narrative

    if not n.requires_escalation:
        print(f"[{AGENT_NAME}] {n.co_id} — no escalation needed, skipping.")
        return

    # Pull supporting data from earlier room events
    actuals_data = actuals_by_co.get(n.co_id, {})
    budget_data = budget_by_co.get(n.co_id, {})

    s = actuals_data.get("status", {})
    b = budget_data.get("impact", {})

    escalation = EscalationRequest(
        project_code=n.project_code,
        co_id=n.co_id,
        narrative_summary=n.summary,
        variance_amount=s.get("mainframe_variance", 0),
        variance_pct=n.variance_pct,
        budget_before=b.get("tm1_budget_before", 0),
        budget_after=b.get("tm1_budget_after", 0),
        actuals_absorbed=s.get("actuals_absorbed_co", False),
        tm1_reflected=b.get("budget_reflected_in_tm1", False),
        recommended_action=n.recommended_action,
    )

    result = EscalationRequestedEvent(request=escalation)
    await room.post_event(
        event_type=result.event_type,
        payload=result.model_dump(mode="json"),
        agent_name=AGENT_NAME,
    )

    await notify_dashboard(escalation)
    print(f"[{AGENT_NAME}] ESCALATED: {n.co_id} — {n.project_code}")


async def run(room=None):
    if room is None:
        room = get_room()

    print(f"[{AGENT_NAME}] Starting — monitoring for NarrativeReady escalations...")

    processed: set[str] = set()

    while True:
        narrative_events = await room.get_events("NarrativeReady")
        actuals_events = await room.get_events("ActualsChecked")
        budget_events = await room.get_events("BudgetImpact")

        actuals_by_co = {e["payload"]["status"]["co_id"]: e["payload"] for e in actuals_events}
        budget_by_co = {e["payload"]["impact"]["co_id"]: e["payload"] for e in budget_events}

        for event in narrative_events:
            co_id = event["payload"]["narrative"]["co_id"]
            if co_id in processed:
                continue
            await process_narrative(room, event["payload"], actuals_by_co, budget_by_co)
            processed.add(co_id)

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
