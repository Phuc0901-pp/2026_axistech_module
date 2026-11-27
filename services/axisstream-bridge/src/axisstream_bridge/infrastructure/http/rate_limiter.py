"""Token Bucket Rate Limiter with injectable clock and sleeper for deterministic tests."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable


class TokenBucketRateLimiter:
    """Async token bucket rate limiter."""

    def __init__(
        self,
        rate_per_sec: float = 10.0,
        burst: int = 20,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if burst < 1:
            raise ValueError("burst must be >= 1")
        self.rate_per_sec = rate_per_sec
        self.burst = float(burst)
        self._tokens = float(burst)
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or asyncio.sleep
        self._last_refill = self._clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed > 0:
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_sec)
            self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens, returning total seconds waited."""
        if tokens <= 0 or tokens > self.burst:
            raise ValueError(f"Requested tokens {tokens} must be in (0, {self.burst}]")
        waited = 0.0
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return waited
                deficit = tokens - self._tokens
                wait_sec = deficit / self.rate_per_sec
                waited += wait_sec
                await self._sleeper(wait_sec)
                self._refill()
                # If sleeper didn't advance a fake clock, force refill step to avoid infinite loop
                if self._tokens < tokens:
                    self._tokens = max(0.0, self._tokens + wait_sec * self.rate_per_sec)
                    self._last_refill = self._clock()
                    if self._tokens >= tokens:
                        self._tokens -= tokens
                        return waited
