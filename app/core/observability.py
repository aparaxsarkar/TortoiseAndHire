"""Minimal in-process metrics + a request-timing middleware.

Deliberately tiny (see docs/architecture.md §11): counters and a sum/count
"histogram", held in memory, rendered in Prometheus text format. Not a metrics
backend — just enough to answer "how many ingestion runs failed today" and
"how slow are requests" without adding infrastructure.

`TimingMiddleware` records one counter + one duration observation per HTTP
request and logs a structured line. Wired into the app in `app/main.py`; the
`/metrics` route that exposes `metrics.render_prometheus()` is added with auth
on Day 8.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

log = get_logger("http")

_Labels = tuple[tuple[str, str], ...]


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[tuple[str, _Labels], float] = defaultdict(float)
        self._hist_sum: dict[str, float] = defaultdict(float)
        self._hist_count: dict[str, int] = defaultdict(int)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._hist_sum[name] += value
            self._hist_count[name] += 1

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._hist_sum.clear()
            self._hist_count.clear()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                suffix = f"{{{label_str}}}" if label_str else ""
                lines.append(f"{name}{suffix} {value}")
            for name, total in sorted(self._hist_sum.items()):
                lines.append(f"{name}_sum {total}")
                lines.append(f"{name}_count {self._hist_count[name]}")
        return "\n".join(lines) + "\n"


# Process-wide registry. App code imports this instance.
metrics = Metrics()


class TimingMiddleware:
    """Raw ASGI middleware: times every HTTP request, records a metric, logs it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = {"code": 500}
        start = perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = perf_counter() - start
            method = str(scope.get("method", "-"))
            path = str(scope.get("path", "-"))
            metrics.inc("http_requests_total", method=method, status=str(status["code"]))
            metrics.observe("http_request_duration_seconds", elapsed)
            log.info(
                "http.request",
                method=method,
                path=path,
                status=status["code"],
                duration_ms=round(elapsed * 1000, 2),
            )
