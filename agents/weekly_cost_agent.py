"""
Agent 6: weekly_cost_agent

Responsibility: Answer the question nobody can currently answer quickly:

  "For the week starting Monday June 10 and ending Sunday June 16,
   what was the actual cost and committed cost for this project?"

The mainframe ERP only stores cumulative running totals — not period
figures. To get a weekly number you must subtract the prior week's
cumulative from this week's cumulative. Without stored snapshots this
requires manual analyst work (30–60 min per project per week).

This agent:
  1. Reads periodic snapshots stored from mainframe batch exports
  2. Computes the week-on-week delta automatically
  3. Posts a WeeklyCostSummary event to the Band room
  4. Flags unusual weeks where cost velocity spiked unexpectedly

This is Agent 6 — it runs independently of the change order pipeline.
It fires on a schedule (weekly) or on demand via the API.

--- WHY THIS MATTERS ---
A portfolio of 10 projects = 10 × 30–60 min = up to 10 hours of analyst
time every single week just to answer one question. This agent answers
it in under a second.

In production: the snapshot table is populated by a scheduled job that
reads the mainframe batch export every Friday evening and writes a row.
No mainframe API needed — just the same flat file export that already exists.
"""

import asyncio
import sqlite3
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from core.room import get_room

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/finops.db")
AGENT_NAME = "weekly_cost_agent"
SPIKE_THRESHOLD_PCT = float(os.getenv("SPIKE_THRESHOLD_PCT", "15.0"))


def get_all_project_codes() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT project_code FROM projects")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_snapshots_for_project(project_code: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM weekly_snapshots
        WHERE project_code = ?
        ORDER BY week_start ASC
    """, (project_code,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def compute_weekly_deltas(snapshots: list[dict]) -> list[dict]:
    """
    Convert cumulative snapshot totals into period-bounded weekly figures.

    The mainframe stores running totals. Week N's actual spend =
    snapshot[N].actual_cost - snapshot[N-1].actual_cost

    First week has no prior snapshot so we use its value as-is
    (represents spend from project start to end of that week).
    """
    results = []
    for i, snap in enumerate(snapshots):
        if i == 0:
            weekly_actual = snap["actual_cost"]
            weekly_committed = snap["committed_cost"]
            prior_actual = 0
            prior_committed = 0
        else:
            prior = snapshots[i - 1]
            prior_actual = prior["actual_cost"]
            prior_committed = prior["committed_cost"]
            weekly_actual = snap["actual_cost"] - prior_actual
            weekly_committed = snap["committed_cost"] - prior_committed

        # Detect cost velocity spike vs prior week
        if i >= 2:
            prev_weekly_actual = snapshots[i-1]["actual_cost"] - snapshots[i-2]["actual_cost"]
            if prev_weekly_actual > 0:
                spike_pct = ((weekly_actual - prev_weekly_actual) / prev_weekly_actual) * 100
            else:
                spike_pct = 0.0
        else:
            spike_pct = 0.0

        results.append({
            "project_code": snap["project_code"],
            "week_start": snap["week_start"],
            "week_end": snap["week_end"],
            "weekly_actual_cost": round(weekly_actual, 2),
            "weekly_committed_cost": round(weekly_committed, 2),
            "cumulative_actual": snap["actual_cost"],
            "cumulative_committed": snap["committed_cost"],
            "week_on_week_actual_change_pct": round(spike_pct, 2),
            "spike_detected": abs(spike_pct) > SPIKE_THRESHOLD_PCT,
        })
    return results


async def run(room=None, project_code: str = None):
    """
    Compute and post weekly cost summaries for all projects
    (or a specific project if project_code is supplied).
    """
    if room is None:
        room = get_room()

    project_codes = [project_code] if project_code else get_all_project_codes()

    print(f"[{AGENT_NAME}] Computing weekly cost deltas for {len(project_codes)} project(s)...")

    for code in project_codes:
        snapshots = get_snapshots_for_project(code)
        if len(snapshots) < 2:
            print(f"[{AGENT_NAME}] {code}: not enough snapshots for delta calculation (need ≥2)")
            continue

        weekly = compute_weekly_deltas(snapshots)
        latest = weekly[-1]

        # Flag spikes for escalation
        spikes = [w for w in weekly if w["spike_detected"]]

        payload = {
            "project_code": code,
            "weeks_analysed": len(weekly),
            "latest_week": {
                "period": f"{latest['week_start']} to {latest['week_end']}",
                "actual_cost_this_week": latest["weekly_actual_cost"],
                "committed_cost_this_week": latest["weekly_committed_cost"],
                "wow_change_pct": latest["week_on_week_actual_change_pct"],
                "spike_detected": latest["spike_detected"],
            },
            "all_weeks": weekly,
            "spike_weeks": spikes,
            "requires_attention": len(spikes) > 0,
        }

        await room.post_event(
            event_type="WeeklyCostSummary",
            payload=payload,
            agent_name=AGENT_NAME,
        )

        if spikes:
            print(
                f"[{AGENT_NAME}] {code}: ⚠ spike detected in "
                f"{len(spikes)} week(s) — flagging for escalation"
            )

    print(f"[{AGENT_NAME}] Weekly cost analysis complete.")


if __name__ == "__main__":
    asyncio.run(run())
