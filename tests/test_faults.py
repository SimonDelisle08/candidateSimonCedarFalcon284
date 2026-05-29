# a valid uuid we pin so FaultCleared can point back at this FaultReported
FAULT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _register(client, make_event, compartment="C1", locker="L1"):
    payload = {"compartment_id": compartment}
    return client.post("/events", json=make_event("CompartmentRegistered", payload, locker_id=locker))


def _report_fault(client, make_event, *, event_id, compartment="C1", severity=4, locker="L1"):
    payload = {"compartment_id": compartment, "severity": severity}
    return client.post("/events", json=make_event("FaultReported", payload, event_id=event_id, locker_id=locker))


def _clear_fault(client, make_event, *, fault_event_id, compartment="C1", locker="L1"):
    payload = {"compartment_id": compartment, "fault_event_id": fault_event_id}
    return client.post("/events", json=make_event("FaultCleared", payload, locker_id=locker))


def _reserve(client, make_event, reservation="R1", compartment="C1", locker="L1"):
    payload = {"reservation_id": reservation, "compartment_id": compartment}
    return client.post("/events", json=make_event("ReservationCreated", payload, locker_id=locker))


def test_fault_at_threshold_degrades_compartment(client, make_event):
    _register(client, make_event)
    assert _report_fault(client, make_event, event_id=FAULT_ID, severity=3).status_code == 202
    assert client.get("/lockers/L1/compartments/C1").json()["degraded"] is True


def test_fault_below_threshold_does_not_degrade(client, make_event):
    _register(client, make_event)
    _report_fault(client, make_event, event_id=FAULT_ID, severity=2)
    assert client.get("/lockers/L1/compartments/C1").json()["degraded"] is False


def test_degraded_compartment_blocks_new_reservation(client, make_event):
    _register(client, make_event)
    _report_fault(client, make_event, event_id=FAULT_ID, severity=4)
    assert _reserve(client, make_event).status_code == 409


def test_low_severity_fault_still_allows_reservation(client, make_event):
    _register(client, make_event)
    _report_fault(client, make_event, event_id=FAULT_ID, severity=1)
    assert _reserve(client, make_event).status_code == 202


def test_non_integer_severity_is_rejected(client, make_event):
    _register(client, make_event)
    assert _report_fault(client, make_event, event_id=FAULT_ID, severity="high").status_code == 422


def test_boolean_severity_is_rejected(client, make_event):
    _register(client, make_event)
    assert _report_fault(client, make_event, event_id=FAULT_ID, severity=True).status_code == 422


def test_clearing_unknown_fault_is_rejected(client, make_event):
    _register(client, make_event)
    assert _clear_fault(client, make_event, fault_event_id=FAULT_ID).status_code == 409


def test_clearing_an_already_cleared_fault_is_rejected(client, make_event):
    _register(client, make_event)
    _report_fault(client, make_event, event_id=FAULT_ID, severity=4)
    assert _clear_fault(client, make_event, fault_event_id=FAULT_ID).status_code == 202
    assert _clear_fault(client, make_event, fault_event_id=FAULT_ID).status_code == 409


def test_clearing_fault_on_wrong_compartment_is_rejected(client, make_event):
    _register(client, make_event, compartment="C1")
    _register(client, make_event, compartment="C2")
    _report_fault(client, make_event, event_id=FAULT_ID, compartment="C1", severity=4)
    assert _clear_fault(client, make_event, fault_event_id=FAULT_ID, compartment="C2").status_code == 409


def test_clearing_fault_restores_availability(client, make_event):
    _register(client, make_event)
    _report_fault(client, make_event, event_id=FAULT_ID, severity=4)
    assert _reserve(client, make_event).status_code == 409
    assert _clear_fault(client, make_event, fault_event_id=FAULT_ID).status_code == 202
    assert client.get("/lockers/L1/compartments/C1").json()["degraded"] is False
    assert _reserve(client, make_event).status_code == 202
