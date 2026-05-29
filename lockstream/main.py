import logging
import os
from pathlib import Path

from fastapi import FastAPI

from .api.routes import router
from .application.service import LockStreamService
from .infrastructure.event_store import JsonlEventStore

DEFAULT_EVENT_LOG = "data/events.jsonl"


# app factory: wire one store + service, replay the log, expose the routes
def create_app() -> FastAPI:
    _configure_logging()
    log_path = Path(os.getenv("LOCKSTREAM_EVENT_LOG", DEFAULT_EVENT_LOG))
    service = LockStreamService(JsonlEventStore(log_path))
    service.bootstrap()

    app = FastAPI(title="LockStream API", version="1.0.0")
    app.state.service = service
    app.include_router(router)
    return app


# flip the event trace on with LOG_LEVEL=DEBUG
def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("lockstream").setLevel(level)
