# FinOps Swarm

> Five Band-coordinated AI agents that autonomously reconcile enterprise financial data —
> budget, committed costs, and actuals — tracing every discrepancy to its root change order.
> Inference runs locally on AMD hardware. Financial data never leaves the network.

## Quick start (Day 1)

```bash
# 1. Clone and set up environment
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Seed mock financial data (3 projects, 3 change orders, 2 deliberate discrepancies)
python -m data.seed_data

# 3. Pull the local LLM (one-time, ~5GB)
ollama pull llama3.1:8b

# 4. Run the full swarm
python main.py

# 5. (Optional) Run tests
pytest tests/test_day1.py -v
```

## The problem this solves

When a change order is approved, it should update:
1. The mainframe ERP (actuals + committed costs)
2. The TM1 budget model (reforecast)

In reality, these updates are manual and often missed. By month-end close
the CFO sees Budget ≠ Committed ≠ Actual with no explanation.

**FinOps Swarm** replaces the manual trace with 5 coordinated agents.

## Agent pipeline

```
Change orders DB
       │
       ▼
[1] change_order_watcher  ──► Band room: ChangeOrderApproved
       │
       ├──► [2] mainframe_recon  ──► Band room: ActualsChecked
       │
       └──► [3] budget_impact    ──► Band room: BudgetImpact
                                            │
                     (both must arrive) ◄───┘
                                            │
                                            ▼
                              [4] narrative_agent (AMD/Ollama)
                                            │
                                            ▼
                                  Band room: NarrativeReady
                                            │
                              (if escalation needed)
                                            │
                                            ▼
                              [5] escalation_agent
                                            │
                                            ▼
                               CFO dashboard — one decision card
```

## Mock data discrepancies (demo scenario)

| CO | Project | Delta | Mainframe | TM1 | Result |
|---|---|---|---|---|---|
| CO-2024-047 | PROJ-001 | $320,000 | ❌ NOT absorbed | ❌ NOT reflected | **Escalated** |
| CO-2024-051 | PROJ-002 | $95,000 | ✅ Absorbed | ❌ NOT reflected | **Escalated** |
| CO-2024-053 | PROJ-003 | $48,000 | ✅ Absorbed | ✅ Reflected | Clean |

## AMD deployment

For local inference on AMD GPU, uncomment the ROCm device lines in
`docker-compose.yml` and ensure ROCm drivers are installed.

Ollama supports AMD GPUs via ROCm — same API, GPU-accelerated inference.
See: https://ollama.com/blog/amd-preview

## Swapping to real Band SDK (hackathon Day 1)

When you receive the Band SDK access credentials:

1. `pip install band-sdk` (exact package name TBC from hackathon docs)
2. In `core/room.py`, find the line marked `# BAND_SWAP`
3. Replace the `BandRoom` class with the real import
4. Add `BAND_API_KEY` and `BAND_ROOM_ID` to your `.env`

Everything else stays identical — the event contracts, agent logic,
and orchestration are Band-SDK-shaped from Day 1.

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | Band SDK (stub → real on Day 1) |
| Agent logic | Python 3.11 + asyncio |
| Local LLM inference | Ollama + Llama 3.1 8B |
| AMD GPU inference | ROCm (docker-compose flag) |
| Mock data store | SQLite |
| API | FastAPI |
| Containerisation | Docker Compose |
