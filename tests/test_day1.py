"""
tests/test_day1.py — Day 1 smoke test
"""

import asyncio
import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def seed_to(db_path: str):
    """Seed data directly to a specific path (for testing)."""
    from datetime import datetime, timedelta
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS projects;
        DROP TABLE IF EXISTS change_orders;
        DROP TABLE IF EXISTS actuals;
        DROP TABLE IF EXISTS tm1_budgets;
        CREATE TABLE projects (project_code TEXT PRIMARY KEY, project_name TEXT,
            cost_centre TEXT, budget_baseline REAL, project_manager TEXT);
        CREATE TABLE change_orders (co_id TEXT PRIMARY KEY, project_code TEXT,
            cost_centre TEXT, delta_value REAL, approved_by TEXT, approved_at TEXT,
            description TEXT, propagated_to_mainframe INTEGER, propagated_to_tm1 INTEGER);
        CREATE TABLE actuals (project_code TEXT PRIMARY KEY, committed_cost REAL,
            actual_cost REAL, as_of_date TEXT);
        CREATE TABLE tm1_budgets (project_code TEXT PRIMARY KEY, tm1_budget REAL, last_updated TEXT);
    """)
    now = datetime.now().isoformat()
    c.execute("INSERT INTO projects VALUES (?,?,?,?,?)",
              ("PROJ-001", "Offshore Platform Alpha", "CC-CAPEX-03", 12400000.0, "Sarah Chen"))
    c.execute("INSERT INTO projects VALUES (?,?,?,?,?)",
              ("PROJ-002", "Pipeline Extension West", "CC-CAPEX-07", 8750000.0, "Marcus Webb"))
    c.execute("INSERT INTO change_orders VALUES (?,?,?,?,?,?,?,?,?)",
              ("CO-2024-047", "PROJ-001", "CC-CAPEX-03", 320000.0, "James", now, "Steel casing", 0, 0))
    c.execute("INSERT INTO change_orders VALUES (?,?,?,?,?,?,?,?,?)",
              ("CO-2024-051", "PROJ-002", "CC-CAPEX-07", 95000.0, "Linda", now, "Pipe reroute", 1, 0))
    c.execute("INSERT INTO actuals VALUES (?,?,?,?)",
              ("PROJ-001", 10850000.0, 9920000.0, "2024-06-01"))
    c.execute("INSERT INTO actuals VALUES (?,?,?,?)",
              ("PROJ-002", 8845000.0, 8210000.0, "2024-06-01"))
    c.execute("INSERT INTO tm1_budgets VALUES (?,?,?)",
              ("PROJ-001", 12400000.0, now))
    c.execute("INSERT INTO tm1_budgets VALUES (?,?,?)",
              ("PROJ-002", 8750000.0, now))
    conn.commit()
    conn.close()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    seed_to(db)
    return db


@pytest.fixture
def room():
    from core.room import BandRoom
    return BandRoom("test-room")


@pytest.mark.asyncio
async def test_change_order_watcher_posts_events(room, test_db):
    from agents.change_order_watcher import fetch_pending_change_orders, run as run_watcher
    import agents.change_order_watcher as w
    w.DB_PATH = test_db
    await run_watcher(room, single_shot=True)
    events = await room.get_events("ChangeOrderApproved")
    assert len(events) >= 2
    co_ids = {e["payload"]["change_order"]["co_id"] for e in events}
    assert "CO-2024-047" in co_ids
    assert "CO-2024-051" in co_ids


@pytest.mark.asyncio
async def test_mainframe_recon_posts_actuals(room, test_db):
    import agents.change_order_watcher as w
    import agents.mainframe_recon as m
    w.DB_PATH = test_db
    m.DB_PATH = test_db
    from agents.change_order_watcher import run as run_watcher
    from agents.mainframe_recon import run as run_mainframe
    await run_watcher(room, single_shot=True)
    task = asyncio.create_task(run_mainframe(room))
    await asyncio.sleep(2)
    task.cancel()
    events = await room.get_events("ActualsChecked")
    assert len(events) >= 2


@pytest.mark.asyncio
async def test_budget_impact_posts_events(room, test_db):
    import agents.change_order_watcher as w
    import agents.budget_impact as b
    w.DB_PATH = test_db
    b.DB_PATH = test_db
    from agents.change_order_watcher import run as run_watcher
    from agents.budget_impact import run as run_budget
    await run_watcher(room, single_shot=True)
    task = asyncio.create_task(run_budget(room))
    await asyncio.sleep(2)
    task.cancel()
    events = await room.get_events("BudgetImpact")
    assert len(events) >= 2


@pytest.mark.asyncio
async def test_full_pipeline_produces_escalations(room, test_db):
    import agents.change_order_watcher as w
    import agents.mainframe_recon as m
    import agents.budget_impact as b
    w.DB_PATH = test_db
    m.DB_PATH = test_db
    b.DB_PATH = test_db
    from agents.change_order_watcher import run as run_watcher
    from agents.mainframe_recon import run as run_mainframe
    from agents.budget_impact import run as run_budget
    from agents.narrative_agent import run as run_narrative
    from agents.escalation_agent import run as run_escalation
    await run_watcher(room, single_shot=True)
    tasks = [
        asyncio.create_task(run_mainframe(room)),
        asyncio.create_task(run_budget(room)),
        asyncio.create_task(run_narrative(room)),
        asyncio.create_task(run_escalation(room)),
    ]
    await asyncio.sleep(6)
    for t in tasks:
        t.cancel()
    escalations = await room.get_events("EscalationRequested")
    assert len(escalations) >= 1
    co_ids = {e["payload"]["request"]["co_id"] for e in escalations}
    assert "CO-2024-047" in co_ids
