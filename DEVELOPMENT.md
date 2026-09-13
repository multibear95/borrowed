# MORE — development guide

**More to wear. More to give. More to share.**

MORE is a hackathon prototype for a peer-to-peer occasion-wear rental platform.
It helps people find an outfit for a specific event through a natural-language
conversation, with availability and delivery timing checked before a garment is
recommended.

Built for the AI.WOMEN Hackathon in Hamburg, 12–13 September 2026. The product
story lives in [README.md](README.md); this document is for people running or
changing the code.

---

## Contents

- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Run locally](#run-locally)
- [Environment variables](#environment-variables)
- [Quality checks](#quality-checks)
- [How the borrower flow works](#how-the-borrower-flow-works)
- [The role of AI](#the-role-of-ai)
- [Implementation status](#implementation-status)
- [Technology](#technology)
- [Further reading](#further-reading)

---

## Repository layout

```text
frontend/                         Next.js 15 + React 19 + TypeScript
  app/find/                       borrower chat route
  components/chat/                chat stream, question cards, composer
  components/cards/               results and reservation UI
  lib/api.ts                      API origin and typed requests

backend/
  src/borrowed_backend/agents/    slot extraction and response composition
  src/borrowed_backend/domain/    dates, availability, ranking and models
  src/borrowed_backend/tools/     catalogue search and booking tools
  src/borrowed_backend/api/       FastAPI routes and SSE conversations
  data/catalog.json               386-item seed catalogue
  tests/                          backend tests

docs/                             documentation index and deployment guides
specs/                            product and backend specifications
assets/                           logo and README screenshots
```

The backend is designed for a **single instance with one worker**. It is a
hackathon prototype: no database, no multi-process coordination. Do not start
several processes against the same state directory.

## Requirements

- Node.js 20+
- Python 3.12

## Run locally

### 1. Backend (FastAPI)

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt

# Required for live AI conversations
export OPENAI_API_KEY="..."
export OPENAI_MODEL="..."

PYTHONPATH=src .venv/bin/python -m borrowed_backend --demo-date 2026-09-16
```

The API and interactive documentation are then available at
`http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`.

### 2. Frontend (Next.js)

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
# For local backend development, set API_ORIGIN=http://127.0.0.1:8000 in .env.local
npm install
npm run dev
```

Open `http://localhost:3000/find`.

## Environment variables

| Variable | Side | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | backend | credentials for live conversations |
| `OPENAI_MODEL` | backend | model used by the Responses API |
| `DEMO_DATE` | backend | freezes "today" for the demo (CLI `--demo-date` wins) |
| `CATALOG_PATH` | backend | catalogue JSON location |
| `STATE_DIR` | backend | reservation and conversation snapshots |
| `IMAGES_DIR` | backend | catalogue images |
| `API_ORIGIN` | frontend | FastAPI origin, **server-side only** |

`API_ORIGIN` is never exposed to the browser. Next.js proxies `/api` and
`/images`, so the browser stays on one origin and needs no public API variable.
In Railway, set `API_ORIGIN` to the deployed FastAPI URL. The frontend also has
a production fallback of `https://borrowed-production-58eb.up.railway.app`.

Model credentials belong on the backend only. Reservations survive a redeploy
only with a backend volume mounted at `STATE_DIR`.

## Quality checks

```bash
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m pytest
```

## How the borrower flow works

1. **Describe the occasion.** The borrower explains what they need in everyday
   language.
2. **Clarify the essentials.** The assistant asks only for what is still
   missing — wear date, city, EU size, optionally the event type.
3. **Explore feasible options.** The backend checks eligibility and
   availability, then ranks suitable garments by preferences such as colour,
   occasion and style.
4. **Confirm a reservation.** The borrower explicitly confirms one option. The
   backend re-checks availability and creates a reservation hold. No payment is
   taken.

The availability calculation accounts for outbound delivery, the wear period,
return transit, cleaning and existing bookings. The event deadline is therefore
part of the search itself, not a warning shown afterwards.

Conversation state is kept while the session is open. A new conversation creates
a fresh backend conversation and appears in the sidebar only after its first
message. Refreshing the page does not restore the full chat transcript, but
reservations remain stored in the backend.

## The role of AI

AI interprets the borrower's request and carries the conversation.
Deterministic Python code checks availability, ranks results and controls
reservation creation.

| The model does | Deterministic backend code does |
| --- | --- |
| Extracts explicitly stated details from the borrower message | Checks size, city and date feasibility |
| Identifies missing information and writes a short question | Computes shipping, return and cleaning windows |
| Interprets an optional event or colour preference | Rejects garments with conflicting bookings or insufficient delivery time |
| Summarises the recommendations in English | Returns the exact cards shown in the interface |

The conversation runs on the **OpenAI Responses API**, with **LangGraph**
coordinating the borrower workflow. Availability answers never come from the
model.

## Implementation status

Implemented:

- authless MCP at `/mcp`, sharing the four existing tools and store; see [MCP demo setup](backend/docs/mcp-demo-zh.md)

- structured garment search with availability and lead-time rules
- text conversation over server-sent events
- borrower web interface (`/find`)
- explicit booking confirmation and persistent reservation holds
- JSON snapshots, so runtime bookings survive a restart with the same
  `STATE_DIR`

Not implemented (out of hackathon scope):

- accounts, payments, identity verification, insurance, courier integration
- booking cancellation
- lender listing creation, image understanding, styling assistance, model
  re-ranking and relaxed-condition search

Lender-facing routes and catalogue-building tools remain in the repository but
are not the active demo flow.

## Technology

| Area | Current implementation |
| --- | --- |
| Frontend | Next.js 15, React 19, TypeScript |
| Backend | Python 3.12+, FastAPI, Pydantic v2 |
| Conversation | OpenAI Responses API, LangGraph, server-sent events |
| Search and availability | Python domain rules |
| Storage | catalogue JSON, in-memory state, JSON booking snapshots |
| Hosting | Railway |

## Catalogue data

The 386-item demo catalogue (250 dresses, 136 accessories) is based on public
data from [DCEY](https://www.davetcokelbisemyok.com). Images belong to DCEY and
are used for hackathon demonstration only. Rental prices, availability, delivery
lead times, bookings and lender details are demo data modelled by the team. See
[DATA.md](DATA.md) for the source, pipeline and known gaps.

## Further reading

- [Product story and vision](README.md)
- [Architecture](ARCHITECTURE.md) · [full product spec](SPEC.md)
- [Frontend spec](specs/FRONTEND_SPEC.md) · [backend spec](specs/BACKEND_SPEC.md)
- [Backend setup and API reference](backend/README.md)
- [Documentation index](docs/README.md)
- [Backend deployment guide](docs/backend-railway.readme.md)
- [Frontend deployment guide](docs/frontend-railway.readme.md)
