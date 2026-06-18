"""
core/room.py — Band shared room (REAL SDK implementation)

All 6 agents connect to Band's platform and coordinate through
a shared chat room. Events are posted as structured JSON messages.

The event API (post_event, get_events, wait_for) is identical to
the local stub used during development — only the transport changed.
"""

import asyncio
import json
import time
import os
from typing import Any
from rich.console import Console
from rich.panel import Panel

console = Console()

# Try to import real Band SDK — fall back to local stub if unavailable
try:
    from band import Agent
    from band.config import load_agent_config
    BAND_SDK_AVAILABLE = True
except ImportError:
    BAND_SDK_AVAILABLE = False
    console.print("[yellow]Band SDK not found — using local stub[/yellow]")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")

# Map agent names to config keys
AGENT_CONFIG_MAP = {
    "change_order_watcher": "co_watcher",
    "mainframe_recon": "mainframe_recon",
    "budget_impact": "budget_impact",
    "narrative_agent": "narrative_agent",
    "escalation_agent": "escalation_agent",
    "weekly_cost_agent": "weekly_cost",
}

# Band room ID — all agents join this same room
BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "finops-recon-room")


class BandRoom:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self._local_events: list[dict] = []
        self._lock = asyncio.Lock()
        self._agents: dict[str, Any] = {}

    async def _get_agent(self, agent_name: str):
        """Get or create Band agent connection for this agent."""
        if not BAND_SDK_AVAILABLE:
            return None
        if agent_name in self._agents:
            return self._agents[agent_name]
        try:
            config_key = AGENT_CONFIG_MAP.get(agent_name, agent_name)
            agent_id, api_key = load_agent_config(config_key, config_path=CONFIG_PATH)
            agent = Agent(id=agent_id, api_key=api_key)
            self._agents[agent_name] = agent
            console.print(f"[green]✓ {agent_name} connected to Band[/green]")
            return agent
        except Exception as e:
            console.print(f"[yellow]Band connect warning ({agent_name}): {e}[/yellow]")
            return None

    async def post_event(
        self, event_type: str, payload: dict[str, Any], agent_name: str
    ) -> None:
        event = {
            "event_type": event_type,
            "agent": agent_name,
            "timestamp": time.time(),
            "payload": payload,
        }

        async with self._lock:
            self._local_events.append(event)

        # Post to real Band room
        agent = await self._get_agent(agent_name)
        if agent:
            try:
                message = json.dumps({
                    "finops_event": True,
                    "event_type": event_type,
                    "agent": agent_name,
                    "timestamp": event["timestamp"],
                    "summary": _summarise(event_type, payload),
                })
                await agent.send_message(
                    room_id=self.room_id,
                    content=message,
                )
            except Exception as e:
                console.print(f"[yellow]Band send warning ({agent_name}): {e}[/yellow]")

        console.print(
            Panel(
                f"[bold]{agent_name}[/bold] → [cyan]{event_type}[/cyan]\n"
                + json.dumps(payload, indent=2),
                title=f"[green]Band Room: {self.room_id}[/green]",
                border_style="green",
            )
        )

    async def get_events(self, event_type: str) -> list[dict]:
        async with self._lock:
            return [e for e in self._local_events if e["event_type"] == event_type]

    async def get_all_events(self) -> list[dict]:
        async with self._lock:
            return list(self._local_events)

    async def wait_for(
        self,
        event_types: list[str],
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> dict[str, dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            results = {}
            for et in event_types:
                events = await self.get_events(et)
                if events:
                    results[et] = events[-1]["payload"]
            if len(results) == len(event_types):
                return results
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f"Timed out waiting for events: {event_types} in room {self.room_id}"
        )

    async def clear(self) -> None:
        async with self._lock:
            self._local_events.clear()


def _summarise(event_type: str, payload: dict) -> str:
    """Generate a human-readable one-line summary for the Band room message."""
    try:
        if event_type == "ChangeOrderApproved":
            co = payload["change_order"]
            return f"Change Order {co['co_id']} approved — ${co['delta_value']:,.0f} delta on {co['project_code']}"
        if event_type == "ActualsChecked":
            s = payload["status"]
            return f"{s['project_code']}: mainframe {'✓ absorbed' if s['actuals_absorbed_co'] else '✗ NOT updated'} — variance {s['mainframe_variance']:,.0f}"
        if event_type == "BudgetImpact":
            b = payload["impact"]
            return f"{b['project_code']}: TM1 budget {'✓ reflected' if b['budget_reflected_in_tm1'] else '✗ NOT updated'} — reforecast {'required' if b['reforecast_required'] else 'not needed'}"
        if event_type == "NarrativeReady":
            n = payload["narrative"]
            return f"{n['co_id']}: {n['summary'][:120]}..."
        if event_type == "EscalationRequested":
            r = payload["request"]
            return f"ESCALATION: {r['co_id']} — {r['variance_pct']:.1f}% variance — {r['recommended_action']}"
        if event_type == "WeeklyCostSummary":
            lw = payload["latest_week"]
            return f"{payload['project_code']}: week {lw['period']} — actual ${lw['actual_cost_this_week']:,.0f} committed ${lw['committed_cost_this_week']:,.0f}"
    except Exception:
        pass
    return event_type


_room: BandRoom | None = None


def get_room(room_id: str = "finops-recon-room") -> BandRoom:
    global _room
    if _room is None:
        _room = BandRoom(room_id)
    return _room