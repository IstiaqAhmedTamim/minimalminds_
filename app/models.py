from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DirectiveType(str, Enum):
    """Directive categories used by the GridWise optimizer."""

    solar_reduction = "solar_reduction"
    minimum_battery_reserve = "minimum_battery_reserve"
    no_charge_window = "no_charge_window"
    no_discharge_window = "no_discharge_window"
    max_grid_window = "max_grid_window"
    no_op = "no_op"


class BatteryAction(str, Enum):
    """Allowed battery actions for each hour."""

    charge = "charge"
    discharge = "discharge"
    idle = "idle"


class Hour(BaseModel):
    """One hourly demand and tariff sample in the optimization horizon."""

    hour: int = Field(ge=0, le=23, description="Hour index from 0 to 23.")
    demand_kwh: float = Field(ge=0, description="Demand in kWh for the hour.")
    solar_kwh: float = Field(ge=0, description="Solar generation in kWh for the hour.")
    tariff_bdt_per_kwh: float = Field(
        ge=0,
        description="Electricity tariff in BDT per kWh for the hour.",
    )


class Battery(BaseModel):
    """Battery operating constraints used by the optimizer."""

    capacity_kwh: float = Field(gt=0, description="Maximum usable battery capacity.")
    initial_energy_kwh: float = Field(ge=0, description="Starting stored energy.")
    minimum_energy_kwh: float = Field(ge=0, description="Minimum allowed stored energy.")
    max_charge_kwh_per_hour: float = Field(gt=0, description="Maximum charge rate per hour.")
    max_discharge_kwh_per_hour: float = Field(
        gt=0,
        description="Maximum discharge rate per hour.",
    )


class OptimizeRequest(BaseModel):
    """Optimization input built from the GridWise specification."""

    scenario_id: str = Field(min_length=1, description="Scenario identifier.")
    operator_notes: list[str] = Field(
        min_length=1,
        max_length=3,
        description="One to three operator notes.",
    )
    hours: list[Hour] = Field(description="A complete 24-hour planning horizon.")
    battery: Battery = Field(description="Battery parameters for the scenario.")

    @model_validator(mode="after")
    def validate_grid_horizon(self) -> "OptimizeRequest":
        if len(self.hours) != 24:
            raise ValueError("hours must contain exactly 24 entries")

        hour_values = [hour.hour for hour in self.hours]
        if sorted(hour_values) != list(range(24)):
            raise ValueError("hour values must include every integer from 0 to 23 exactly once")

        normalized_notes = [note.strip() for note in self.operator_notes if note.strip()]
        if not 1 <= len(normalized_notes) <= 3:
            raise ValueError("operator_notes must contain between 1 and 3 non-empty notes")

        self.operator_notes = normalized_notes
        return self


class DirectiveInterpretation(BaseModel):
    """Interpretation of one operator note returned by the LLM."""

    note_index: int = Field(ge=0, description="Zero-based operator note index.")
    applies: bool = Field(description="Whether the note changes the plan.")
    directive_type: DirectiveType = Field(description="Directive selected for the note.")
    structured_adjustment: str = Field(
        description="Structured adjustment summary returned by the LLM.",
    )
    explanation: str = Field(description="Short explanation for the interpretation.")


class HourlyPlan(BaseModel):
    """Per-hour optimization output."""

    hour: int = Field(ge=0, le=23, description="Hour index from 0 to 23.")
    directive: DirectiveType = Field(description="Directive applied at this hour.")
    battery_action: BatteryAction = Field(description="Battery action for the hour.")
    grid_kwh: float = Field(ge=0, description="Energy imported from the grid.")
    battery_kwh: float = Field(ge=0, description="Battery energy moved during the hour.")
    solar_kwh: float = Field(ge=0, description="Solar generation used in the plan.")
    demand_kwh: float = Field(ge=0, description="Demand served in the hour.")


class AppliedHour(BaseModel):
    """Scenario hour after deterministic directive application."""

    hour: int = Field(ge=0, le=23, description="Hour index from 0 to 23.")
    demand_kwh: float = Field(ge=0, description="Original demand in kWh.")
    tariff_bdt_per_kwh: float = Field(
        ge=0,
        description="Original tariff in BDT per kWh.",
    )
    original_solar_kwh: float = Field(ge=0, description="Original solar generation in kWh.")
    effective_solar_kwh: float = Field(ge=0, description="Solar after directive application.")
    minimum_battery_reserve_kwh: float = Field(
        ge=0,
        description="Minimum battery reserve after directive application.",
    )
    charge_allowed: bool = Field(default=True, description="Whether charging is allowed.")
    discharge_allowed: bool = Field(default=True, description="Whether discharging is allowed.")
    max_grid_kwh: float | None = Field(
        default=None,
        ge=0,
        description="Maximum grid usage for the hour when constrained.",
    )


class AppliedScenario(BaseModel):
    """Scenario after deterministic directive application."""

    scenario_id: str = Field(description="Scenario identifier.")
    battery: Battery = Field(description="Original battery parameters.")
    hours: list[AppliedHour] = Field(description="Transformed hourly scenario.")
    applied_directives: list[dict] = Field(
        default_factory=list,
        description="Validated directives used to transform the scenario.",
    )


class OptimizeResponse(BaseModel):
    """Top-level response for the GridWise optimization engine."""

    scenario_id: str = Field(description="Scenario identifier.")
    directive_interpretations: list[DirectiveInterpretation] = Field(
        default_factory=list,
        description="Interpretation of the directives applied to the scenario.",
    )
    hourly_plan: list[HourlyPlan] = Field(
        default_factory=list,
        description="The 24-hour optimized schedule.",
    )
    total_grid_kwh: float = Field(ge=0, description="Total grid import across the horizon.")
    total_solar_kwh: float = Field(ge=0, description="Total solar usage across the horizon.")
    total_battery_kwh: float = Field(ge=0, description="Total battery movement across the horizon.")
    total_cost_bdt: float = Field(ge=0, description="Total grid cost across the horizon in BDT.")
    peak_grid_kwh: float = Field(ge=0, description="Peak grid usage in kWh for any hour.")
    plan_summary: str = Field(description="Short summary of the optimized plan.")
    message: str = Field(default="ok", description="Summary of the optimization result.")


class GridOptimizationRequest(BaseModel):
    """Input payload for a simple grid optimization request."""

    demand_mw: float = Field(gt=0, description="Expected demand in MW.")
    available_capacity_mw: float = Field(gt=0, description="Available capacity in MW.")
    priority: Literal["cost", "reliability", "balanced"] = Field(
        default="balanced",
        description="Optimization preference.",
    )
    notes: str | None = Field(default=None, description="Optional free-form context.")


class OptimizationResult(BaseModel):
    """Structured result returned by the optimization service."""

    status: str
    allocated_mw: float
    remaining_capacity_mw: float
    recommendation: str


class OptimizeEnergyResponse(BaseModel):
    """Placeholder response for the energy optimization endpoint."""

    status: str
    message: str


class LLMRecommendationRequest(BaseModel):
    """Prompt wrapper for LLM-assisted recommendations."""

    context: str = Field(min_length=1, description="Operational context for the model.")


class LLMRecommendationResponse(BaseModel):
    """LLM output for user-facing guidance."""

    text: str


class HealthResponse(BaseModel):
    """Basic service health response."""

    status: str
    service: str
