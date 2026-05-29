import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lockstream.main import create_app

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.yaml"


# each test gets its own empty log under tmp_path, so state never leaks between tests
@pytest.fixture
def event_log(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def app(event_log: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("LOCKSTREAM_EVENT_LOG", str(event_log))
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_event() -> Callable[..., dict[str, Any]]:
    # build a valid event envelope; event_id is fresh each call unless you pin it
    def _make(
        event_type: str,
        payload: dict[str, Any],
        *,
        locker_id: str = "L1",
        event_id: str | None = None,
        occurred_at: str = "2026-05-28T10:00:00Z",
    ) -> dict[str, Any]:
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "occurred_at": occurred_at,
            "locker_id": locker_id,
            "type": event_type,
            "payload": payload,
        }

    return _make


@pytest.fixture(scope="session")
def openapi_schemas() -> dict[str, Any]:
    spec = yaml.safe_load(OPENAPI_PATH.read_text())
    return {name: _normalize_nullable(schema) for name, schema in spec["components"]["schemas"].items()}


def _normalize_nullable(node: Any) -> Any:
    # validator accepts null where the spec marked a field nullable (see DECISIONS.md)
    if isinstance(node, dict):
        node = {key: _normalize_nullable(value) for key, value in node.items()}
        if node.pop("nullable", False) and "type" in node:
            node["type"] = [node["type"], "null"]
        return node
    if isinstance(node, list):
        return [_normalize_nullable(item) for item in node]
    return node
