import math

from fastapi import HTTPException

from .models import BatteryInput, Directive, HourInput, HourPlan


def validate_plan(
    hours: list[HourInput],
    battery: BatteryInput,
    directives: list[Directive],
    plan: list[HourPlan],
) -> None:
    solar_factor = [1.0] * 24
    reserve = [battery.minimum_energy_kwh] * 24
    charge_allowed = [True] * 24
    discharge_allowed = [True] * 24
    grid_cap = [None] * 24
    for directive in directives:
        adjustment = directive.structured_adjustment
        if not directive.applies or adjustment is None:
            continue
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

    energy_before = battery.initial_energy_kwh
    if len(plan) != 24:
        raise HTTPException(status_code=500, detail="optimizer returned an incomplete hourly plan")
    for hour, item in enumerate(plan):
        values = (item.grid_kwh, item.solar_used_kwh, item.battery_kwh, item.battery_energy_after_kwh)
        if not all(math.isfinite(value) for value in values):
            raise HTTPException(status_code=500, detail="optimizer returned a non-finite schedule value")
        if item.hour != hour or min(item.grid_kwh, item.solar_used_kwh, item.battery_kwh) < -0.01:
            raise HTTPException(status_code=500, detail="optimizer returned an invalid hourly plan")
        if item.solar_used_kwh > hours[hour].solar_kwh * solar_factor[hour] + 0.01:
            raise HTTPException(status_code=500, detail="schedule exceeds effective solar availability")
        if item.grid_kwh > (grid_cap[hour] if grid_cap[hour] is not None else math.inf) + 0.01:
            raise HTTPException(status_code=500, detail="schedule exceeds a grid cap")

        amount = item.battery_kwh
        if item.battery_action == "charge":
            if not charge_allowed[hour] or amount > battery.max_charge_kwh_per_hour + 0.01:
                raise HTTPException(status_code=500, detail="schedule violates charge constraints")
            expected_energy = energy_before + amount
            charge_amount, discharge_amount = amount, 0.0
        elif item.battery_action == "discharge":
            if not discharge_allowed[hour] or amount > battery.max_discharge_kwh_per_hour + 0.01:
                raise HTTPException(status_code=500, detail="schedule violates discharge constraints")
            expected_energy = energy_before - amount
            charge_amount, discharge_amount = 0.0, amount
        else:
            if amount > 0.01:
                raise HTTPException(status_code=500, detail="idle schedule entries must have zero battery_kwh")
            expected_energy = energy_before
            charge_amount, discharge_amount = 0.0, 0.0

        if abs(item.battery_energy_after_kwh - expected_energy) > 0.01:
            raise HTTPException(status_code=500, detail="schedule battery transition is inconsistent")
        if item.battery_energy_after_kwh < reserve[hour] - 0.01 or item.battery_energy_after_kwh > battery.capacity_kwh + 0.01:
            raise HTTPException(status_code=500, detail="schedule violates battery bounds")
        balance = item.grid_kwh + item.solar_used_kwh + discharge_amount - hours[hour].demand_kwh - charge_amount
        if abs(balance) > 0.01:
            raise HTTPException(status_code=500, detail="schedule violates hourly energy balance")
        energy_before = item.battery_energy_after_kwh

    if abs(energy_before - battery.initial_energy_kwh) > 0.01:
        raise HTTPException(status_code=500, detail="schedule violates end-of-day battery neutrality")