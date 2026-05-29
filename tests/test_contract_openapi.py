from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

# read required fields straight from the spec so the 422 cases are driven by the contract, not hardcoded
_SPEC = yaml.safe_load((Path(__file__).resolve().parent.parent / "openapi.yaml").read_text())
_EVENT_REQUIRED = _SPEC["components"]["schemas"]["Event"]["required"]


def _validate(schema, instance):
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=str)
    assert not errors, errors


@pytest.mark.parametrize("field", _EVENT_REQUIRED)
def test_missing_required_field_is_422(client, make_event, field):
    event = make_event("CompartmentRegistered", {"compartment_id": "C1"})
    del event[field]
    assert client.post("/events", json=event).status_code == 422


def test_unknown_event_type_is_422(client, make_event):
    assert client.post("/events", json=make_event("Teleported", {})).status_code == 422


def test_non_uuid_event_id_is_422(client, make_event):
    event = make_event("CompartmentRegistered", {"compartment_id": "C1"}, event_id="not-a-uuid")
    assert client.post("/events", json=event).status_code == 422


def test_non_object_payload_is_422(client, make_event):
    event = make_event("CompartmentRegistered", {"compartment_id": "C1"})
    event["payload"] = "not-an-object"
    assert client.post("/events", json=event).status_code == 422


def test_payload_missing_a_typed_field_is_422(client, make_event):
    # envelope is fine, but ReservationCreated needs compartment_id - our factory enforces that
    assert client.post("/events", json=make_event("ReservationCreated", {"reservation_id": "R1"})).status_code == 422


def test_locker_summary_matches_schema(client, make_event, openapi_schemas):
    client.post("/events", json=make_event("CompartmentRegistered", {"compartment_id": "C1"}))
    _validate(openapi_schemas["LockerSummary"], client.get("/lockers/L1").json())


def test_compartment_status_with_reservation_matches_schema(client, make_event, openapi_schemas):
    client.post("/events", json=make_event("CompartmentRegistered", {"compartment_id": "C1"}))
    client.post("/events", json=make_event("ReservationCreated", {"reservation_id": "R1", "compartment_id": "C1"}))
    body = client.get("/lockers/L1/compartments/C1").json()
    assert body["active_reservation"] == "R1"
    _validate(openapi_schemas["CompartmentStatus"], body)


def test_compartment_status_with_null_reservation_matches_schema(client, make_event, openapi_schemas):
    client.post("/events", json=make_event("CompartmentRegistered", {"compartment_id": "C1"}))
    body = client.get("/lockers/L1/compartments/C1").json()
    assert body["active_reservation"] is None  # the case the nullable shim exists for
    _validate(openapi_schemas["CompartmentStatus"], body)


def test_reservation_status_matches_schema(client, make_event, openapi_schemas):
    client.post("/events", json=make_event("CompartmentRegistered", {"compartment_id": "C1"}))
    client.post("/events", json=make_event("ReservationCreated", {"reservation_id": "R1", "compartment_id": "C1"}))
    _validate(openapi_schemas["ReservationStatus"], client.get("/reservations/R1").json())


def test_unknown_ids_return_404(client):
    assert client.get("/lockers/ZZZ").status_code == 404
    assert client.get("/lockers/L1/compartments/ZZZ").status_code == 404
    assert client.get("/reservations/ZZZ").status_code == 404
