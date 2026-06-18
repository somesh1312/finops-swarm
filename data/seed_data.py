"""
seed_data.py — generates realistic mock financial data for the demo.

Run this once on Day 1:
    python -m data.seed_data

Creates three tables in data/finops.db:
  - projects          (budget baseline, project metadata)
  - change_orders     (approved COs waiting to propagate)
  - actuals           (mainframe ERP ledger — deliberately NOT yet updated)
  - tm1_budgets       (TM1 planning model — also NOT yet updated)

Two deliberate discrepancies are injected so the agents have something to find.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "finops.db")


PROJECTS = [
    {
        "project_code": "PROJ-001",
        "project_name": "Offshore Platform Alpha — Phase 2",
        "cost_centre": "CC-CAPEX-03",
        "budget_baseline": 12_400_000.00,
        "project_manager": "Sarah Chen",
    },
    {
        "project_code": "PROJ-002",
        "project_name": "Onshore Pipeline Extension — West",
        "cost_centre": "CC-CAPEX-07",
        "budget_baseline": 8_750_000.00,
        "project_manager": "Marcus Webb",
    },
    {
        "project_code": "PROJ-003",
        "project_name": "Refinery Upgrade — Unit 4",
        "cost_centre": "CC-OPEX-12",
        "budget_baseline": 5_200_000.00,
        "project_manager": "Priya Nair",
    },
]

CHANGE_ORDERS = [
    {
        "co_id": "CO-2024-047",
        "project_code": "PROJ-001",
        "cost_centre": "CC-CAPEX-03",
        "delta_value": 320_000.00,
        "approved_by": "James Okafor",
        "approved_at": (datetime.now() - timedelta(days=3)).isoformat(),
        "description": "Additional steel casing required due to revised seabed survey findings.",
        "propagated_to_mainframe": 0,  # NOT YET in ERP — deliberate discrepancy 1
        "propagated_to_tm1": 0,        # NOT YET in TM1 — deliberate discrepancy 1
    },
    {
        "co_id": "CO-2024-051",
        "project_code": "PROJ-002",
        "cost_centre": "CC-CAPEX-07",
        "delta_value": 95_000.00,
        "approved_by": "Linda Frost",
        "approved_at": (datetime.now() - timedelta(days=8)).isoformat(),
        "description": "Pipe reroute around protected wetland corridor.",
        "propagated_to_mainframe": 1,  # Already in ERP — clean
        "propagated_to_tm1": 0,        # NOT YET in TM1 — deliberate discrepancy 2
    },
    {
        "co_id": "CO-2024-053",
        "project_code": "PROJ-003",
        "cost_centre": "CC-OPEX-12",
        "delta_value": 48_000.00,
        "approved_by": "James Okafor",
        "approved_at": (datetime.now() - timedelta(days=1)).isoformat(),
        "description": "Emergency shutdown valve replacement — unplanned maintenance.",
        "propagated_to_mainframe": 1,  # Both already updated — clean
        "propagated_to_tm1": 1,
    },
]

# Mainframe ERP actuals — reflect only propagated COs
ACTUALS = [
    {
        "project_code": "PROJ-001",
        "committed_cost": 10_850_000.00,   # Budget was 12.4M, CO-047 NOT absorbed
        "actual_cost": 9_920_000.00,
        "as_of_date": datetime.now().date().isoformat(),
    },
    {
        "project_code": "PROJ-002",
        "committed_cost": 8_845_000.00,    # Includes CO-051 delta (absorbed)
        "actual_cost": 8_210_000.00,
        "as_of_date": datetime.now().date().isoformat(),
    },
    {
        "project_code": "PROJ-003",
        "committed_cost": 5_248_000.00,    # Includes CO-053 delta (absorbed)
        "actual_cost": 4_890_000.00,
        "as_of_date": datetime.now().date().isoformat(),
    },
]

# TM1 budget model — reflects only fully propagated COs
TM1_BUDGETS = [
    {
        "project_code": "PROJ-001",
        "tm1_budget": 12_400_000.00,    # Still at baseline — CO-047 not in TM1
        "last_updated": (datetime.now() - timedelta(days=10)).isoformat(),
    },
    {
        "project_code": "PROJ-002",
        "tm1_budget": 8_750_000.00,     # Still at baseline — CO-051 not in TM1
        "last_updated": (datetime.now() - timedelta(days=10)).isoformat(),
    },
    {
        "project_code": "PROJ-003",
        "tm1_budget": 5_248_000.00,     # Updated — CO-053 reflected
        "last_updated": (datetime.now() - timedelta(days=1)).isoformat(),
    },
]



WEEKLY_SNAPSHOTS = [
    {"project_code": "PROJ-001", "week_start": "2024-05-27", "week_end": "2024-06-02", "committed_cost": 10_200_000.00, "actual_cost": 9_450_000.00},
    {"project_code": "PROJ-001", "week_start": "2024-06-03", "week_end": "2024-06-09", "committed_cost": 10_530_000.00, "actual_cost": 9_710_000.00},
    {"project_code": "PROJ-001", "week_start": "2024-06-10", "week_end": "2024-06-16", "committed_cost": 10_850_000.00, "actual_cost": 9_920_000.00},
    {"project_code": "PROJ-002", "week_start": "2024-05-27", "week_end": "2024-06-02", "committed_cost": 8_400_000.00, "actual_cost": 7_890_000.00},
    {"project_code": "PROJ-002", "week_start": "2024-06-03", "week_end": "2024-06-09", "committed_cost": 8_620_000.00, "actual_cost": 8_050_000.00},
    {"project_code": "PROJ-002", "week_start": "2024-06-10", "week_end": "2024-06-16", "committed_cost": 8_845_000.00, "actual_cost": 8_210_000.00},
]


def seed_snapshots(conn):
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS weekly_snapshots")
    c.execute("""
        CREATE TABLE weekly_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_code TEXT,
            week_start TEXT,
            week_end TEXT,
            committed_cost REAL,
            actual_cost REAL
        )
    """)
    c.executemany(
        "INSERT INTO weekly_snapshots (project_code, week_start, week_end, committed_cost, actual_cost) VALUES (?,?,?,?,?)",
        [(s["project_code"], s["week_start"], s["week_end"], s["committed_cost"], s["actual_cost"]) for s in WEEKLY_SNAPSHOTS]
    )
    conn.commit()
    print(f"   {len(WEEKLY_SNAPSHOTS)} weekly snapshots seeded")


def seed():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS projects")
    c.execute("DROP TABLE IF EXISTS change_orders")
    c.execute("DROP TABLE IF EXISTS actuals")
    c.execute("DROP TABLE IF EXISTS tm1_budgets")

    c.execute("""
        CREATE TABLE projects (
            project_code TEXT PRIMARY KEY,
            project_name TEXT,
            cost_centre TEXT,
            budget_baseline REAL,
            project_manager TEXT
        )
    """)

    c.execute("""
        CREATE TABLE change_orders (
            co_id TEXT PRIMARY KEY,
            project_code TEXT,
            cost_centre TEXT,
            delta_value REAL,
            approved_by TEXT,
            approved_at TEXT,
            description TEXT,
            propagated_to_mainframe INTEGER,
            propagated_to_tm1 INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE actuals (
            project_code TEXT PRIMARY KEY,
            committed_cost REAL,
            actual_cost REAL,
            as_of_date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE tm1_budgets (
            project_code TEXT PRIMARY KEY,
            tm1_budget REAL,
            last_updated TEXT
        )
    """)

    c.executemany("INSERT INTO projects VALUES (?,?,?,?,?)",
                  [tuple(p.values()) for p in PROJECTS])
    c.executemany("INSERT INTO change_orders VALUES (?,?,?,?,?,?,?,?,?)",
                  [tuple(co.values()) for co in CHANGE_ORDERS])
    c.executemany("INSERT INTO actuals VALUES (?,?,?,?)",
                  [tuple(a.values()) for a in ACTUALS])
    c.executemany("INSERT INTO tm1_budgets VALUES (?,?,?)",
                  [tuple(t.values()) for t in TM1_BUDGETS])
    seed_snapshots(conn)
    conn.commit()
    conn.close()
    print(f"✅ Mock data seeded to {DB_PATH}")
    print(f"   {len(PROJECTS)} projects | {len(CHANGE_ORDERS)} change orders")
    print("   Discrepancy 1: CO-2024-047 not in mainframe OR TM1 (PROJ-001, $320k)")
    print("   Discrepancy 2: CO-2024-051 in mainframe but NOT TM1 (PROJ-002, $95k)")
    print("   Clean:         CO-2024-053 fully propagated (PROJ-003, $48k)")


if __name__ == "__main__":
    seed()
