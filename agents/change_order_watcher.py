"""
Agent 1: change_order_watcher

Responsibility: Poll the change orders table, detect newly approved COs
that have NOT yet been propagated to mainframe or TM1, and post a
ChangeOrderApproved event to the Band room.

In production: replace the SQLite poll with a webhook from your change
order system or a mainframe MQ listener.
"""

import asyncio
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv

from core.room import get_room
from core.models import ChangeOrder, ChangeOrderApprovedEvent

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/finops.db")
AGENT_NAME = "change_order_watcher"


def fetch_pending_change_orders() -> list[dict]:
    """Fetch COs not yet fully propagated to both systems."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM change_orders
        WHERE propagated_to_mainframe = 0 OR propagated_to_tm1 = 0
        ORDER BY approved_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


async def run(room=None, single_shot: bool = False):
    """
    Main agent loop.
    single_shot=True runs once and returns (useful for testing + demo).
    """
    if room is None:
        room = get_room()

    print(f"[{AGENT_NAME}] Starting — polling for unpropagated change orders...")

    seen_co_ids: set[str] = set()

    while True:
        pending = fetch_pending_change_orders()

        for row in pending:
            co_id = row["co_id"]
            if co_id in seen_co_ids:
                continue

            co = ChangeOrder(
                co_id=co_id,
                project_code=row["project_code"],
                cost_centre=row["cost_centre"],
                delta_value=row["delta_value"],
                approved_by=row["approved_by"],
                approved_at=datetime.fromisoformat(row["approved_at"]),
                description=row["description"],
            )

            event = ChangeOrderApprovedEvent(change_order=co)
            await room.post_event(
                event_type=event.event_type,
                payload=event.model_dump(mode="json"),
                agent_name=AGENT_NAME,
            )
            seen_co_ids.add(co_id)

        if single_shot or not pending:
            break

        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
