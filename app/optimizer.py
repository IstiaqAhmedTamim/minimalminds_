from fastapi import HTTPException
import pulp

from .models import BatteryInput, Directive, HourInput, HourPlan


def optimize(hours: list[HourInput], battery: BatteryInput, directives: list[Directive]) -> list[HourPlan]:
    solar_factor = [1.0] * 24
    reserve = [battery.minimum_energy_kwh] * 24
    charge_allowed = [True] * 24
    discharge_allowed = [True] * 24
    grid_cap = [None] * 24
    for directive in directives:
        if not directive.applies or directive.structured_adjustment is None:
            continue
        adjustment = directive.structured_adjustment
        for hour in adjustment["hours"]:
            if directive.directive_type == "solar_reduction":
                solar_factor[hour] = min(solar_factor[hour], adjustment["factor"])
            elif directive.directive_type == "minimum_battery_reserve":
                reserve[hour] = max(reserve[hour], adjustment["minimum_energy_kwh"])
            elif directive.directive_type == "no_charge_window":
                charge_allowed[hour] = False
            elif directive.directive_type == "no_discharge_window":
                discharge_allowed[hour] = False
            elif directive.directive_type == "max_grid_window":
                grid_cap[hour] = adjustment["max_grid_kwh"] if grid_cap[hour] is None else min(grid_cap[hour], adjustment["max_grid_kwh"])

    problem = pulp.LpProblem("gridwise_energy", pulp.LpMinimize)
    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0, upBound=grid_cap[h]) for h in range(24)]
    solar = [pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=hours[h].solar_kwh * solar_factor[h]) for h in range(24)]
    charge = [pulp.LpVariable(f"charge_{h}", lowBound=0, upBound=battery.max_charge_kwh_per_hour if charge_allowed[h] else 0) for h in range(24)]
    discharge = [pulp.LpVariable(f"discharge_{h}", lowBound=0, upBound=battery.max_discharge_kwh_per_hour if discharge_allowed[h] else 0) for h in range(24)]
    charging_mode = [pulp.LpVariable(f"charging_mode_{h}", cat="Binary") for h in range(24)]
    energy = [pulp.LpVariable(f"energy_{h}", lowBound=reserve[h], upBound=battery.capacity_kwh) for h in range(24)]

    for hour in range(24):
        previous = battery.initial_energy_kwh if hour == 0 else energy[hour - 1]
        problem += grid[hour] + solar[hour] + discharge[hour] == hours[hour].demand_kwh + charge[hour]
        problem += energy[hour] == previous + charge[hour] - discharge[hour]
        problem += charge[hour] <= battery.max_charge_kwh_per_hour * charging_mode[hour]
        problem += discharge[hour] <= battery.max_discharge_kwh_per_hour * (1 - charging_mode[hour])
    problem += energy[23] == battery.initial_energy_kwh
    problem += pulp.lpSum(grid[h] * hours[h].tariff_bdt_per_kwh for h in range(24))
    status = problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))
    if pulp.LpStatus[status] != "Optimal":
        raise HTTPException(status_code=422, detail="No feasible schedule satisfies all constraints")

    plan: list[HourPlan] = []
    for hour in range(24):
        charge_value = charge[hour].value() or 0.0
        discharge_value = discharge[hour].value() or 0.0
        action = "charge" if charge_value > 1e-7 else "discharge" if discharge_value > 1e-7 else "idle"
        plan.append(HourPlan(
            hour=hour,
            grid_kwh=round(grid[hour].value() or 0.0, 6),
            solar_used_kwh=round(solar[hour].value() or 0.0, 6),
            battery_action=action,
            battery_kwh=round(charge_value if action == "charge" else discharge_value if action == "discharge" else 0.0, 6),
            battery_energy_after_kwh=round(energy[hour].value() or 0.0, 6),
        ))
    return plan