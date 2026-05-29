# LockStream

A small event-sourced service for tracking parcel locker state. Lockers send in events (a
compartment getting registered, a reservation, a deposit, a pickup, an expiry, faults), and the
service validates them, keeps a derived view of the world, and answers queries over HTTP. The
contract in [`openapi.yaml`](openapi.yaml) is the source of truth.

## Requirements

Python 3.11 or newer.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

If you only want to run the API and not the tests, `pip install -e .` is enough.

## Running it

```bash
uvicorn lockstream.main:create_app --factory --reload
```

The event log is written to `data/events.jsonl` by default. Set `LOCKSTREAM_EVENT_LOG` to put it
elsewhere. The in-memory view is rebuilt from that file on startup, so state survives a restart.
Swagger UI is at <http://127.0.0.1:8000/docs>.

Set `LOG_LEVEL=DEBUG` to watch each event get applied, rejected, or deduped end-to-end (the trace is
scoped to the app's own loggers, so there's no third-party noise):

```bash
LOG_LEVEL=DEBUG uvicorn lockstream.main:create_app --factory
```

Quick check once it's up:

```bash
curl -i -X POST localhost:8000/events -H 'content-type: application/json' -d '{
  "event_id":"11111111-1111-1111-1111-111111111111","occurred_at":"2026-05-27T10:00:00Z",
  "locker_id":"L1","type":"CompartmentRegistered","payload":{"compartment_id":"C1"}}'

curl -s localhost:8000/lockers/L1
curl -s localhost:8000/lockers/L1/compartments/C1
```

## Tests

```bash
pytest
```

Covers the five areas the brief asks for: OpenAPI contract tests (bad requests rejected with 422,
good responses validated against the spec), idempotency, invalid state transitions, fault degradation
and clearing, and projection equivalence (incremental apply == full rebuild).

To run just the OpenAPI contract tests (the ones that load `openapi.yaml` and validate against it):

```bash
./.venv/bin/pytest tests/test_contract_openapi.py -v
```

## How it's laid out

Clean-ish layering where the dependencies all point inward (`api -> application -> domain`), and
infrastructure plugs into an application interface.

```text
lockstream/
  main.py            create_app() factory + the LOG_LEVEL switch
  domain/            business logic, no framework imports
    models.py        enums + the in-memory aggregates
    events.py        typed events + the factory that builds/validates them
    projection.py    the read model: apply/rebuild, queries, state_hash
    errors.py        the two error types (-> 422 / 409)
  application/
    ports.py         EventStore interface
    service.py       LockStreamService - the facade the API calls
  infrastructure/
    event_store.py   JSONL-backed store with idempotent appends
  api/
    schemas.py       pydantic models for the requests/responses
    routes.py        the routes + the only place errors become status codes
    dependencies.py  DI wiring
```

A few notes on the design:

- The `payload` in the `Event` schema is an open object, so the actual shape of each event is
  inferred from the rules in the brief and validated in `events.py`. The reasoning (and the spec
  issues I ran into) is in [`DECISIONS.md`](DECISIONS.md).
- The JSONL file is the source of truth; the projection is a cache I can rebuild any time. Building it
  event-by-event gives the same `state_hash` as a full rebuild.
- Lookups are dict-based (O(1)), a rebuild is O(N), and duplicate detection uses an in-memory set of
  seen ids primed from the file, so it doesn't re-read the log on every request.
- Patterns in play: **Repository** (the store behind an interface), a **Factory** for events, the
  **service as a Facade**, and ingest handled as a **Command**. I skipped SQLAlchemy on purpose - for
  in-memory state plus a JSONL log it would have been overhead with no payoff.
