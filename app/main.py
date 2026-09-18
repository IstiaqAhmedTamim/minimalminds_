import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .guardrails import validate_directives
from .interpreter import interpret_notes
from .models import OptimizeRequest, OptimizeResponse
from .optimizer import optimize
from .replay import validate_plan

app = FastAPI(title="GridWise Energy Optimizer", version="1.0.0")
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    try:
        directives = validate_directives(
            interpret_notes(request.operator_notes),
            len(request.operator_notes),
            request.battery.capacity_kwh,
        )
        plan = optimize(request.hours, request.battery, directives)
        validate_plan(request.hours, request.battery, directives, plan)
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    total_grid = sum(item.grid_kwh for item in plan)
    total_cost = sum(item.grid_kwh * hour.tariff_bdt_per_kwh for item, hour in zip(plan, request.hours))
    return OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=directives,
        hourly_plan=plan,
        total_grid_kwh=round(total_grid, 6),
        total_cost_bdt=round(total_cost, 6),
        peak_grid_kwh=round(max(item.grid_kwh for item in plan), 6),
        plan_summary=f"Scheduled 24 hours with {total_grid:.2f} kWh grid import at {total_cost:.2f} BDT.",
    )