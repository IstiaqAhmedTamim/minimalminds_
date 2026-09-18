import json
from functools import lru_cache
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from .config import get_settings
from .models import DirectiveInterpretation, DirectiveType


class OperatorNoteInterpretation(BaseModel):
    """Structured interpretation for one operator note."""

    note_index: int = Field(ge=0, description="Zero-based note index.")
    applies: bool = Field(description="Whether the note changes the plan.")
    directive_type: DirectiveType = Field(description="Directive selected for the note.")
    structured_adjustment: str = Field(description="Machine-readable adjustment summary.")
    explanation: str = Field(description="Short explanation for the interpretation.")


class _InterpretationEnvelope(BaseModel):
    """Top-level JSON payload expected from the LLM."""

    interpretations: list[OperatorNoteInterpretation]


@lru_cache(maxsize=1)
def _get_openai_client() -> OpenAI | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _call_operator_notes_model(notes: list[str]) -> dict[str, Any]:
    cleaned_notes = [note.strip() for note in notes if note and note.strip()]
    if not 1 <= len(cleaned_notes) <= 3:
        raise ValueError("notes must contain between 1 and 3 non-empty items")

    client = _get_openai_client()
    if client is None:
        return {
            "interpretations": [
                {
                    "note_index": index,
                    "applies": False,
                    "directive_type": DirectiveType.no_op.value,
                    "structured_adjustment": None,
                    "explanation": "OPENAI_API_KEY is not configured, so the note was not interpreted.",
                }
                for index, _ in enumerate(cleaned_notes)
            ]
        }

    settings = get_settings()
    response = client.responses.create(
        model=settings.openai_model,
        temperature=0,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a GridWise planning assistant. "
                    "Interpret operator notes into JSON only. "
                    "Return one interpretation per input note and do not add markdown or commentary. "
                    "Supported directives are solar_reduction, minimum_battery_reserve, no_charge_window, "
                    "no_discharge_window, max_grid_window, and no_op."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "notes": cleaned_notes,
                        "required_fields": [
                            "note_index",
                            "applies",
                            "directive_type",
                            "structured_adjustment",
                            "explanation",
                        ],
                    },
                    ensure_ascii=True,
                ),
            },
        ],
        text={"format": {"type": "json_object"}},
    )

    raw_text = response.output_text.strip()
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM did not return valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM output must be a JSON object")

    return payload


def interpret_operator_notes_raw(notes: list[str]) -> dict[str, Any]:
    """Return the raw JSON object produced by the model."""

    return _call_operator_notes_model(notes)


def interpret_operator_notes(notes: list[str]) -> list[DirectiveInterpretation]:
    """Interpret 1-3 operator notes into deterministic directive guidance."""

    raw_payload = _call_operator_notes_model(notes)

    try:
        envelope = _InterpretationEnvelope.model_validate(raw_payload)
    except ValidationError as exc:
        raise ValueError("LLM JSON did not match the expected interpretation schema") from exc

    if len(envelope.interpretations) != len(cleaned_notes):
        raise ValueError("LLM must return one interpretation for every input note")

    return [
        DirectiveInterpretation(
            note_index=item.note_index,
            applies=item.applies,
            directive_type=item.directive_type,
            structured_adjustment=item.structured_adjustment,
            explanation=item.explanation,
        )
        for item in envelope.interpretations
    ]
