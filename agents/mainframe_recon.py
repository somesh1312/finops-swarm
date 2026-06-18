"""
Agent 2: mainframe_recon

Responsibility: Listen for ChangeOrderApproved events in the Band room.
For each one, query the mainframe ERP (SQLite stub) to check whether
actuals and committed costs already reflect the change order.
Post ActualsChecked event with the full reconciliation status.

In production: replace SQLite query with your mainframe connector
(JDBC, MQ, flat-file extract, or REST façade over the legacy system).
"""

import asyncio
import sqlite3
import os
from dotenv import load_dotenv

from core.room import get_room
from core.models import (
    ChangeOrderApprovedEvent,
    ActualsStatus,
    ActualsCheckedEvent,
)

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/finops.db")
VARIANCE_THRESHOLD_PCT = float(os.getenv("VARIANCE_THRESHOLD_PCT", "2.0"))
AGENT_NAME = "mainframe_recon"


def query_actuals(project_code: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM actuals WHERE project_code = ?", (project_code,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def query_project(project_code: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE project_code = ?", (project_code,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def query_co_mainframe_status(co_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT propagated_to_mainframe FROM change_orders WHERE co_id = ?", (co_id,)
    )
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False


async def process_change_order(room, co_payload: dict):
    event = ChangeOrderApprovedEvent(**co_payload)
    co = event.change_order
    project_code = co.project_code

    print(f"[{AGENT_NAME}] Checking mainframe for {co.co_id} / {project_code}...")

    actuals = query_actuals(project_code)
    project = query_project(project_code)

    if not actuals or not project:
        print(f"[{AGENT_NAME}] WARNING: No actuals found for {project_code}")
        return

    budget_baseline = project["budget_baseline"]
    committed_cost = actuals["committed_cost"]
    actual_cost = actuals["actual_cost"]
    actuals_absorbed = query_co_mainframe_status(co.co_id)

    mainframe_variance = committed_cost - actual_cost
    expected_committed = budget_baseline + (co.delta_value if actuals_absorbed else 0)
    variance_pct = abs(mainframe_variance / budget_baseline) * 100
    within_tolerance = variance_pct <= VARIANCE_THRESHOLD_PCT

    status = ActualsStatus(
        project_code=project_code,
        co_id=co.co_id,
        budget_baseline=budget_baseline,
        committed_cost=committed_cost,
        actual_cost=actual_cost,
        actuals_absorbed_co=actuals_absorbed,
        mainframe_variance=mainframe_variance,
        within_tolerance=within_tolerance,
    )

    result = ActualsCheckedEvent(status=status)
    await room.post_event(
        event_type=result.event_type,
        payload=result.model_dump(mode="json"),
        agent_name=AGENT_NAME,
    )


async def run(room=None):
    if room is None:
        room = get_room()

    print(f"[{AGENT_NAME}] Starting — watching Band room for ChangeOrderApproved...")

    processed: set[str] = set()

    while True:
        events = await room.get_events("ChangeOrderApproved")

        for event in events:
            co_id = event["payload"]["change_order"]["co_id"]
            if co_id in processed:
                continue
            await process_change_order(room, event["payload"])
            processed.add(co_id)

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
