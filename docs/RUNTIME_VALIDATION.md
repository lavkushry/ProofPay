# Runtime foundation validation

Date: 2 October 2026. This report covers the first M0 slice; it does not establish full MVP acceptance.

| Check | Observed result |
| --- | --- |
| Regression suite, local Python 3.14.4 | 22 passed |
| Regression suite, deployment Python 3.11 image | 22 passed with a read-only source mount and network disabled |
| Python syntax | `compileall` passed for backend, fixture, runner and scripts |
| Frontend TypeScript/production build | Passed with Vite 8.3.2 and React plugin 6.1.1 |
| npm dependency audit | Zero reported vulnerabilities |
| Fresh PostgreSQL 17 initialization | SQL scaffold executed after restoring the documented composite obligation key |
| Compose HTTP smoke | Database ready, actual seeded owner visible, nginx `/api` proxy and SPA fallback working, both fixture pages served, delivery submission held with 503 |
| Pinned Playwright 1.63 / Chromium browser | UI rendered, compile returned 503 with visible feedback; measured broken scroll width 544px and corrected width 320px at a 320px viewport |
| API inventory | 55 contract operations tracked; route/schema/authorization conformance remains pending |

Regression tests exercise missing executor credentials across all six operations, denial of live/untrusted hosts and custom endpoint paths, preservation of provider errors, mutation holds, absence of delivery/payment/budget writes, readiness error redaction, and repeatable seeding that preserves actors/balances. Test transports are explicitly local simulations.

The local ASGI test-client hang reproduced inside the filesystem/network sandbox and disappeared with the same suite outside it. All 22 tests also passed on the actual Python 3.11 image. Initial Compose checks exposed a missing SQL composite unique key and host-port conflicts; the code now restores the key from `05-DATA_MODEL.md` and supports configurable localhost ports.

The isolated smoke project used web port 13000, API 18000, fixture 18080 and database 15432 so existing workspace services were preserved. CI uses a fresh runner with default ports. Provider credentials were not supplied to the API or used in these checks.

Browser captures: [preview](screenshots/runtime-preview.png), [workflow hold](screenshots/workflow-hold.png), [broken fixture](screenshots/fixture-broken.png), [corrected fixture](screenshots/fixture-fixed.png), and [measured dimensions](screenshots/fixture-observations.json). These local validation artifacts are separate from payment-authorizing database evidence. The actual broken fixture's measured 544px must not be replaced with the prototype's canned 480px observation.

Reproduce browser checks by building `docker build -t proofpay-runner-check runner`, then running `scripts/browser_smoke.py` in that image on the Compose network with a read-only source mount and writable screenshot directory. Its default targets are the `web` and `fixture` service names. The isolated build also verified that the browser image matches the pinned Python Playwright package.

Still pending: actual inference and image grounding, stored verification evidence, executor-worker credential grants, financial concurrency/dispatch/reconciliation, real sandbox settlement/signature/cancellation records, hosted runner access, and the full EV01–EV16 evidence register. `/readyz` reports infrastructure database readiness and explicitly reports the workflow unavailable.
