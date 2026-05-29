from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ..domain.models import EventType, ReservationStatus


# request body for POST /events
class EventIn(BaseModel):
    event_id: UUID
    occurred_at: datetime
    locker_id: str
    type: EventType
    payload: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "occurred_at": self.occurred_at.isoformat(),
            "locker_id": self.locker_id,
            "type": self.type.value,
            "payload": self.payload,
        }


class LockerSummaryOut(BaseModel):
    locker_id: str
    compartments: int
    active_reservations: int
    degraded_compartments: int
    state_hash: str


class CompartmentStatusOut(BaseModel):
    compartment_id: str
    degraded: bool
    active_reservation: str | None


class ReservationStatusOut(BaseModel):
    reservation_id: str
    status: ReservationStatus
