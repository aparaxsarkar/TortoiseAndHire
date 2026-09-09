"""Shared async HTTP for adapters.

One `httpx.AsyncClient` per adapter, with an honest User-Agent that names the
tool (never a browser impersonation), a per-source token bucket, retry on
transient errors, and HTTP status mapped to the `SourceError` taxonomy. A `429`
with a small `Retry-After` is honoured once here; anything larger is raised for
the ingestion runner to decide on.

`get_json` covers Greenhouse / Lever / Ashby; `post_json` (same machinery, POST
+ JSON body) covers Workday's hidden `wday/cxs` search endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.logging import get_logger
from app.core.rate_limit import TokenBucket
from app.core.retry import async_retry_policy
from app.sources.errors import (
    SourceAuthError,
    SourcePayloadError,
    SourceRateLimited,
    SourceUnavailable,
)

log = get_logger("sources.http")

USER_AGENT = "TortoiseAndHire/0.1 (+https://github.com/aparaxsarkar/TortoiseAndHire)"
_MAX_HONOURED_RETRY_AFTER = 30.0


class HttpClient:
    def __init__(
        self,
        *,
        base_url: str = "",
        rate_limit: TokenBucket | None = None,
        timeout: float = 20.0,
        user_agent: str = USER_AGENT,
        retry_attempts: int = 4,
        retry_backoff: float = 0.5,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                # Workday's list strings ("Posted Today") are localised; pin English.
                "Accept-Language": "en-US",
            },
            follow_redirects=True,
        )
        self._bucket = rate_limit
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, url: str, params: dict[str, Any] | None, json_body: Any | None
    ) -> httpx.Response:
        try:
            resp = await self._client.request(method, url, params=params, json=json_body)
        except httpx.TimeoutException as exc:
            raise SourceUnavailable(f"timeout: {url}") from exc
        except httpx.TransportError as exc:
            raise SourceUnavailable(f"transport error: {url}: {exc}") from exc

        code = resp.status_code
        if code == 429:
            ra = resp.headers.get("retry-after", "")
            retry_after = float(ra) if ra.replace(".", "", 1).isdigit() else None
            raise SourceRateLimited(f"429 from {url}", retry_after=retry_after)
        if code in (401, 403):
            raise SourceAuthError(f"{code} from {url}")
        if code >= 500:
            raise SourceUnavailable(f"{code} from {url}")
        if code >= 400:
            raise SourcePayloadError(f"{code} from {url}: {resp.text[:200]}")
        return resp

    async def _send_with_retries(
        self, method: str, url: str, params: dict[str, Any] | None, json_body: Any | None
    ) -> httpx.Response:
        retrying = async_retry_policy(
            retry_on=SourceUnavailable,
            max_attempts=self._retry_attempts,
            initial_backoff=self._retry_backoff,
            max_backoff=8.0,
        )
        if self._bucket is not None:
            await self._bucket.acquire()
        try:
            return await retrying(self._request, method, url, params, json_body)
        except SourceRateLimited as exc:
            if exc.retry_after is None or exc.retry_after > _MAX_HONOURED_RETRY_AFTER:
                raise
            log.warning("sources.http.rate_limited", url=url, retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            if self._bucket is not None:
                await self._bucket.acquire()
            return await retrying(self._request, method, url, params, json_body)

    @staticmethod
    def _json(resp: httpx.Response, url: str) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            raise SourcePayloadError(f"invalid JSON from {url}") from exc

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._json(await self._send_with_retries("GET", url, params, None), url)

    async def post_json(
        self, url: str, *, json_body: Any, params: dict[str, Any] | None = None
    ) -> Any:
        return self._json(await self._send_with_retries("POST", url, params, json_body), url)
