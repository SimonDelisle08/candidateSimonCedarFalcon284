import logging
from enum import Enum, auto
from typing import Any

from ..domain.events import event_from_dict
from ..domain.projection import Projection
from .ports import EventRecord, EventStore

logger = logging.getLogger(__name__)


class IngestOutcome(Enum):
    ACCEPTED = auto()   # new event, applied and written -> 202
    DUPLICATE = auto()  # event_id already stored, no-op -> 200


# facade the API talks to: turns a raw event into projected state + a durable log line, and answers queries
class LockStreamService:
    def __init__(self, store: EventStore) -> None:
        self._store = store
        self._projection = Projection()

    def ingest(self, record: EventRecord) -> IngestOutcome:
        event_id = record["event_id"]
        # order matters: dedupe first (a known id is a no-op), then validate payload, then rules, then persist
        if self._store.exists(event_id):
            logger.debug("ingest: duplicate %s", event_id)
            return IngestOutcome.DUPLICATE
        event = event_from_dict(record)  # bad payload -> PayloadValidationError (422)
        self._projection.apply(event)    # rule violation -> DomainRuleViolation (409), state left untouched
        self._store.append(record)
        logger.debug("ingest: accepted %s", event_id)
        return IngestOutcome.ACCEPTED

    # replay the whole log into a fresh projection - this is what makes idempotency survive a restart
    def bootstrap(self) -> None:
        records = list(self._store.load_all())
        self._projection = Projection.rebuild(event_from_dict(record) for record in records)
        logger.debug("bootstrap: replayed %d events", len(records))

    def locker_summary(self, locker_id: str) -> dict[str, Any] | None:
        return self._projection.locker_summary(locker_id)

    def compartment_status(self, locker_id: str, compartment_id: str) -> dict[str, Any] | None:
        return self._projection.compartment_status(locker_id, compartment_id)

    def reservation_status(self, reservation_id: str) -> dict[str, Any] | None:
        return self._projection.reservation_status(reservation_id)
