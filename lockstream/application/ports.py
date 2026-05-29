from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

# a raw, JSON-serializable event exactly as it sits on a line of the log
EventRecord = dict[str, Any]


# storage port the app depends on - the adapter lives in infrastructure
class EventStore(ABC):
    @abstractmethod
    def exists(self, event_id: str) -> bool: ...

    @abstractmethod
    def append(self, record: EventRecord) -> bool:
        """Append the record. Returns True if it wrote, False if the event_id was already stored."""

    @abstractmethod
    def load_all(self) -> Iterable[EventRecord]: ...

    @abstractmethod
    def load_by_locker(self, locker_id: str) -> Iterable[EventRecord]: ...
