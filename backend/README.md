# borrowed backend — Stages 1–2

MCP demo is now available at `/mcp`: four shared tools over authless Streamable HTTP. See [Cursor / ChatGPT / Claude setup](docs/mcp-demo-zh.md). MCP tool calls do not need OpenAI credentials.

Structured search → submit booking → immediate hold → survive restart. Python 3.12, FastAPI, Pydantic v2, single-process in-memory dict with JSON snapshots.

Stage 2 adds the OpenAI borrower conversation API. See [Stage 2 setup and API flow](docs/stage2-usage.md) and [中文说明](docs/stage2-usage-zh.md). Configure `OPENAI_API_KEY` and `OPENAI_MODEL` for live conversations.

## Install & run

```bash
cd borrowed/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
PYTHONPATH=src .venv/bin/python -m borrowed_backend --demo-date 2026-09-16
```

```bash
conda create -n env_borrowed python=3.12 -y
conda activate env_borrowed
python -m pip install -r requirements.lock.txt
PYTHONPATH=src python -m borrowed_backend --demo-date 2026-09-16
```

`requirements.lock.txt` pins the runtime and test dependencies verified for this milestone. You can also install the Python package with `.venv/bin/python -m pip install -e '.[test]'`, then run `.venv/bin/borrowed-backend --demo-date 2026-09-16`.

The server listens on `127.0.0.1:8000` by default. Interactive API docs: `http://127.0.0.1:8000/docs`. The CLI accepts `--host`, `--port`, and `--demo-date`; the CLI date takes precedence over the `DEMO_DATE` environment variable. If no date is provided, the current system date is used.

Keep **one server instance and one worker**. The CLI hard-codes `workers=1`, and the Procfile also pins `--workers 1`. Do not start multiple processes that share the same state directory. Equivalent uvicorn command:

```bash
DEMO_DATE=2026-09-16 .venv/bin/python -m uvicorn borrowed_backend.main:create_app --factory --app-dir src --host 127.0.0.1 --port 8000 --workers 1
```

Configurable env vars: `DEMO_DATE`, `CATALOG_PATH`, `STATE_DIR`, `IMAGES_DIR`. Default paths are resolved relative to the backend directory, independent of the process working directory. For non-editable installs, set external catalog, image, and state directories explicitly.

## Fixed demo

Check health and all candidate garments first:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/garments/search \
  -H 'Content-Type: application/json' \
  -d '{"city":"Hamburg","sizes_eu":[38],"wear_date":"2026-09-18","limit":1000}'
```

The script below picks the first garment from search results and books it, printing the request and response. Running it again picks the next garment and creates another booking. Booking only holds the garment; no payment is taken.

```bash
.venv/bin/python - <<'PY'
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as client:
    search = {"city": "Hamburg", "sizes_eu": [38], "wear_date": "2026-09-18"}
    response = client.post("/api/garments/search", json=search)
    response.raise_for_status()
    hits = response.json()
    if not hits:
        raise SystemExit("No feasible garments remain for this demo.")
    garment_id = hits[0]["garment"]["id"]
    booking = {**search, "garment_id": garment_id, "idempotency_key": f"demo-{garment_id}"}
    print("Request:", booking)
    response = client.post("/api/bookings", json=booking)
    response.raise_for_status()
    print("Booking:", response.json())
    response = client.post("/api/bookings", json=booking)
    response.raise_for_status()
    print("Retry:", response.json())
PY
```

A subsequent search no longer returns that garment. After stopping the server and restarting with the same date and state directory, the hold remains. For a clean demo, stop the server and start with a new `STATE_DIR`; no need to change the seed catalog.

## API contract

| Endpoint | Request & response |
| --- | --- |
| `GET /health` | `status`, `garments`, `bookings` (seed + runtime total), `today` |
| `POST /api/garments/search` | Required city and wear date; sizes array defaults to empty; returns `SearchHit[]`, default max 20, `limit` is 1–1000 |
| `GET /api/garments/{id}` | Public garment projection; excludes source links and booking internals |
| `GET /api/garments/{id}/availability` | `wear=2026-09-18&return=2026-09-21&city=Hamburg&sizes_eu=38`; repeat `sizes_eu` for multiple sizes |
| `POST /api/bookings` | Required `garment_id`, `wear_date`, `city`, `sizes_eu`, `idempotency_key`; optional `return_date`, `borrower_name` |
| `GET /images/{filename}` | Existing local images |

Search also supports `category` (default dress), `occasion`, `colour_family`, `style_hints`, `max_price`. Missing or mismatched dress sizes yield no borrowable hits; accessories skip size checks. Colour, occasion, style, and formality affect scoring only; unknown colours do not exclude garments.

`return_date` is the **last wear day (inclusive)**, not a return delivery date. When omitted, the garment rental period is used (4 days in the current seed). One extra buffer day before outbound shipping; return transit and cleaning continue to hold the garment. Two hold intervals that touch on the same day still conflict. Cleaning-period reasons follow the spec: from after an existing wear window ends through the end of the hold.

A successful booking returns `BookingResult` with dates, `status: reserved`, `payment_taken: false`, and `already_existed`. The same idempotency key with an equivalent request returns the original booking and remains valid across restarts. City is case-insensitive; sizes are deduped and sorted; omitting the end date is treated as equivalent to explicitly filling the default end date. Any other request change returns 409 `IDEMPOTENCY_KEY_REUSED`.

Other errors: 422 for invalid requests, 404 `GARMENT_NOT_FOUND`, 409 for availability conflicts (top-level `reason`, `feasibility`), 503 `PERSISTENCE_FAILED`. A failed booking must not look like success; keep the idempotency key and retry.

## Storage & boundaries

- Catalog is read-only; runtime bookings are saved to `data/state/bookings.json`, version 1, including bookings and the structured request used for idempotency comparison.
- Each booking re-checks under a lock, updates memory, and saves atomically; on write failure, memory is restored. Corrupt, inconsistent, or duplicate snapshot records fail startup — inspect and restore from backup; do not silently wipe state.
- Local development and Hackathon single-instance only. This stage has no auth, payment, booking cancellation, database, multi-process coordination, or cross-machine persistence.
- Stage 2 conversation APIs are implemented. Stage 3 UI pages, MCP, lender flows, listing, styling, model reranking and image processing remain out of scope.
- Code comments and docstrings are in English.

## Acceptance vs spec drift

Clean state, demo date 2026-09-16, wear date 2026-09-18, Hamburg, EU 38, dress:

| Result | Count |
| --- | ---: |
| Borrowable | 22 |
| City mismatch | 66 |
| Size mismatch | 69 |
| Ships too late | 72 |
| Booking conflict | 21 |

Total: 250 dresses; plus 136 accessories. The original BACKEND_SPEC / ARCHITECTURE cited 24 borrowable and 19 booking conflicts, which no longer match the current seed after booked wear-window expansion. This round confirms **22 / 21**; keep data and rules unchanged. Default `limit=20`; raise the limit explicitly when verifying totals.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_stage1.py
```

The smoke script uses a temporary state directory, starts a real HTTP server, issues 20 concurrent bookings, shuts down and restarts the process, then verifies search and idempotent recovery. On exit it stops the server and cleans up temp state. Actual results: `docs/stage1-acceptance-zh.md`.

Stage 2 verification: [阶段 2 验收记录](docs/stage2-acceptance-zh.md).

Stage 3 connects the existing Next.js borrower page to this backend. See [browser demo instructions](docs/stage3-usage-zh.md) for local setup, explicit confirmation, and two-tab conflict verification.
