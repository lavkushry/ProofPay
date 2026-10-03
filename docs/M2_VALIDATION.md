# M2 compilation validation

M2 adds an immutable fixture contract, owner-scoped brief revisions and a durable
structured-output compiler. The checked-in contract contains six hashed artifacts:
broken and corrected variants for responsive CSS, API endpoint, and keyboard
accessibility families. The API stores the manifest and artifact rows per agency;
seed verification rejects a changed digest instead of rewriting history.

`POST /api/briefs/{brief_id}/compile` verifies the current revision digest, writes a
`compilations` row and `compile_requested` outbox job in one transaction, and returns
`202`. The worker validates the persisted manifest, calls the configured provider,
persists an immutable `ai_interactions` row, and completes the compilation only after
the lease fence still belongs to it. A proposal is ready only when it contains the
three catalog templates in order, exact manifest parameters, `compiled_by="ai"`, and
`approved=false`; unsupported or ambiguous output is held as `ambiguous`.

The adapter supports `openai`, `gemini`, and `openrouter` through server-side keys.
It uses structured JSON output, a 45-second deadline, no hidden SDK retries, and
fails closed as `MODEL_UNAVAILABLE` when a provider or credential is absent. Provider
responses are parsed with duplicate-key and non-finite-number rejection; raw response
bodies and credentials are never included in errors or logs.

Validation from the repository root:

```sh
.venv/bin/python -m pytest -q
PROOFPAY_TEST_DATABASE_URL=postgresql://ADMIN:PASSWORD@HOST/DB .venv/bin/python -m pytest -q -m postgres
.venv/bin/python scripts/fixture_manifest.py
```

The PostgreSQL suite includes capture, idempotent compile enqueueing, worker
completion, interaction lineage and owner-scoped compilation reads. Real provider
access remains an environment-dependent deployment check; tests use an explicit
HTTP transport double and never claim external model execution.
