import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ortools.linear_solver import pywraplp

from .models import (
    AppliedHour,
    AppliedScenario,
    DirectiveType,
    DirectiveInterpretation,
    HourlyPlan,
    GridOptimizationRequest,
    OptimizationResult,
    OptimizeResponse,
    OptimizeRequest,
    BatteryAction,
)


def _coerce_adjustment(raw_adjustment: Any) -> dict[str, Any]:
    if raw_adjustment is None:
        return {}
    if isinstance(raw_adjustment, Mapping):
        return dict(raw_adjustment)
    if isinstance(raw_adjustment, str):
        stripped = raw_adjustment.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if hasattr(raw_adjustment, "model_dump"):
        dumped = raw_adjustment.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _serialize_adjustment(raw_adjustment: Any) -> str:
    if raw_adjustment is None:
        return "null"
    if isinstance(raw_adjustment, str):
        return raw_adjustment
    try:
        return json.dumps(raw_adjustment, ensure_ascii=True)
    except TypeError:
        return json.dumps(str(raw_adjustment), ensure_ascii=True)


def _coerce_directive_type(value: Any) -> DirectiveType | None:
    if value is None:
        return None
    if isinstance(value, DirectiveType):
        return value
    try:
        return DirectiveType(str(value))
    except ValueError:
        return None


def _coerce_directives(validated_directives: Sequence[Any]) -> list[dict[str, Any]]:
    normalized_directives: list[dict[str, Any]] = []
    for directive in validated_directives:
        if isinstance(directive, Mapping):
            source = dict(directive)
        elif hasattr(directive, "model_dump"):
            source = directive.model_dump()
        else:
            source = {
                key: getattr(directive, key)
                for key in ("note_index", "applies", "directive_type", "structured_adjustment", "explanation")
                if hasattr(directive, key)
            }

        source["directive_type"] = _coerce_directive_type(source.get("directive_type"))
        normalized_directives.append(source)

    return normalized_directives


def _select_hours(adjustment: Mapping[str, Any], default_hours: Iterable[int]) -> list[int]:
    def _is_hour_collection(value: Any) -> bool:
        return isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping))

    if "hours" in adjustment and _is_hour_collection(adjustment["hours"]):
        selected = [int(hour) for hour in adjustment["hours"]]
    elif "hour_range" in adjustment and _is_hour_collection(adjustment["hour_range"]):
        hour_range = list(adjustment["hour_range"])
        if len(hour_range) == 2:
            start_hour = int(hour_range[0])
            end_hour = int(hour_range[1])
            selected = list(range(min(start_hour, end_hour), max(start_hour, end_hour) + 1))
        else:
            selected = list(default_hours)
    elif "start_hour" in adjustment and "end_hour" in adjustment:
        start_hour = int(adjustment["start_hour"])
        end_hour = int(adjustment["end_hour"])
        selected = list(range(min(start_hour, end_hour), max(start_hour, end_hour) + 1))
    elif "hour" in adjustment:
        selected = [int(adjustment["hour"])]
    else:
        selected = list(default_hours)

    return [hour for hour in sorted(set(selected)) if 0 <= hour <= 23]


def apply_directives(
    original_scenario: OptimizeRequest,
    validated_directives: Sequence[Any],
) -> AppliedScenario:
    """Apply validated directives to a scenario without changing demand or tariff."""

    normalized_directives = _coerce_directives(validated_directives)
    applied_hours = {
        hour.hour: AppliedHour(
            hour=hour.hour,
            demand_kwh=hour.demand_kwh,
            tariff_bdt_per_kwh=hour.tariff_bdt_per_kwh,
            original_solar_kwh=hour.solar_kwh,
            effective_solar_kwh=hour.solar_kwh,
            minimum_battery_reserve_kwh=original_scenario.battery.minimum_energy_kwh,
            charge_allowed=True,
            discharge_allowed=True,
            max_grid_kwh=None,
        )
        for hour in original_scenario.hours
    }

    for directive in normalized_directives:
        if directive.get("applies") is False:
            continue

        directive_type = directive.get("directive_type")
        if directive_type is None:
            continue

        adjustment = _coerce_adjustment(directive.get("structured_adjustment"))
        target_hours = _select_hours(adjustment, applied_hours.keys())

        if directive_type == DirectiveType.solar_reduction:
            factor = float(
                adjustment.get(
                    "factor",
                    adjustment.get("solar_factor", adjustment.get("reduction_factor", 1.0)),
                )
            )
            for hour in target_hours:
                applied_hours[hour].effective_solar_kwh *= factor
            continue

        if directive_type == DirectiveType.minimum_battery_reserve:
            reserve_value = float(
                adjustment.get(
                    "minimum_battery_reserve_kwh",
                    adjustment.get(
                        "minimum_energy_kwh",
                        adjustment.get("reserve_kwh", original_scenario.battery.minimum_energy_kwh),
                    ),
                )
            )
            for hour in target_hours:
                applied_hours[hour].minimum_battery_reserve_kwh = max(
                    applied_hours[hour].minimum_battery_reserve_kwh,
                    reserve_value,
                )
            continue

        if directive_type == DirectiveType.no_charge_window:
            for hour in target_hours:
                applied_hours[hour].charge_allowed = False
            continue

        if directive_type == DirectiveType.no_discharge_window:
            for hour in target_hours:
                applied_hours[hour].discharge_allowed = False
            continue

        if directive_type == DirectiveType.max_grid_window:
            for hour in target_hours:
                cap_value = adjustment.get("max_grid_kwh")
                if cap_value is None:
                    cap_value = adjustment.get("grid_kwh")
                if cap_value is None:
                    cap_value = adjustment.get("limit_kwh")
                if cap_value is None:
                    cap_value = max(
                        0.0,
                        applied_hours[hour].demand_kwh - applied_hours[hour].effective_solar_kwh,
                    )
                cap = float(cap_value)
                current_cap = applied_hours[hour].max_grid_kwh
                applied_hours[hour].max_grid_kwh = cap if current_cap is None else min(current_cap, cap)
            continue

    return AppliedScenario(
        scenario_id=original_scenario.scenario_id,
        battery=original_scenario.battery,
        hours=[applied_hours[hour.hour] for hour in original_scenario.hours],
        applied_directives=normalized_directives,
    )


def _directive_for_hour(hour: int, directives: Sequence[dict[str, Any]]) -> DirectiveType:
    precedence = (
        DirectiveType.no_charge_window,
        DirectiveType.no_discharge_window,
        DirectiveType.max_grid_window,
        DirectiveType.minimum_battery_reserve,
        DirectiveType.solar_reduction,
    )

    for directive_type in precedence:
        for directive in directives:
            if directive.get("directive_type") != directive_type:
                continue
            adjustment = _coerce_adjustment(directive.get("structured_adjustment"))
            if hour in _select_hours(adjustment, range(24)):
                return directive_type

    return DirectiveType.no_op


def _battery_action_for_hour(charge_value: float, discharge_value: float) -> BatteryAction:
    epsilon = 1e-9
    if charge_value > epsilon and charge_value >= discharge_value:
        return BatteryAction.charge
    if discharge_value > epsilon:
        return BatteryAction.discharge
    return BatteryAction.idle


def optimize_energy(
    original_scenario: OptimizeRequest,
    validated_directives: Sequence[Any],
) -> OptimizeResponse:
    """Optimize a 24-hour scenario using linear programming."""

    applied_scenario = apply_directives(original_scenario, validated_directives)
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("Google OR-Tools linear solver GLOP is unavailable")

    hours = applied_scenario.hours
    battery = applied_scenario.battery
    grid_vars: list[Any] = []
    battery_charge_vars: list[Any] = []
    battery_discharge_vars: list[Any] = []
    battery_energy_vars: list[Any] = []
    solar_used_vars: list[Any] = []

    for index, hour in enumerate(hours):
        charge_cap = 0.0 if not hour.charge_allowed else battery.max_charge_kwh_per_hour
        discharge_cap = 0.0 if not hour.discharge_allowed else battery.max_discharge_kwh_per_hour
        grid_cap = hour.max_grid_kwh if hour.max_grid_kwh is not None else solver.infinity()

        grid_var = solver.NumVar(0.0, grid_cap, f"grid_kwh_{index}")
        charge_var = solver.NumVar(0.0, charge_cap, f"battery_charge_{index}")
        discharge_var = solver.NumVar(0.0, discharge_cap, f"battery_discharge_{index}")
        solar_used_var = solver.NumVar(0.0, hour.effective_solar_kwh, f"solar_used_{index}")
        battery_energy_var = solver.NumVar(
            hour.minimum_battery_reserve_kwh,
            battery.capacity_kwh,
            f"battery_energy_{index}",
        )

        grid_vars.append(grid_var)
        battery_charge_vars.append(charge_var)
        battery_discharge_vars.append(discharge_var)
        solar_used_vars.append(solar_used_var)
        battery_energy_vars.append(battery_energy_var)

        solver.Add(
            grid_var + solar_used_var + discharge_var == hour.demand_kwh + charge_var
        )

        if index == 0:
            solver.Add(
                battery_energy_var == battery.initial_energy_kwh + charge_var - discharge_var
            )
        else:
            solver.Add(
                battery_energy_var
                == battery_energy_vars[index - 1] + charge_var - discharge_var
            )

    solver.Add(battery_energy_vars[-1] == battery.initial_energy_kwh)

    objective = solver.Objective()
    for index, hour in enumerate(hours):
        objective.SetCoefficient(grid_vars[index], hour.tariff_bdt_per_kwh)
        objective.SetCoefficient(battery_charge_vars[index], 1e-6)
        objective.SetCoefficient(battery_discharge_vars[index], 1e-6)
    objective.SetMinimization()

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        raise RuntimeError("Energy optimization is infeasible for the supplied scenario")

    hourly_plan: list[HourlyPlan] = []
    directive_interpretations: list[DirectiveInterpretation] = []
    total_grid_kwh = 0.0
    total_solar_kwh = 0.0
    total_battery_kwh = 0.0
    total_cost_bdt = 0.0
    peak_grid_kwh = 0.0

    normalized_directives = _coerce_directives(validated_directives)
    for directive in normalized_directives:
        directive_interpretations.append(
            DirectiveInterpretation(
                note_index=int(directive.get("note_index", 0)),
                applies=bool(directive.get("applies", False)),
                directive_type=directive.get("directive_type") or DirectiveType.no_op,
                structured_adjustment=_serialize_adjustment(directive.get("structured_adjustment")),
                explanation=str(directive.get("explanation", "")),
            )
        )

    for index, hour in enumerate(hours):
        grid_kwh = grid_vars[index].solution_value()
        battery_charge = battery_charge_vars[index].solution_value()
        battery_discharge = battery_discharge_vars[index].solution_value()
        battery_energy = battery_energy_vars[index].solution_value()
        solar_used = solar_used_vars[index].solution_value()
        battery_action = _battery_action_for_hour(battery_charge, battery_discharge)
        if battery_action == BatteryAction.charge:
            battery_kwh = battery_charge
        elif battery_action == BatteryAction.discharge:
            battery_kwh = battery_discharge
        else:
            battery_kwh = 0.0

        total_grid_kwh += grid_kwh
        total_solar_kwh += solar_used
        total_battery_kwh += battery_charge + battery_discharge
        total_cost_bdt += grid_kwh * hour.tariff_bdt_per_kwh
        peak_grid_kwh = max(peak_grid_kwh, grid_kwh)

        hourly_plan.append(
            HourlyPlan(
                hour=hour.hour,
                directive=_directive_for_hour(hour.hour, applied_scenario.applied_directives),
                battery_action=battery_action,
                grid_kwh=round(grid_kwh, 6),
                battery_kwh=round(battery_kwh, 6),
                solar_kwh=round(solar_used, 6),
                demand_kwh=round(hour.demand_kwh, 6),
            )
        )

    plan_summary = (
        f"Optimized {len(hourly_plan)} hours with peak grid {peak_grid_kwh:.2f} kWh and "
        f"total cost {total_cost_bdt:.2f} BDT."
    )

    return OptimizeResponse(
        scenario_id=applied_scenario.scenario_id,
        directive_interpretations=directive_interpretations,
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid_kwh, 6),
        total_solar_kwh=round(total_solar_kwh, 6),
        total_battery_kwh=round(total_battery_kwh, 6),
        total_cost_bdt=round(total_cost_bdt, 6),
        peak_grid_kwh=round(peak_grid_kwh, 6),
        plan_summary=plan_summary,
        message="ok",
    )


class GridOptimizer:
    """Solve a simple allocation problem using OR-Tools."""

    def optimize(self, payload: GridOptimizationRequest) -> OptimizationResult:
        solver = pywraplp.Solver.CreateSolver("GLOP")
        if solver is None:
            allocated_mw = min(payload.demand_mw, payload.available_capacity_mw)
            return OptimizationResult(
                status="fallback",
                allocated_mw=allocated_mw,
                remaining_capacity_mw=payload.available_capacity_mw - allocated_mw,
                recommendation="Solver unavailable; used deterministic fallback allocation.",
            )

        allocated = solver.NumVar(0.0, payload.available_capacity_mw, "allocated")
        solver.Add(allocated <= payload.demand_mw)

        objective = solver.Objective()
        objective.SetCoefficient(allocated, 1.0)
        objective.SetMaximization()

        if payload.priority == "reliability":
            solver.Add(allocated == payload.demand_mw)

        status = solver.Solve()
        allocated_mw = (
            allocated.solution_value()
            if status == pywraplp.Solver.OPTIMAL
            else min(payload.demand_mw, payload.available_capacity_mw)
        )

        recommendation = self._build_recommendation(payload, allocated_mw)
        return OptimizationResult(
            status="optimal" if status == pywraplp.Solver.OPTIMAL else "approximate",
            allocated_mw=round(allocated_mw, 3),
            remaining_capacity_mw=round(payload.available_capacity_mw - allocated_mw, 3),
            recommendation=recommendation,
        )

    def _build_recommendation(self, payload: GridOptimizationRequest, allocated_mw: float) -> str:
        if allocated_mw >= payload.demand_mw:
            return "Demand can be fully covered with current capacity."
        if payload.priority == "reliability":
            return "Increase available capacity before scheduling this load."
        return "Partial allocation recommended with staged demand handling."
