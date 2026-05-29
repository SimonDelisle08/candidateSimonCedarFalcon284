import hashlib
import json
import logging
from collections.abc import Iterable
from typing import Any

from .errors import DomainRuleViolation
from .events import (
    CompartmentRegistered,
    DomainEvent,
    FaultCleared,
    FaultReported,
    ParcelDeposited,
    ParcelPickedUp,
    ReservationCreated,
    ReservationExpired,
)
from .models import Compartment, Fault, Reservation, ReservationStatus

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({ReservationStatus.CREATED, ReservationStatus.DEPOSITED})


class Projection:
    def __init__(self) -> None:
        self._lockers: dict[str, dict[str, Compartment]] = {}
        self._reservations: dict[str, Reservation] = {}

    def apply(self, event: DomainEvent) -> None:
        logger.debug(
            "applying %s id=%s locker=%s",
            type(event).__name__, event.event_id, event.locker_id,
        )
        match event:
            case CompartmentRegistered():
                self._register_compartment(event)
            case ReservationCreated():
                self._create_reservation(event)
            case ParcelDeposited():
                self._deposit(event)
            case ParcelPickedUp():
                self._pickup(event)
            case ReservationExpired():
                self._expire(event)
            case FaultReported():
                self._report_fault(event)
            case FaultCleared():
                self._clear_fault(event)
            case _:
                raise TypeError(f"unhandled event: {type(event).__name__}")

    @classmethod
    def rebuild(cls, events: Iterable[DomainEvent]) -> "Projection":
        projection = cls()
        for event in events:
            projection.apply(event)
        logger.debug(
            "rebuilt projection: %d lockers, %d reservations",
            len(projection._lockers), len(projection._reservations),
        )
        return projection

    def locker_summary(self, locker_id: str) -> dict[str, Any] | None:
        compartments = self._lockers.get(locker_id)
        if compartments is None:
            return None
        return {
            "locker_id": locker_id,
            "compartments": len(compartments),
            "active_reservations": sum(
                1 for c in compartments.values() if c.active_reservation is not None
            ),
            "degraded_compartments": sum(1 for c in compartments.values() if c.degraded),
            "state_hash": self.state_hash(locker_id),
        }

    def compartment_status(self, locker_id: str, compartment_id: str) -> dict[str, Any] | None:
        compartment = self._lockers.get(locker_id, {}).get(compartment_id)
        if compartment is None:
            return None
        return {
            "compartment_id": compartment.compartment_id,
            "degraded": compartment.degraded,
            "active_reservation": compartment.active_reservation,
        }

    def reservation_status(self, reservation_id: str) -> dict[str, Any] | None:
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            return None
        return {
            "reservation_id": reservation.reservation_id,
            "status": reservation.status.value,
        }

    def state_hash(self, locker_id: str) -> str:
        compartments = self._lockers.get(locker_id, {})
        # everything sorted by id, so the hash depends on state alone - not the order events arrived
        snapshot = {
            "compartments": [
                {
                    "compartment_id": c.compartment_id,
                    "active_reservation": c.active_reservation,
                    "faults": [
                        {"event_id": f.event_id, "severity": f.severity, "cleared": f.cleared}
                        for f in sorted(c.faults.values(), key=lambda f: f.event_id)
                    ],
                }
                for c in sorted(compartments.values(), key=lambda c: c.compartment_id)
            ],
            "reservations": [
                {
                    "reservation_id": r.reservation_id,
                    "compartment_id": r.compartment_id,
                    "status": r.status.value,
                }
                for r in sorted(self._reservations_for(locker_id), key=lambda r: r.reservation_id)
            ],
        }
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _register_compartment(self, event: CompartmentRegistered) -> None:
        compartments = self._lockers.setdefault(event.locker_id, {})
        if event.compartment_id not in compartments:
            compartments[event.compartment_id] = Compartment(event.compartment_id)
            logger.debug(
                "registered compartment %s in locker %s",
                event.compartment_id, event.locker_id,
            )
        else:
            raise DomainRuleViolation(f"compartment {event.compartment_id} already registered")

    def _create_reservation(self, event: ReservationCreated) -> None:
        compartment = self._find_compartment(event.locker_id, event.compartment_id)
        self._assert_can_reserve(compartment, event)
        self._reservations[event.reservation_id] = Reservation(
            event.reservation_id, event.locker_id, event.compartment_id
        )
        compartment.active_reservation = event.reservation_id
        logger.debug(
            "reservation %s created on compartment %s",
            event.reservation_id, event.compartment_id,
        )

    def _deposit(self, event: ParcelDeposited) -> None:
        reservation = self._reservations.get(event.reservation_id)
        if reservation is not None:
            if reservation.status is ReservationStatus.CREATED:
                reservation.status = ReservationStatus.DEPOSITED
                logger.debug("reservation %s -> DEPOSITED", event.reservation_id)
            else:
                raise DomainRuleViolation(f"reservation {event.reservation_id} cannot accept a deposit")
        else:
            raise DomainRuleViolation(f"unknown reservation {event.reservation_id}")

    def _pickup(self, event: ParcelPickedUp) -> None:
        reservation = self._reservations.get(event.reservation_id)
        if reservation is not None:
            if reservation.status is ReservationStatus.DEPOSITED:
                reservation.status = ReservationStatus.PICKED_UP
                self._release_compartment(reservation)
                logger.debug("reservation %s -> PICKED_UP", event.reservation_id)
            else:
                raise DomainRuleViolation(f"reservation {event.reservation_id} has nothing to pick up")
        else:
            raise DomainRuleViolation(f"unknown reservation {event.reservation_id}")

    def _expire(self, event: ReservationExpired) -> None:
        reservation = self._reservations.get(event.reservation_id)
        if reservation is not None:
            if reservation.status in _ACTIVE_STATUSES:
                reservation.status = ReservationStatus.EXPIRED
                self._release_compartment(reservation)
                logger.debug("reservation %s -> EXPIRED", event.reservation_id)
            else:
                raise DomainRuleViolation(f"reservation {event.reservation_id} is not active")
        else:
            raise DomainRuleViolation(f"unknown reservation {event.reservation_id}")

    def _report_fault(self, event: FaultReported) -> None:
        compartment = self._find_compartment(event.locker_id, event.compartment_id)
        compartment.faults[event.event_id] = Fault(event.event_id, event.severity)
        logger.debug(
            "fault %s reported on compartment %s (severity=%d, degraded=%s)",
            event.event_id, event.compartment_id, event.severity, compartment.degraded,
        )

    def _clear_fault(self, event: FaultCleared) -> None:
        compartment = self._find_compartment(event.locker_id, event.compartment_id)
        # looking the fault up on this compartment also enforces the "same compartment" rule
        fault = compartment.faults.get(event.fault_event_id)
        if fault is not None:
            if not fault.cleared:
                fault.cleared = True
                logger.debug(
                    "fault %s cleared on compartment %s",
                    event.fault_event_id, event.compartment_id,
                )
            else:
                raise DomainRuleViolation(f"fault {event.fault_event_id} already cleared")
        else:
            raise DomainRuleViolation(
                f"no fault {event.fault_event_id} on compartment {event.compartment_id}"
            )

    def _find_compartment(self, locker_id: str, compartment_id: str) -> Compartment:
        compartment = self._lockers.get(locker_id, {}).get(compartment_id)
        if compartment is None:
            raise DomainRuleViolation(f"unknown compartment {compartment_id} in locker {locker_id}")
        return compartment

    def _assert_can_reserve(self, compartment: Compartment, event: ReservationCreated) -> None:
        if compartment.degraded:
            raise DomainRuleViolation(f"compartment {compartment.compartment_id} is degraded")
        if compartment.active_reservation is not None:
            raise DomainRuleViolation(f"compartment {compartment.compartment_id} already reserved")
        if event.reservation_id in self._reservations:
            raise DomainRuleViolation(f"reservation {event.reservation_id} already exists")

    def _release_compartment(self, reservation: Reservation) -> None:
        compartment = self._lockers[reservation.locker_id][reservation.compartment_id]
        compartment.active_reservation = None

    def _reservations_for(self, locker_id: str) -> list[Reservation]:
        return [r for r in self._reservations.values() if r.locker_id == locker_id]
