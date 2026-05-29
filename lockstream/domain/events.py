from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import PayloadValidationError
from .models import EventType


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    occurred_at: str  # metadata only - ordering is by append order, not this
    locker_id: str


@dataclass(frozen=True)
class CompartmentRegistered(DomainEvent):
    compartment_id: str


@dataclass(frozen=True)
class ReservationCreated(DomainEvent):
    reservation_id: str
    compartment_id: str


@dataclass(frozen=True)
class ParcelDeposited(DomainEvent):
    reservation_id: str


@dataclass(frozen=True)
class ParcelPickedUp(DomainEvent):
    reservation_id: str


@dataclass(frozen=True)
class ReservationExpired(DomainEvent):
    reservation_id: str


@dataclass(frozen=True)
class FaultReported(DomainEvent):
    compartment_id: str
    severity: int


@dataclass(frozen=True)
class FaultCleared(DomainEvent):
    compartment_id: str
    fault_event_id: str  # points back at a FaultReported.event_id


# payload is an open object in the spec, so each type's real shape is inferred and checked here
def event_from_dict(record: Mapping[str, Any]) -> DomainEvent:
    event_type = _event_type(record.get("type"))
    # envelope is already validated upstream (pydantic, or trusted on rebuild) - we only vet payload
    envelope = {
        "event_id": record["event_id"],
        "occurred_at": record["occurred_at"],
        "locker_id": record["locker_id"],
    }
    payload = record.get("payload") or {}
    match event_type:
        case EventType.COMPARTMENT_REGISTERED:
            return CompartmentRegistered(**envelope, compartment_id=_str(payload, "compartment_id"))
        case EventType.RESERVATION_CREATED:
            return ReservationCreated(
                **envelope,
                reservation_id=_str(payload, "reservation_id"),
                compartment_id=_str(payload, "compartment_id"),
            )
        case EventType.PARCEL_DEPOSITED:
            return ParcelDeposited(**envelope, reservation_id=_str(payload, "reservation_id"))
        case EventType.PARCEL_PICKED_UP:
            return ParcelPickedUp(**envelope, reservation_id=_str(payload, "reservation_id"))
        case EventType.RESERVATION_EXPIRED:
            return ReservationExpired(**envelope, reservation_id=_str(payload, "reservation_id"))
        case EventType.FAULT_REPORTED:
            return FaultReported(
                **envelope,
                compartment_id=_str(payload, "compartment_id"),
                severity=_int(payload, "severity"),
            )
        case EventType.FAULT_CLEARED:
            return FaultCleared(
                **envelope,
                compartment_id=_str(payload, "compartment_id"),
                fault_event_id=_str(payload, "fault_event_id"),
            )
        case _:
            raise PayloadValidationError(f"unhandled event type: {event_type}")


def _event_type(raw: Any) -> EventType:
    try:
        return EventType(raw)
    except ValueError:
        raise PayloadValidationError(f"unknown event type: {raw!r}") from None


def _str(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise PayloadValidationError(f"payload.{field} must be a string")
    return value


def _int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    # bool is an int subclass, so reject it explicitly
    if isinstance(value, bool) or not isinstance(value, int):
        raise PayloadValidationError(f"payload.{field} must be an integer")
    return value
