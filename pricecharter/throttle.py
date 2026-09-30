import asyncio
import time
from datetime import datetime


class DeadlineReached(Exception):
    """The crawl window closed; stop cleanly."""


class Throttle:
    """Keeps at least `interval` seconds between request starts.

    `base` (default 1s) is the floor. A 429 doubles the interval (up to `ceiling`);
    every `recover_after` consecutive successes shrink it back toward the floor.
    """

    def __init__(
        self, base: float = 1.0, ceiling: float = 15.0, recover_after: int = 25, deadline: datetime | None = None
    ):
        self.base = self.interval = base
        self.deadline = deadline
        self.ceiling = ceiling
        self.recover_after = recover_after
        self._streak = 0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self.deadline and datetime.now() >= self.deadline:
            raise DeadlineReached(f"crawl window closed at {self.deadline:%Y-%m-%d %H:%M}")
        async with self._lock:
            delay = self._last + self.interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()

    def ok(self) -> None:
        self._streak += 1
        if self._streak >= self.recover_after and self.interval > self.base:
            self.interval = max(self.base, self.interval * 0.75)
            self._streak = 0

    async def rate_limited(self, attempt: int, retry_after: str | None = None) -> None:
        self._streak = 0
        self.interval = min(self.ceiling, self.interval * 2)
        try:
            pause = float(retry_after) if retry_after else 0.0
        except ValueError:
            pause = 0.0
        pause = max(pause, min(600.0, 30.0 * 2**attempt))
        if self.deadline:
            pause = max(0.0, min(pause, (self.deadline - datetime.now()).total_seconds()))
        print(f"   rate limited: pausing {pause:.0f}s, interval now {self.interval:.1f}s")
        await asyncio.sleep(pause)

    async def backoff(self, attempt: int, cap: float = 120.0) -> None:
        await asyncio.sleep(min(cap, self.base * 2 ** (attempt + 1)))
