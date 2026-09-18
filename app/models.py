from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HourInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class BatteryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)

    @field_validator("initial_energy_kwh")
    @classmethod
    def initial_must_be_within_capacity(cls, value: float, info):
        capacity = info.data.get("capacity_kwh")
        if capacity is not None and value > capacity:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        return value

    @field_validator("minimum_energy_kwh")
    @classmethod
    def minimum_must_be_within_capacity(cls, value: float, info):
        capacity = info.data.get("capacity_kwh")
        if capacity is not None and value > capacity:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        return value


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario_id: str = Field(min_length=1)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryInput

    @field_validator("hours")
    @classmethod
    def hours_must_be_complete(cls, value: list[HourInput]):
        numbers = [item.hour for item in value]
        if numbers != list(range(24)):
            raise ValueError("hours must contain unique hours 0 through 23 in ascending order")
        return value

    @field_validator("operator_notes")
    @classmethod
    def notes_must_contain_text(cls, value: list[str]):
        if any(not note.strip() for note in value):
            raise ValueError("operator_notes must contain non-empty strings")
        return value


DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]


class Directive(BaseModel):
    note_index: int = Field(ge=0)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict | None
    explanation: str = Field(min_length=1)


class HourPlan(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[Directive]
    hourly_plan: list[HourPlan]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str