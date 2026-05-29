import json
import logging
from collections.abc import Iterator
from pathlib import Path

from ..application.ports import EventRecord, EventStore

logger = logging.getLogger(__name__)


# append-only log: one JSON object per line, with O(1) dedupe via an in-memory set of seen event_ids
class JsonlEventStore(EventStore):
    def __init__(self, path: Path) -> None:
        self._path = path
        # primed from disk so dedupe survives a restart
        self._seen: set[str] = {record["event_id"] for record in self._read()}
        logger.debug("event store at %s primed with %d event ids", path, len(self._seen))

    def exists(self, event_id: str) -> bool:
        return event_id in self._seen

    def append(self, record: EventRecord) -> bool:
        event_id = record["event_id"]
        if event_id not in self._seen:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")
            self._seen.add(event_id)
            logger.debug("appended event %s", event_id)
            return True
        logger.debug("duplicate event %s, skipped", event_id)
        return False

    def load_all(self) -> list[EventRecord]:
        records = list(self._read())
        logger.debug("loaded %d events", len(records))
        return records

    def load_by_locker(self, locker_id: str) -> list[EventRecord]:
        records = [record for record in self._read() if record.get("locker_id") == locker_id]
        logger.debug("loaded %d events for locker %s", len(records), locker_id)
        return records

    # walk the log line by line; an absent file just means no events yet, not an error
    def _read(self) -> Iterator[EventRecord]:
        if self._path.exists():
            with self._path.open(encoding="utf-8") as log:
                for line in log:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
