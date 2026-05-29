from fastapi.testclient import TestClient

from lockstream.main import create_app

E_REGISTER = "11111111-1111-1111-1111-111111111111"
E_RESERVE = "22222222-2222-2222-2222-222222222222"


def test_resending_same_event_id_returns_200_and_keeps_state(client, make_event):
    register = make_event("CompartmentRegistered", {"compartment_id": "C1"}, event_id=E_REGISTER)
    reserve = make_event("ReservationCreated", {"reservation_id": "R1", "compartment_id": "C1"}, event_id=E_RESERVE)
    assert client.post("/events", json=register).status_code == 202
    assert client.post("/events", json=reserve).status_code == 202

    before = client.get("/lockers/L1").json()["state_hash"]
    assert client.post("/events", json=reserve).status_code == 200  # same event_id -> duplicate
    after = client.get("/lockers/L1").json()["state_hash"]
    assert before == after


def test_reused_event_id_with_garbage_payload_is_a_noop(client, make_event):
    register = make_event("CompartmentRegistered", {"compartment_id": "C1"}, event_id=E_REGISTER)
    assert client.post("/events", json=register).status_code == 202
    before = client.get("/lockers/L1").json()["state_hash"]

    # same event_id, payload that would be a 422 if validated -> proves dedupe runs before validation
    clash = make_event("ParcelDeposited", {}, event_id=E_REGISTER)
    assert client.post("/events", json=clash).status_code == 200
    assert client.get("/lockers/L1").json()["state_hash"] == before


def test_idempotency_survives_a_restart(client, make_event):
    register = make_event("CompartmentRegistered", {"compartment_id": "C1"}, event_id=E_REGISTER)
    assert client.post("/events", json=register).status_code == 202

    # a brand-new app over the same log file (env still points there) must still recognise the event_id
    restarted = TestClient(create_app())
    assert restarted.post("/events", json=register).status_code == 200
    assert restarted.get("/lockers/L1").json()["state_hash"] == client.get("/lockers/L1").json()["state_hash"]
