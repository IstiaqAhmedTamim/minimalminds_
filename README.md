# GridWise

GridWise is a FastAPI backend for optimization-driven grid planning workflows.

## Stack

- Python 3.12
- FastAPI
- Pydantic
- OR-Tools
- OpenAI SDK
- Uvicorn

## Project Structure

- `app/main.py`: FastAPI application factory and startup wiring.
- `app/routes.py`: HTTP routes.
- `app/models.py`: Pydantic request and response models.
- `app/optimizer.py`: OR-Tools-based optimization service.
- `app/llm.py`: OpenAI SDK integration.
- `app/guardrails.py`: Input validation and policy checks.
- `app/config.py`: Environment configuration.

## Setup

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and configure your values.

## Run

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the Swagger UI.

## Docker

Build and run the container:

```bash
docker build -t gridwise .
docker run -p 8000:8000 --env-file .env gridwise
```
# minimalminds_