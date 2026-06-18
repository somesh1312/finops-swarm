"""
Agent 4: narrative_agent (AMD-powered via Ollama)

Responsibility: Wait until BOTH ActualsChecked AND BudgetImpact events
exist in the Band room for the same CO. Then call the local Ollama LLM
to generate a CFO-ready one-paragraph narrative. Post NarrativeReady event.

This is where AMD inference runs. No financial data leaves the machine.

In production: point OLLAMA_BASE_URL at your AMD ROCm server.
For the hackathon: Ollama CPU mode works fine — same API, just slower.
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv

from core.room import get_room
from core.models import (
    ActualsCheckedEvent,
    BudgetImpactEvent,
    ReconciliationNarrative,
    NarrativeReadyEvent,
)

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
VARIANCE_THRESHOLD_PCT = float(os.getenv("VARIANCE_THRESHOLD_PCT", "2.0"))
AGENT_NAME = "narrative_agent"


NARRATIVE_PROMPT = """You are a financial controller. Write a TWO-SENTENCE reconciliation note for the CFO. Be specific and direct. No preamble.

Sentence 1: State what happened — name {co_id}, the ${delta_value:,.0f} delta, and which systems are NOT yet updated (mainframe ERP: {mainframe_absorbed}, TM1 budget model: {tm1_reflected}).
Sentence 2: State the financial impact — committed cost ${committed_cost:,.0f} vs budget ${budget_before:,.0f}, variance {variance_pct:.2f}% against {threshold:.1f}% threshold, and one action.

Rules: Two sentences only. No bullet points. No markdown. No hedging words like 'may' or 'could'. State facts."""


async def call_ollama(prompt: str) -> str:
    """Call local Ollama instance. Falls back to template if Ollama is unavailable."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 200},
                },
            )
            response.raise_for_status()
            return response.json()["response"].strip()
    except Exception as e:
        print(f"[{AGENT_NAME}] Ollama unavailable ({e}) — using template fallback")
        return None


def template_narrative(data: dict) -> str:
    """Fallback narrative if Ollama is not running. Always produces valid output."""
    sync_issues = []
    if not data["mainframe_absorbed"]:
        sync_issues.append("the mainframe ERP")
    if not data["tm1_reflected"]:
        sync_issues.append("the TM1 budget model")

    systems_str = " and ".join(sync_issues) if sync_issues else "no systems"
    within = "within" if data["variance_pct"] <= data["threshold"] else "outside"

    return (
        f"Change Order {data['co_id']} for ${data['delta_value']:,.0f} was approved against "
        f"project {data['project_code']} but has not yet been reflected in {systems_str}. "
        f"The current committed cost of ${data['committed_cost']:,.0f} against a budget baseline "
        f"of ${data['budget_before']:,.0f} produces a variance of {data['variance_pct']:.2f}%, "
        f"which is {within} the {data['threshold']:.1f}% tolerance threshold. "
        f"{'Escalation to the finance controller is recommended before month-end close.' if data['requires_escalation'] else 'No immediate action required; update TM1 and ERP in the next processing cycle.'}"
    )


async def process_co_pair(room, co_id: str, actuals_payload: dict, budget_payload: dict):
    actuals_event = ActualsCheckedEvent(**actuals_payload)
    budget_event = BudgetImpactEvent(**budget_payload)

    s = actuals_event.status
    b = budget_event.impact
    variance_pct = abs(s.mainframe_variance / s.budget_baseline) * 100
    requires_escalation = not s.actuals_absorbed_co or not b.budget_reflected_in_tm1

    data = {
        "co_id": co_id,
        "project_code": s.project_code,
        "delta_value": s.budget_baseline * 0,  # placeholder; overridden below
        "budget_before": b.tm1_budget_before,
        "budget_after": b.tm1_budget_after,
        "committed_cost": s.committed_cost,
        "actual_cost": s.actual_cost,
        "mainframe_absorbed": s.actuals_absorbed_co,
        "tm1_reflected": b.budget_reflected_in_tm1,
        "variance_pct": round(variance_pct, 2),
        "threshold": VARIANCE_THRESHOLD_PCT,
        "requires_escalation": requires_escalation,
    }
    # delta_value from budget impact
    data["delta_value"] = b.budget_delta if b.budget_delta != 0 else abs(s.mainframe_variance)

    print(f"[{AGENT_NAME}] Generating narrative for {co_id} (AMD/Ollama)...")

    prompt = NARRATIVE_PROMPT.format(**data)
    summary = await call_ollama(prompt)
    if not summary:
        summary = template_narrative(data)

    narrative = ReconciliationNarrative(
        project_code=s.project_code,
        co_id=co_id,
        summary=summary,
        variance_pct=round(variance_pct, 2),
        requires_escalation=requires_escalation,
        recommended_action=(
            "Escalate to finance controller before month-end close."
            if requires_escalation
            else "Update systems in next processing cycle."
        ),
    )

    result = NarrativeReadyEvent(narrative=narrative)
    await room.post_event(
        event_type=result.event_type,
        payload=result.model_dump(mode="json"),
        agent_name=AGENT_NAME,
    )


async def run(room=None):
    if room is None:
        room = get_room()

    print(f"[{AGENT_NAME}] Starting — waiting for ActualsChecked + BudgetImpact pairs...")

    processed: set[str] = set()

    while True:
        actuals_events = await room.get_events("ActualsChecked")
        budget_events = await room.get_events("BudgetImpact")

        actuals_by_co = {e["payload"]["status"]["co_id"]: e["payload"] for e in actuals_events}
        budget_by_co = {e["payload"]["impact"]["co_id"]: e["payload"] for e in budget_events}

        # Only fire when BOTH agents have posted for the same CO
        ready_co_ids = set(actuals_by_co.keys()) & set(budget_by_co.keys())

        for co_id in ready_co_ids:
            if co_id in processed:
                continue
            await process_co_pair(
                room, co_id, actuals_by_co[co_id], budget_by_co[co_id]
            )
            processed.add(co_id)

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
