def _register(client, make_event, compartment="C1", locker="L1"):
    payload = {"compartment_id": compartment}
    return client.post("/events", json=make_event("CompartmentRegistered", payload, locker_id=locker))


def _reserve(client, make_event, reservation="R1", compartment="C1", locker="L1"):
    payload = {"reservation_id": reservation, "compartment_id": compartment}
    return client.post("/events", json=make_event("ReservationCreated", payload, locker_id=locker))


def _deposit(client, make_event, reservation="R1"):
    return client.post("/events", json=make_event("ParcelDeposited", {"reservation_id": reservation}))


def _pickup(client, make_event, reservation="R1"):
    return client.post("/events", json=make_event("ParcelPickedUp", {"reservation_id": reservation}))


def _expire(client, make_event, reservation="R1"):
    return client.post("/events", json=make_event("ReservationExpired", {"reservation_id": reservation}))


def test_happy_path_created_deposited_picked_up(client, make_event):
    assert _register(client, make_event).status_code == 202
    assert _reserve(client, make_event).status_code == 202
    assert _deposit(client, make_event).status_code == 202
    assert _pickup(client, make_event).status_code == 202
    assert client.get("/reservations/R1").json()["status"] == "PICKED_UP"


def test_reserve_on_unknown_compartment_is_rejected(client, make_event):
    assert _reserve(client, make_event).status_code == 409


def test_deposit_before_reservation_is_rejected(client, make_event):
    _register(client, make_event)
    assert _deposit(client, make_event).status_code == 409


def test_pickup_before_deposit_is_rejected(client, make_event):
    _register(client, make_event)
    _reserve(client, make_event)
    assert _pickup(client, make_event).status_code == 409


def test_pickup_after_expiration_is_rejected(client, make_event):
    _register(client, make_event)
    _reserve(client, make_event)
    _deposit(client, make_event)
    assert _expire(client, make_event).status_code == 202
    assert _pickup(client, make_event).status_code == 409
    assert client.get("/reservations/R1").json()["status"] == "EXPIRED"


def test_deposit_after_expiration_is_rejected(client, make_event):
    _register(client, make_event)
    _reserve(client, make_event)
    _expire(client, make_event)
    assert _deposit(client, make_event).status_code == 409


def test_second_active_reservation_on_compartment_is_rejected(client, make_event):
    _register(client, make_event)
    assert _reserve(client, make_event, reservation="R1").status_code == 202
    assert _reserve(client, make_event, reservation="R2").status_code == 409


def test_rejected_event_leaves_state_untouched(client, make_event):
    _register(client, make_event)
    _reserve(client, make_event)
    before = client.get("/lockers/L1").json()["state_hash"]
    assert _deposit(client, make_event, reservation="GHOST").status_code == 409
    after = client.get("/lockers/L1").json()["state_hash"]
    assert before == after
