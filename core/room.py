"""
core/room.py — Band shared room (REAL SDK implementation)
Each agent posts to Band using its own API key and mentions a different agent.
"""

import asyncio
import json
import time
import os
from typing import Any
from rich.console import Console
from rich.panel import Panel

console = Console()

try:
    from thenvoi.config import load_agent_config
    BAND_SDK_AVAILABLE = True
except ImportError:
    try:
        from band.config import load_agent_config
        BAND_SDK_AVAILABLE = True
    except ImportError:
        BAND_SDK_AVAILABLE = False

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")

AGENT_CONFIG_MAP = {
    "change_order_watcher": "co_watcher",
    "mainframe_recon":      "mainframe_recon",
    "budget_impact":        "budget_impact",
    "narrative_agent":      "narrative_agent",
    "escalation_agent":     "escalation_agent",
    "weekly_cost_agent":    "weekly_cost",
}

# Each agent mentions a DIFFERENT agent (never itself)
AGENT_MENTION_MAP = {
    "weekly_cost_agent":    "36c0ee46-a8c6-4340-83eb-9a05f0ecb698",  # → mainframe_recon
    "change_order_watcher": "31f5de7a-9eed-44e5-95d5-113c9b985a4a",  # → budget_impact
    "mainframe_recon":      "bf2351c1-5913-476f-96a2-aad8c2e974a7",  # → narrative_agent
    "budget_impact":        "7cd49335-3b41-4400-9d06-1ea00524fea5",  # → co_watcher
    "narrative_agent":      "cb58d3fd-2035-47c3-8f24-4c49a97826dc",  # → escalation_agent
    "escalation_agent":     "5f658d85-4eb9-4199-a9ed-854a0511af13",  # → weekly_cost
}


class BandRoom:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self._local_events: list[dict] = []
        self._lock = asyncio.Lock()
        self._rest_clients: dict[str, Any] = {}

    async def _get_rest_client(self, agent_name: str):
        if not BAND_SDK_AVAILABLE:
            return None
        if agent_name in self._rest_clients:
            return self._rest_clients[agent_name]
        try:
            config_key = AGENT_CONFIG_MAP.get(agent_name, agent_name)
            agent_id, api_key = load_agent_config(
                config_key, config_path=CONFIG_PATH
            )
            self._rest_clients[agent_name] = {
                "agent_id": agent_id,
                "api_key": api_key,
            }
            console.print(f"[green]✓ {agent_name} credentials loaded[/green]")
            return self._rest_clients[agent_name]
        except Exception as e:
            console.print(f"[yellow]Band config warning ({agent_name}): {e}[/yellow]")
            return None

    async def _post_to_band(self, agent_name: str, message: str):
        if not BAND_SDK_AVAILABLE:
            return
        client = await self._get_rest_client(agent_name)
        if not client:
            return
        try:
            import httpx
            chat_id = os.getenv("BAND_CHAT_ID", self.room_id)
            mention_id = AGENT_MENTION_MAP.get(
                agent_name, "36c0ee46-a8c6-4340-83eb-9a05f0ecb698"
            )
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(
                    f"https://app.band.ai/api/v1/agent/chats/{chat_id}/messages",
                    headers={
                        "X-API-Key": client["api_key"],
                        "Content-Type": "application/json",
                    },
                    json={"message": {
                        "content": message,
                        "mentions": [{"id": mention_id}]
                    }},
                )
                if resp.status_code == 201:
                    console.print(f"[green]✓ {agent_name} posted to Band room[/green]")
                else:
                    console.print(
                        f"[yellow]Band API {resp.status_code} ({agent_name}): "
                        f"{resp.text[:100]}[/yellow]"
                    )
        except Exception as e:
            console.print(f"[dim]Band REST warning ({agent_name}): {e}[/dim]")

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

        message = (
            f"**[{event_type}]** {_summarise(event_type, payload)}\n"
            f"```json\n{json.dumps(payload, indent=2)[:500]}\n```"
        )
        await self._post_to_band(agent_name, message)

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
    try:
        if event_type == "ChangeOrderApproved":
            co = payload["change_order"]
            return f"{co['co_id']} — ${co['delta_value']:,.0f} on {co['project_code']}"
        if event_type == "ActualsChecked":
            s = payload["status"]
            return f"{s['project_code']}: mainframe {'✓ absorbed' if s['actuals_absorbed_co'] else '✗ NOT updated'}"
        if event_type == "BudgetImpact":
            b = payload["impact"]
            return f"{b['project_code']}: TM1 {'✓ reflected' if b['budget_reflected_in_tm1'] else '✗ NOT updated'}"
        if event_type == "NarrativeReady":
            n = payload["narrative"]
            return f"{n['co_id']}: variance {n['variance_pct']}%"
        if event_type == "EscalationRequested":
            r = payload["request"]
            return f"ESCALATION: {r['co_id']} — {r['variance_pct']:.1f}% variance"
        if event_type == "WeeklyCostSummary":
            lw = payload["latest_week"]
            return f"{payload['project_code']}: actual ${lw['actual_cost_this_week']:,.0f} this week"
    except Exception:
        pass
    return event_type


_room: BandRoom | None = None


def get_room(room_id: str = "finops-recon-room") -> BandRoom:
    global _room
    if _room is None:
        _room = BandRoom(room_id)
    return _room