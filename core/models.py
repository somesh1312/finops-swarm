"""
Shared data models. Every agent posts and reads these exact shapes.
Pydantic validates them so no agent can accidentally post a malformed event.
"""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class ChangeOrder(BaseModel):
    co_id: str                          # e.g. "CO-2024-047"
    project_code: str                   # e.g. "PROJ-001"
    cost_centre: str                    # e.g. "CC-CAPEX-03"
    delta_value: float                  # positive = cost increase
    approved_by: str
    approved_at: datetime
    description: str


class ChangeOrderApprovedEvent(BaseModel):
    """Posted by: change_order_watcher agent"""
    event_type: Literal["ChangeOrderApproved"] = "ChangeOrderApproved"
    change_order: ChangeOrder


class ActualsStatus(BaseModel):
    project_code: str
    co_id: str
    budget_baseline: float
    committed_cost: float
    actual_cost: float
    actuals_absorbed_co: bool           # True if mainframe already reflects CO
    mainframe_variance: float           # committed_cost - actual_cost
    within_tolerance: bool


class ActualsCheckedEvent(BaseModel):
    """Posted by: mainframe_recon agent"""
    event_type: Literal["ActualsChecked"] = "ActualsChecked"
    status: ActualsStatus


class BudgetImpact(BaseModel):
    project_code: str
    co_id: str
    tm1_budget_before: float
    tm1_budget_after: float
    budget_delta: float
    budget_reflected_in_tm1: bool       # True if TM1 already shows the CO
    affected_cost_centres: list[str]
    reforecast_required: bool


class BudgetImpactEvent(BaseModel):
    """Posted by: budget_impact agent"""
    event_type: Literal["BudgetImpact"] = "BudgetImpact"
    impact: BudgetImpact


class ReconciliationNarrative(BaseModel):
    project_code: str
    co_id: str
    summary: str                        # One CFO-ready paragraph
    variance_pct: float
    requires_escalation: bool
    recommended_action: str


class NarrativeReadyEvent(BaseModel):
    """Posted by: narrative agent"""
    event_type: Literal["NarrativeReady"] = "NarrativeReady"
    narrative: ReconciliationNarrative


class EscalationRequest(BaseModel):
    project_code: str
    co_id: str
    narrative_summary: str
    variance_amount: float
    variance_pct: float
    budget_before: float
    budget_after: float
    actuals_absorbed: bool
    tm1_reflected: bool
    recommended_action: str


class EscalationRequestedEvent(BaseModel):
    """Posted by: escalation agent → triggers human review UI"""
    event_type: Literal["EscalationRequested"] = "EscalationRequested"
    request: EscalationRequest
