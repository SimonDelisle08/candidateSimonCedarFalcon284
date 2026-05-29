# Decisions & trade-offs

Just jotting down the calls I made and the things I noticed in the spec, so it's clear why the
code looks the way it does. Filled in as I went.

## Reading the OpenAPI spec

The brief says the contract is the boss and drops a hint that it might have mistakes, so I read it
slowly and left `openapi.yaml` exactly as given. A few things jumped out:

- **That `nullable: true` is a bit off.** It's on `CompartmentStatus.active_reservation`, but the
  doc says `openapi: 3.1.0`, and 3.1 is JSON Schema 2020-12 - which doesn't use `nullable` anymore
  (you're meant to write `type: ["string", "null"]`). I didn't touch the spec. The API still returns
  `active_reservation: null` for a free compartment, and in the tests I quietly rewrite `nullable`
  into a real null-union before validating, so I'm checking against a schema that actually works.
  That's `_normalize_nullable` in `tests/conftest.py`.
- **The payload is wide open.** `Event.payload` is just `additionalProperties: true`, but the rules
  obviously need real fields in there. So I worked out a shape per event type and check it in one
  spot (`event_from_dict`). Table's below.
- **The GETs only list `200`.** No 404 anywhere. Making up an empty body for an id that doesn't exist
  felt wrong, so I return `404` instead - noting it here since it's technically not in the contract.
- **POST /events has no response body.** The four responses are just status codes, so the endpoint
  returns nothing and leans on the code (202 / 200 / 409 / 422).

## Inferred payload shapes

| type                  | payload                            |
| --------------------- | ---------------------------------- |
| CompartmentRegistered | `compartment_id`                   |
| ReservationCreated    | `reservation_id`, `compartment_id` |
| ParcelDeposited       | `reservation_id`                   |
| ParcelPickedUp        | `reservation_id`                   |
| ReservationExpired    | `reservation_id`                   |
| FaultReported         | `compartment_id`, `severity`       |
| FaultCleared          | `compartment_id`, `fault_event_id` |

A fault is just the `FaultReported` event that opened it - so `FaultCleared` points back at that
event's id via `fault_event_id`. I didn't invent a separate "fault id"; the contract doesn't have
one, so neither do I. Clearing checks the fault actually exists on that same compartment and hasn't
already been cleared.

## 422 vs 409

The contract has both, so I needed a clear line between them. Mine is simple: **422 = the event is
wrong by itself, 409 = the event is fine but clashes with what's already happened.**

- 422: you can tell it's broken without looking at anything else - dodgy envelope (bad uuid, bad
  date, unknown type, payload that isn't an object), or a payload missing a field that type needs.
- 409: the event is well-formed, it just breaks a rule given the history - depositing before there's
  a reservation, reserving a degraded or already-taken compartment, picking up after expiry, clearing
  a fault that isn't there, that sort of thing.

This lines up with the brief: the "must reference an existing X" rules live under *domain rules*, so
pointing at something that doesn't exist is a 409, not a 422.

## No SQLAlchemy

It's optional, and honestly it would've just been in the way. The storage ask is already "in-memory
state + an append-only JSONL file", so bolting an ORM on top buys nothing here (and that's why
there's no Unit of Work either). The brief wants at least two patterns - there are four anyway:
**Repository** (the store sits behind an interface), **Factory** (`event_from_dict`), **Command**
(each event is handled by `ingest`), and **Facade** (`LockStreamService` is the one door the API
knocks on).

## Ingest order

`ingest` goes: check if we've seen the id (yep -> 200), validate the payload (bad -> 422), run the
rules (broken -> 409), then write it down. Every rule check happens *before* anything changes, so a
rejected event leaves the projection exactly as it was - no rollback needed - and I only append to
the log once the event is fully in.

There's a tiny gap where the in-memory update lands but the disk write fails. In a real system I'd
close that with a write-ahead/outbox thing, but for one local file in one process I kept it simple.

Worth calling out: because the id check comes first, re-sending a known id gives you a 200 even if
the second copy has a totally different (or junk) payload. That's on purpose - the first accepted
write wins, and "same id, same outcome" is the whole point of idempotency.

## Idempotency across restarts

It's keyed on `event_id`. The store keeps a set of ids it's seen for instant lookups, but that set
gets rebuilt from the JSONL file when the store starts up - so after a restart an old id is still
recognised and comes back 200 without being re-applied. On boot, `bootstrap()` just replays the whole
log into a fresh projection. Ids get normalised too: pydantic parses the uuid and writes it back in
canonical form, so the same uuid in different casing still dedupes.

## Event ordering

What matters is the order things were appended, not `occurred_at` (I treat that as a label). A
rebuild reads the file top to bottom - the same order things happened live - so the rebuilt view
always matches the live one.

## state_hash

It's a SHA-256 of a tidied-up JSON snapshot of one locker: compartments and reservations sorted by
id, faults sorted by id, keys in a fixed order. Since it only depends on the state itself and not on
what order events arrived, a projection built event-by-event hashes the same as one rebuilt from
scratch - which is exactly the equivalence the tests check.

## Degradation

A compartment is degraded if it's got an uncleared fault of severity 3 or higher
(`DEGRADED_SEVERITY_THRESHOLD`). That blocks new reservations but leaves any parcel already inside
alone - matching "faults affect availability, not parcel state". `severity` only has to be an integer;
the spec never says it must be positive, so I don't add a rule that isn't there (a negative severity
is just below the threshold). I do reject `bool` though, since it sneaks in as an `int` subclass.

## Error -> HTTP mapping

The domain throws `PayloadValidationError` / `DomainRuleViolation` and never imports FastAPI.
`api/routes.py` is the single place those become 422 / 409, plus a 404 when a lookup comes back
empty. Keeps the rules trivial to test on their own.

## Test-only dependencies

To validate against the real `openapi.yaml` I load it with PyYAML and check responses with a JSON
Schema 2020-12 validator (jsonschema). Both live under the `test` extra only - the runtime just needs
FastAPI, uvicorn, and pydantic.

## Logging

The domain, store, and service drop `logger.debug` lines at the spots worth watching (each event
applied or rejected, idempotency skips, rebuild counts). They're off by default and scoped to the
`lockstream` loggers, so flipping `LOG_LEVEL=DEBUG` lets you follow a request end to end without
drowning in third-party chatter.
