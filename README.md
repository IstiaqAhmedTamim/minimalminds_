# GridWise LLM Energy Optimizer

FastAPI implementation of the **BUP CSE Fest 2026 – GridWise LLM Energy Optimization Challenge**.

The complete request pipeline is:

`operator_notes → Gemini 2.5 Flash → Pydantic Guardrails → PuLP/CBC Optimizer → Validated JSON Response`

---

## Live Deployment

**Render API:** https://minimalminds.onrender.com/

**Swagger Docs:** https://minimalminds.onrender.com/docs

**Health Check:** https://minimalminds.onrender.com/health

---

## Features

* LLM-powered interpretation of natural language operator notes
* Deterministic guardrails for validation
* Cost-optimized 24-hour energy scheduling using PuLP
* FastAPI REST API with OpenAPI/Swagger documentation
* Docker & Render deployment ready
* Public sample validation script included

---

## Project Structure

```text
minimalminds/
│
├── app/
│   ├── main.py
│   ├── routes.py
│   ├── models.py
│   ├── llm.py
│   ├── guardrails.py
│   ├── optimizer.py
│   └── config.py
│
├── scripts/
│   └── check_samples.py
│
├── tests/
├── Dockerfile
├── requirements.txt
├── .env.example
├── render.yaml
└── README.md
```

---

## Run Locally

### Requirements

* Python 3.11+
* Gemini API Key

### Installation

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Configure your Gemini credentials:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

Start the server:

```bash
uvicorn app.main:app --reload
```

Local API:

* http://localhost:8000
* http://localhost:8000/docs

---

## API Endpoints

### Health Check

```http
GET /health
```

Example:

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "ok"
}
```

### Optimize Energy

```http
POST /optimize-energy
```

Example:

```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  --data @scenario.json
```

The request must contain:

* `scenario_id`
* `operator_notes` (1–3 notes)
* `hours` (exactly 24 hourly entries)
* `battery` configuration

---

## Test the Live API

You can test the deployed API directly without running locally.

Open:

**https://minimalminds.onrender.com/docs**

1. Expand **POST /optimize-energy**
2. Click **Try it out**
3. Paste a sample scenario JSON
4. Click **Execute**

A successful response includes:

```json
{
  "scenario_id": "...",
  "directive_interpretation": [...],
  "hourly_plan": [...],
  "total_cost_bdt": 0,
  "peak_grid_kwh": 0,
  "plan_summary": "..."
}
```

---

## Public Sample Validation

Run all organizer public sample cases against either the local server or the deployed Render API.

### Local

```bash
python scripts/check_samples.py public_samples.json \
  --base-url http://localhost:8000
```

### Render

```bash
python scripts/check_samples.py public_samples.json \
  --base-url https://minimalminds.onrender.com
```

Expected output:

```text
SAMPLE-01 PASS
SAMPLE-02 PASS
...
SAMPLE-10 PASS
```

---

## Architecture

```text
Operator Notes
       │
       ▼
 Gemini 2.5 Flash
       │
       ▼
 Deterministic Guardrails
       │
       ▼
 PuLP/CBC Optimizer
       │
       ▼
 Validated 24-Hour Energy Plan
```

### Design Principles

* Gemini interprets **only** natural-language operator notes.
* The optimizer never trusts raw LLM output directly.
* Guardrails validate directive types, hours, factors, and numeric values.
* Every response is replayed deterministically before being returned.
* Missing or invalid Gemini credentials cause the request to fail safely.

---

## Docker

Build:

```bash
docker build -t gridwise:2026 .
```

Run:

```bash
docker run --rm \
  -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  gridwise:2026
```

---

## Deploy on Render

1. Create a **New Web Service**
2. Connect this GitHub repository
3. Select **Docker**
4. Add the environment variable:

```text
GEMINI_API_KEY=your_gemini_api_key
```

Render automatically builds the Docker image and deploys the API.

**Live URL:** https://minimalminds.onrender.com/

---

## Environment Variables

| Variable         | Required | Description                     |
| ---------------- | -------- | ------------------------------- |
| `GEMINI_API_KEY` | Yes      | Gemini API credential           |
| `GEMINI_MODEL`   | No       | Default: `gemini-2.5-flash`     |
| `CORS_ORIGINS`   | No       | Comma-separated allowed origins |

> Never commit `.env` or API keys to the repository.

---

## License

Developed for **BUP CSE Fest 2026 Hackathon – GridWise LLM Energy Optimization Challenge**.
