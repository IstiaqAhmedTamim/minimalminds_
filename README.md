# GridWise LLM Energy Optimizer

FastAPI implementation of the BUP CSE Fest 2026 GridWise challenge. The request path is deliberately explicit:

`operator_notes` -> Gemini 2.5 Flash -> Pydantic/deterministic guardrails -> PuLP/CBC optimizer -> independently assembled response.

## Run locally

Requires Python 3.11 and a Gemini API key for optimization requests. The service fails closed when the key is missing so operator notes can never silently bypass the mandatory LLM stage.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit GEMINI_API_KEY in this untracked file
uvicorn app.main:app --reload
```

The service loads `GEMINI_API_KEY`, optional `GEMINI_MODEL`, and optional `CORS_ORIGINS` from `.env` locally. In Render or Docker, configure them as environment variables instead. Set `CORS_ORIGINS` to a comma-separated origin allowlist in production; `*` is the development default. Do not commit `.env`.

Endpoints:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/optimize-energy \
	-H 'content-type: application/json' \
	--data @scenario.json
```

The POST body contains `scenario_id`, 1-3 `operator_notes`, exactly 24 ordered `hours`, and the `battery` limits described in the challenge. Swagger is available at `/docs`.

## Public sample validation

Save the organizer-provided public sample pack as `public_samples.json`, start the service with `GEMINI_API_KEY` configured, then run:

```bash
python scripts/check_samples.py public_samples.json --base-url http://localhost:8000
```

The runner posts every case and checks the scenario ID, one interpretation per note, and all 24 plan entries. The judge remains the source of truth for equivalent optimal schedules.

## Design notes

- Gemini is prompted for strict JSON and exactly one directive per note. The model is never allowed to directly write a schedule.
- Guardrails reject unknown directive types, malformed adjustment shapes, invalid hours, invalid factors, and incorrect note indexes. No-op directives must have `applies: false` and a null adjustment.
- PuLP minimizes tariff-weighted grid import while enforcing balance, solar availability, charge/discharge limits, reserves, grid caps, and end-of-day battery neutrality.
- Response totals are recalculated from the returned hourly plan and rounded to six decimal places.
- A final deterministic replay validates effective solar, every directive window, battery transitions, energy balance, bounds, and end-of-day neutrality before the response is returned.
- The API requires `GEMINI_API_KEY`; it never silently treats notes as `no_op` when Gemini is unavailable.

## Docker and Render

```bash
docker build -t gridwise:2026 .
docker run --rm -p 8000:8000 -e GEMINI_API_KEY="$GEMINI_API_KEY" gridwise:2026
```

For Render, create a **Web Service** from this repository, choose Docker, and add `GEMINI_API_KEY` as a secret environment variable. Render uses the Dockerfile and publishes port 8000. Never commit `.env` or a key.

Render can also use the included `render.yaml` Blueprint. Set the `GEMINI_API_KEY` secret when prompted; the Blueprint supplies the model name and uses the Dockerfile startup command.

## Known limitations

Gemini failures or a missing key are returned as a 502 so a stale or invented directive cannot silently reach the optimizer. Infeasible combinations of reserves, windows, and battery limits return 422.