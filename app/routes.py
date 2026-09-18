from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .guardrails import GuardrailViolation, validate_llm_output
from .llm import interpret_operator_notes_raw
from .models import OptimizeRequest, OptimizeResponse
from .optimizer import optimize_energy as run_optimizer


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(payload: OptimizeRequest) -> OptimizeResponse:
    try:
        raw_llm_output = interpret_operator_notes_raw(payload.operator_notes)
        validated_directives = validate_llm_output(raw_llm_output, len(payload.operator_notes))
        result = run_optimizer(payload, validated_directives.directive_interpretations)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail="Validation errors") from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Validation errors") from exc

    return result
