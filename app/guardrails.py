import math

from .models import Directive

REQUIRED_FIELDS = {
    "solar_reduction": {"hours", "factor"},
    "minimum_battery_reserve": {"hours", "minimum_energy_kwh"},
    "no_charge_window": {"hours"},
    "no_discharge_window": {"hours"},
    "max_grid_window": {"hours", "max_grid_kwh"},
}


def validate_directives(directives: list[Directive], note_count: int, battery_capacity_kwh: float | None = None) -> list[Directive]:
    if len(directives) != note_count:
        raise ValueError("LLM must return exactly one directive per operator note")

    validated: list[Directive] = []
    for index, directive in enumerate(directives):
        if directive.note_index != index:
            raise ValueError("directive note_index values must be sequential")
        if directive.directive_type == "no_op":
            if directive.applies or directive.structured_adjustment is not None:
                raise ValueError("no_op directives must not apply")
            validated.append(directive)
            continue
        if not directive.applies or directive.structured_adjustment is None:
            raise ValueError("relevant directives must apply and have an adjustment")
        adjustment = directive.structured_adjustment
        if set(adjustment) != REQUIRED_FIELDS[directive.directive_type]:
            raise ValueError(f"invalid fields for {directive.directive_type}")
        hours = adjustment["hours"]
        if not isinstance(hours, list) or hours != sorted(set(hours)) or any(not isinstance(hour, int) or not 0 <= hour <= 23 for hour in hours):
            raise ValueError("directive hours must be unique ascending integers from 0 to 23")
        if directive.directive_type == "solar_reduction" and (
            not _finite_number(adjustment["factor"]) or not 0 <= adjustment["factor"] <= 1
        ):
            raise ValueError("solar reduction factor must be between 0 and 1")
        for field in ("minimum_energy_kwh", "max_grid_kwh"):
            if field in adjustment and (not _finite_number(adjustment[field]) or adjustment[field] < 0):
                raise ValueError(f"{field} must be non-negative")
        if (
            directive.directive_type == "minimum_battery_reserve"
            and battery_capacity_kwh is not None
            and adjustment["minimum_energy_kwh"] > battery_capacity_kwh
        ):
            raise ValueError("minimum battery reserve cannot exceed battery capacity")
        validated.append(directive)
    return validated


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)