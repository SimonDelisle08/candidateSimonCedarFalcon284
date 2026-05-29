# enums + the in-memory aggregates the projection builds and queries
from dataclasses import dataclass, field
from enum import Enum

DEGRADED_SEVERITY_THRESHOLD = 3  # an uncleared fault at or above this degrades the compartment


class EventType(str, Enum):
    COMPARTMENT_REGISTERED = "CompartmentRegistered"
    RESERVATION_CREATED = "ReservationCreated"
    PARCEL_DEPOSITED = "ParcelDeposited"
    PARCEL_PICKED_UP = "ParcelPickedUp"
    RESERVATION_EXPIRED = "ReservationExpired"
    FAULT_REPORTED = "FaultReported"
    FAULT_CLEARED = "FaultCleared"


class ReservationStatus(str, Enum):
    CREATED = "CREATED"
    DEPOSITED = "DEPOSITED"
    PICKED_UP = "PICKED_UP"
    EXPIRED = "EXPIRED"


@dataclass
class Fault:
    event_id: str  # the FaultReported event_id that opened this fault
    severity: int
    cleared: bool = False


@dataclass
class Compartment:
    compartment_id: str
    active_reservation: str | None = None  # one slot - enforces "at most one active" and keeps lookups O(1)
    faults: dict[str, Fault] = field(default_factory=dict)  # keyed by FaultReported event_id so clearing is O(1)

    @property
    def degraded(self) -> bool:
        return any(
            not fault.cleared and fault.severity >= DEGRADED_SEVERITY_THRESHOLD
            for fault in self.faults.values()
        )


@dataclass
class Reservation:
    reservation_id: str
    locker_id: str  # later events only carry reservation_id, so we keep these to find the compartment
    compartment_id: str
    status: ReservationStatus = ReservationStatus.CREATED
