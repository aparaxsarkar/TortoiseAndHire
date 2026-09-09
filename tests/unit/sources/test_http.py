from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.sources.errors import (
    SourceAuthError,
    SourcePayloadError,
    SourceRateLimited,
    SourceUnavailable,
)
from app.sources.http import HttpClient

URL = "https://api.example.test/data"


@pytest.fixture
async def http() -> AsyncIterator[HttpClient]:
    client = HttpClient(retry_attempts=3, retry_backoff=0.0)
    try:
        yield client
    finally:
        await client.aclose()


@respx.mock
async def test_returns_parsed_json(http: HttpClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await http.get_json(URL) == {"ok": 1}


@respx.mock
async def test_post_json_sends_the_body_and_parses_the_response(http: HttpClient) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"total": 3}))
    assert await http.post_json(URL, json_body={"limit": 20, "offset": 0}) == {"total": 3}
    assert route.calls.last.request.method == "POST"
    assert json.loads(route.calls.last.request.content) == {"limit": 20, "offset": 0}
    assert route.calls.last.request.headers["content-type"] == "application/json"


@respx.mock
async def test_post_json_maps_5xx_to_unavailable_and_retries(http: HttpClient) -> None:
    route = respx.post(URL)
    route.side_effect = [httpx.Response(503), httpx.Response(200, json={"ok": True})]
    assert await http.post_json(URL, json_body={}) == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_retries_transient_5xx_then_succeeds(http: HttpClient) -> None:
    route = respx.get(URL)
    route.side_effect = [httpx.Response(503), httpx.Response(200, json={"ok": True})]
    assert await http.get_json(URL) == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_5xx_exhausts_retries_and_raises_unavailable(http: HttpClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(SourceUnavailable):
        await http.get_json(URL)


@respx.mock
async def test_403_raises_auth_error_without_retrying(http: HttpClient) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(403))
    with pytest.raises(SourceAuthError):
        await http.get_json(URL)
    assert route.call_count == 1


@respx.mock
async def test_429_without_retry_after_raises_rate_limited(http: HttpClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(SourceRateLimited):
        await http.get_json(URL)


@respx.mock
async def test_429_with_small_retry_after_is_honoured_once(http: HttpClient) -> None:
    route = respx.get(URL)
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"ok": 1}),
    ]
    assert await http.get_json(URL) == {"ok": 1}
    assert route.call_count == 2


@respx.mock
async def test_non_json_body_raises_payload_error(http: HttpClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(SourcePayloadError):
        await http.get_json(URL)


@respx.mock
async def test_other_4xx_raises_payload_error(http: HttpClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(404, text="missing"))
    with pytest.raises(SourcePayloadError):
        await http.get_json(URL)
