from lockstream.application.service import LockStreamService
from lockstream.domain.events import event_from_dict
from lockstream.domain.projection import Projection
from lockstream.infrastructure.event_store import JsonlEventStore


def _id(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


# a multi-locker scenario touching every event type, including a fault that gets cleared
def _records() -> list[dict]:
    def rec(n, locker, event_type, payload):
        return {
            "event_id": _id(n),
            "occurred_at": "2026-05-28T10:00:00Z",
            "locker_id": locker,
            "type": event_type,
            "payload": payload,
        }

    return [
        rec(1, "L1", "CompartmentRegistered", {"compartment_id": "C1"}),
        rec(2, "L1", "CompartmentRegistered", {"compartment_id": "C2"}),
        rec(3, "L1", "ReservationCreated", {"reservation_id": "R1", "compartment_id": "C1"}),
        rec(4, "L1", "ParcelDeposited", {"reservation_id": "R1"}),
        rec(5, "L1", "FaultReported", {"compartment_id": "C2", "severity": 5}),
        rec(6, "L2", "CompartmentRegistered", {"compartment_id": "C9"}),
        rec(7, "L2", "ReservationCreated", {"reservation_id": "R9", "compartment_id": "C9"}),
        rec(8, "L2", "ParcelDeposited", {"reservation_id": "R9"}),
        rec(9, "L2", "ParcelPickedUp", {"reservation_id": "R9"}),
        rec(10, "L1", "FaultCleared", {"compartment_id": "C2", "fault_event_id": _id(5)}),
    ]


def test_incremental_apply_matches_full_rebuild():
    events = [event_from_dict(record) for record in _records()]
    incremental = Projection()
    for event in events:
        incremental.apply(event)
    rebuilt = Projection.rebuild(events)
    for locker in ("L1", "L2"):
        assert incremental.state_hash(locker) == rebuilt.state_hash(locker)


def test_live_run_matches_service_bootstrapped_from_log(client, event_log):
    for record in _records():
        assert client.post("/events", json=record).status_code == 202

    # rebuild a fresh service straight from the log file the API just wrote
    rebuilt = LockStreamService(JsonlEventStore(event_log))
    rebuilt.bootstrap()
    for locker in ("L1", "L2"):
        live = client.get(f"/lockers/{locker}").json()["state_hash"]
        assert rebuilt.locker_summary(locker)["state_hash"] == live
