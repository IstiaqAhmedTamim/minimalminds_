import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

from .models import Directive

logger = logging.getLogger(__name__)
load_dotenv()


def interpret_notes(notes: list[str]) -> list[Directive]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required to interpret operator_notes")

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=_prompt(notes),
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        parsed: Any = json.loads(response.text)
        raw_directives = parsed.get("directives", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(raw_directives, list) or len(raw_directives) != len(notes):
            raise ValueError("Gemini returned the wrong number of directives")
        return [Directive.model_validate({**item, "note_index": index}) for index, item in enumerate(raw_directives)]
    except Exception as exc:
        logger.error("Gemini interpretation failed: %s", type(exc).__name__)
        raise RuntimeError("LLM interpretation failed") from exc


def _prompt(notes: list[str]) -> str:
    return f"""You are the operator-note interpreter in an energy scheduling API.
Return JSON only in this shape: {{"directives": [{{"applies": true, "directive_type": "...", "structured_adjustment": {{...}}, "explanation": "..."}}]}}.
Return exactly one item per note, in the same order. Allowed directive_type values are:
- solar_reduction: adjustment {{"hours": [0], "factor": 0.2}} where factor is the remaining solar fraction
- minimum_battery_reserve: {{"hours": [0], "minimum_energy_kwh": 120}}
- no_charge_window: {{"hours": [0]}}
- no_discharge_window: {{"hours": [0]}}
- max_grid_window: {{"hours": [0], "max_grid_kwh": 100}}
- no_op: null
Use integer hours 0-23, unique and ascending, and use start-inclusive/end-exclusive time ranges.
Relevant energy instructions must never be no_op. For no_op set applies false and adjustment null. For every other type set applies true.
Interpret paraphrases, percentages, AM/PM, and written time ranges. Do not invent constraints absent from a note.

Operator notes:
{json.dumps(notes, ensure_ascii=True)}"""