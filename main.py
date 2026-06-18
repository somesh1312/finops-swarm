"""
main.py — FinOps Swarm orchestrator

Starts all 5 agents as concurrent asyncio tasks sharing one Band room.
This is your Day 1 smoke test. Run:

    python main.py

You should see the Band room filling up in sequence:
  1. ChangeOrderApproved (×2 discrepancies)
  2. ActualsChecked + BudgetImpact (in parallel, per CO)
  3. NarrativeReady (after both arrive)
  4. EscalationRequested (only for COs that need human review)
"""

import asyncio
from rich.console import Console
from rich.rule import Rule

from core.room import get_room
from data.seed_data import seed
from agents.change_order_watcher import run as run_watcher
from agents.mainframe_recon import run as run_mainframe
from agents.budget_impact import run as run_budget
from agents.narrative_agent import run as run_narrative
from agents.escalation_agent import run as run_escalation
from agents.weekly_cost_agent import run as run_weekly

console = Console()


async def main():
    console.print(Rule("[bold green]FinOps Swarm — Starting up[/bold green]"))

    # Seed the mock DB fresh every run so demo is reproducible
    console.print("[dim]Seeding mock financial data...[/dim]")
    seed()

    room = get_room("finops-recon-room")

    console.print(Rule("[cyan]All 5 agents launching[/cyan]"))

    # Run all agents concurrently. Each one is an infinite loop
    # except the watcher which completes after posting all pending COs.
    # Also run weekly cost analysis upfront
    await run_weekly(room)

    await asyncio.gather(
        run_watcher(room, single_shot=True),   # posts COs then exits
        run_mainframe(room),                    # parallel listeners
        run_budget(room),
        run_narrative(room),
        run_escalation(room),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down FinOps Swarm[/yellow]")
