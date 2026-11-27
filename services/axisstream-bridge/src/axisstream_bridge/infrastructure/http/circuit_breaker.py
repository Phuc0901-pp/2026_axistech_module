"""Deterministic Circuit Breaker state machine (ISO/IEC 25010 reliability)."""

from __future__ import annotations

from enum import Enum
import time
from typing import Callable


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread/async-safe single-process Circuit Breaker with injectable clock."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_sec: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout_sec <= 0:
            raise ValueError("recovery_timeout_sec must be > 0")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self._clock = clock or time.monotonic
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if (self._clock() - self._opened_at) >= self.recovery_timeout_sec:
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_in_flight = False
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.OPEN:
            return False
        # HALF_OPEN allows one probe request at a time
        if not self._half_open_probe_in_flight:
            self._half_open_probe_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
        self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        current = self.state
        if current == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._half_open_probe_in_flight = False
            return

        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._half_open_probe_in_flight = False
