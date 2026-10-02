# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/`: FastAPI routers, Pydantic schemas, SQLAlchemy models, configuration, and domain services; SQL lives in `backend/migrations/schema.sql`.
- `frontend/src/`: React/TypeScript UI and CSS; Vite configuration is in `frontend/`.
- `runner/`: verification worker scaffold; `fixture/`: controlled checkout HTML and API fixtures.
- Root `00`–`06` documents define requirements, architecture, API, data, and AI contracts. Read `00-PROJECT_CONTEXT.md` before scope changes and `04-API_SPEC.yaml` before API changes. Consult `IMPLEMENTATION_PLAN.md` for current gaps and milestone acceptance.
- No test directory exists yet. Place new backend tests in `backend/tests/` and keep fixture assets with `fixture/`.

## Build, Test, and Development Commands

Run from the repository root unless stated otherwise:

- `docker compose up --build`: builds and starts PostgreSQL, API, fixture, runner, and frontend. Existing startup defects are recorded in the implementation plan.
- `python -m pip install -r backend/requirements.txt -r fixture/requirements.txt`: installs API and fixture dependencies.
- `python -m uvicorn backend.app.main:app --reload --port 8000`: starts the development API.
- `python -m uvicorn fixture.app:app --port 8080`: starts the fixture after its documented syntax defect is repaired.
- In `frontend/`, run `npm install`, then `npm run dev` for development or `npm run build` for TypeScript checking and production output.
- `python -m pytest backend/tests`: runs backend tests once that directory is added.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Match the frontend's two-space indentation, `PascalCase` components, and `camelCase` functions/variables. Keep request validation in schemas and domain logic in services. TypeScript strict checking is enabled; no formatter or lint tool is configured.

## Testing Guidelines

Dependencies include pytest, pytest-asyncio, and Playwright; no suite or coverage threshold is established. Name Python tests `test_*.py`. Cover changed behavior, particularly authorization, immutable mandates, evidence grounding, and payout replay. Use PostgreSQL for locking/concurrency tests. Label simulations separately from actual model and sandbox evidence.

## Commit & Pull Request Guidelines

History contains one descriptive initial commit; no prefix convention is established. Use short imperative subjects. PRs should explain behavior, link relevant requirement IDs/issues, report validation and limitations, and include screenshots for UI changes.

## Security & Configuration

Configure secrets through environment variables using `.env.example`; keep credentials out of commits and logs. Use PayPal sandbox only and preserve executor-only financial credentials. Represent money as integer cents, retain approved snapshots, and preserve payment identity across retries.
