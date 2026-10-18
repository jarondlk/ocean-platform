"""Raw multi-message ASGI proof of the C17 request stream byte bound."""
from __future__ import annotations

import json

import anyio
from fastapi import FastAPI
import pytest

from api import auth
from api.investigation_routes import MAX_REQUEST_BYTES, router
from tests.catalogue_service_support import fixture_user
from tests.test_investigation_api import TrustedTestService, payload


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    monkeypatch.setenv("ENABLE_V1_INVESTIGATIONS", "true")
    monkeypatch.setattr(auth, "authenticate_request", lambda request: fixture_user())


def raw_asgi(chunks, *, name="list", declared_length=None):
    """Drive actual middleware/router with an instrumented chunked receiver."""
    service = TrustedTestService()
    app = FastAPI()
    app.middleware("http")(auth.authorization_middleware)
    app.include_router(router)
    app.state.investigation_service = service
    received, sent = [], []
    headers = [(b"content-type", b"application/json")]
    if declared_length is not None:
        headers.append((b"content-length", str(declared_length).encode("ascii")))
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/research/investigations/" + name, "raw_path": ("/research/investigations/" + name).encode(),
        "root_path": "", "query_string": b"", "headers": headers,
        "server": ("test", 80), "client": ("127.0.0.1", 1234),
    }

    async def receive():
        index = len(received)
        assert index < len(chunks), "FastAPI read the consumed receive channel instead of the bounded cache"
        received.append(index)
        return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

    async def send(message):
        sent.append(message)

    async def scenario():
        await app(scope, receive, send)

    anyio.run(scenario)
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert len(starts) == 1
    response = json.loads(b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body"))
    assert dict(starts[0]["headers"])[b"cache-control"] == b"no-store"
    return starts[0]["status"], response, received, service.calls


@pytest.mark.parametrize("declared_length", [None, 2])
@pytest.mark.parametrize("split", ["first", "second", "third"])
def test_oversize_stream_stops_before_unread_tail_or_service_callback(split, declared_length):
    body = b"{}" + b" " * (MAX_REQUEST_BYTES - 2)
    accepted = [body] if split == "second" else [body[:10], body[10:]]
    chunks = [body + b" ", b"NEVER RECEIVE THIS TAIL"] if split == "first" else [*accepted, b" ", b"NEVER RECEIVE THIS TAIL"]
    status, result, received, calls = raw_asgi(chunks, declared_length=declared_length)
    assert status == 422
    assert result == {"error": {"code": "invalid_request", "message": "Investigation request is invalid"}}
    assert len(received) == len(chunks) - 1
    assert calls == []


@pytest.mark.parametrize("size", [MAX_REQUEST_BYTES - 1, MAX_REQUEST_BYTES])
@pytest.mark.parametrize("declared_length", [None, MAX_REQUEST_BYTES])
def test_exact_byte_bound_reassembles_once_and_fastapi_uses_cached_body(size, declared_length):
    body = b"{}" + b" " * (size - 2)
    chunks = [body[:1], b"", body[1:1024], body[1024:-1], body[-1:]]
    status, result, received, calls = raw_asgi(chunks, declared_length=declared_length)
    assert status == 200 and result["request"] == {"limit": 25}
    assert len(received) == len(chunks)
    assert len(calls) == 1 and calls[0][0] == "list"


@pytest.mark.parametrize("chunks", [
    [b'{"limit":1,', b'"limit":100}'],
    [b'{"limit":', b'Na', b'N}'],
    [b'{"private":"', b'\xff', b'"}'],
    [b'{"private":"\\u', b'd800"}'],
])
def test_duplicate_nonfinite_and_invalid_utf8_across_chunks_remain_sanitized(chunks):
    status, result, received, calls = raw_asgi(chunks)
    assert status == 422
    assert result == {"error": {"code": "invalid_request", "message": "Investigation request is invalid"}}
    assert len(received) == len(chunks) and calls == []


def test_valid_utf8_multibyte_name_split_between_messages_is_preserved():
    body = json.dumps(payload("create"), ensure_ascii=False).encode("utf-8")
    offset = body.index("調".encode("utf-8"))
    chunks = [body[:offset + 1], body[offset + 1:offset + 2], body[offset + 2:]]
    status, result, received, calls = raw_asgi(chunks, name="create")
    assert status == 200
    assert result["request"]["name"] == payload("create")["name"]
    assert len(received) == len(chunks) and len(calls) == 1
