"""Token-bucket rate limiting.

One bucket per source. A bucket starts full (`capacity` tokens) and refills at
`rate` tokens/second. `consume()` takes tokens if available; `acquire()` is the
async form that waits until they are.

    bucket = TokenBucket(rate=1.0, capacity=5.0)   # ~1 req/s, bursts of 5
    await bucket.acquire()                          # blocks only if the bucket is dry

`clock` is injectable so the timing logic is testable without real sleeps.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    rate: float
    capacity: float
    clock: Callable[[], float] = time.monotonic
    _tokens: float = field(init=False)
    _last: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last = self.clock()

    def _refill(self) -> None:
        now = self.clock()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)

    def consume(self, tokens: float = 1.0) -> bool:
        """Take `tokens` if the bucket has them. Returns whether it did."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def time_until(self, tokens: float = 1.0) -> float:
        """Seconds until `tokens` would be available (0.0 if already)."""
        self._refill()
        if self._tokens >= tokens:
            return 0.0
        return (tokens - self._tokens) / self.rate

    async def acquire(self, tokens: float = 1.0) -> None:
        """Wait until `tokens` are available, then take them."""
        while not self.consume(tokens):
            await asyncio.sleep(self.time_until(tokens))
