from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from .models import DirectiveType, GridOptimizationRequest, LLMRecommendationRequest


class GuardrailViolation(ValueError):
    """Raised when input fails business or safety checks."""


class LLMDirectiveInterpretation(BaseModel):
    """Validated interpretation for a single operator note."""

    note_index: int = Field(ge=0, description="Zero-based note index.")
    applies: bool = Field(description="Whether the directive applies.")
    directive_type: DirectiveType = Field(description="Directive type returned by the LLM.")
    structured_adjustment: dict[str, Any] | None = Field(
        default=None,
        description="Structured adjustment payload returned by the LLM.",
    )
    explanation: str = Field(description="Short explanation for the interpretation.")

    @model_validator(mode="after")
    def validate_directive_rules(self) -> "LLMDirectiveInterpretation":
        if self.directive_type == DirectiveType.no_op:
            if self.applies is not False:
                raise ValueError("no_op interpretations must set applies to false")
            if self.structured_adjustment is not None:
                raise ValueError("no_op interpretations must set structured_adjustment to null")
        else:
            if self.applies is not True:
                raise ValueError("non-no_op interpretations must set applies to true")

        return self


class LLMHourlyPlan(BaseModel):
    """Validated hourly plan returned by the LLM."""

    hour: int = Field(ge=0, le=23, description="Hour index from 0 to 23.")
    solar_factor: float = Field(
        ge=0,
        le=1,
        description="Solar factor between 0 and 1.",
    )
    reserve_kwh: float = Field(ge=0, description="Reserve energy in kWh.")
    grid_kwh: float = Field(ge=0, description="Grid energy in kWh.")


class LLMOutput(BaseModel):
    """Validated GridWise LLM output payload."""

    expected_note_count: int = Field(ge=1, exclude=True)
    directive_interpretations: list[LLMDirectiveInterpretation] = Field(default_factory=list)
    hourly_plan: list[LLMHourlyPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_output(self) -> "LLMOutput":
        if len(self.directive_interpretations) != self.expected_note_count:
            raise ValueError("exactly one result is required for every note")

        note_indexes = [item.note_index for item in self.directive_interpretations]
        if note_indexes != list(range(self.expected_note_count)):
            raise ValueError("note indexes must start at 0 and increase by 1 for each note")

        hours = [item.hour for item in self.hourly_plan]
        if hours != sorted(hours):
            raise ValueError("hours must be sorted in ascending order")

        if len(set(hours)) != len(hours):
            raise ValueError("hours must be unique")

        return self


def validate_llm_output(payload: dict[str, Any], note_count: int) -> LLMOutput:
    """Validate and normalize the structured LLM output."""

    return LLMOutput.model_validate({**payload, "expected_note_count": note_count})


def validate_grid_request(payload: GridOptimizationRequest) -> None:
    """Apply lightweight business guardrails before optimization."""

    if payload.available_capacity_mw < payload.demand_mw and payload.priority == "reliability":
        raise GuardrailViolation(
            "Reliability mode requires capacity at least equal to demand."
        )

    if payload.notes and len(payload.notes) > 2000:
        raise GuardrailViolation("Notes must be 2000 characters or fewer.")


def validate_llm_request(payload: LLMRecommendationRequest) -> None:
    """Keep prompts concise and actionable before calling the model."""

    if len(payload.context.strip()) < 10:
        raise GuardrailViolation("Context must contain at least 10 non-space characters.")
