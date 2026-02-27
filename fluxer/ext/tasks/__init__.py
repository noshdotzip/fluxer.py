from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable, Optional


class Loop:
    def __init__(
        self,
        coro: Callable[..., Awaitable[Any]],
        *,
        seconds: float = 0.0,
        minutes: float = 0.0,
        hours: float = 0.0,
        count: Optional[int] = None,
        reconnect: bool = True,
    ) -> None:
        if not inspect.iscoroutinefunction(coro):
            raise TypeError("Loop function must be a coroutine")
        self.coro = coro
        self.seconds = seconds + minutes * 60.0 + hours * 3600.0
        self.count = count
        self.reconnect = reconnect
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._before_loop: Optional[Callable[[], Awaitable[None]]] = None
        self._after_loop: Optional[Callable[[], Awaitable[None]]] = None
        self._error: Optional[Callable[[Exception], Awaitable[None]]] = None
        self._current_loop = 0
        self._args: tuple[Any, ...] = ()
        self._kwargs: dict[str, Any] = {}

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, *args: Any, **kwargs: Any) -> None:
        if self.is_running():
            return
        self._stop = asyncio.Event()
        self._args = args
        self._kwargs = kwargs
        self._task = asyncio.create_task(self._run_loop())

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()

    def stop(self) -> None:
        self._stop.set()

    def change_interval(self, *, seconds: float = 0.0, minutes: float = 0.0, hours: float = 0.0) -> None:
        self.seconds = seconds + minutes * 60.0 + hours * 3600.0

    def before_loop(self, coro: Callable[[], Awaitable[None]]):
        self._before_loop = coro
        return coro

    def after_loop(self, coro: Callable[[], Awaitable[None]]):
        self._after_loop = coro
        return coro

    def error(self, coro: Callable[[Exception], Awaitable[None]]):
        self._error = coro
        return coro

    async def _run_loop(self) -> None:
        if self._before_loop:
            await self._before_loop()
        try:
            while not self._stop.is_set():
                try:
                    await self.coro(*self._args, **self._kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self._error:
                        await self._error(exc)
                    if not self.reconnect:
                        raise
                self._current_loop += 1
                if self.count is not None and self._current_loop >= self.count:
                    break
                if self.seconds > 0:
                    await asyncio.sleep(self.seconds)
                else:
                    await asyncio.sleep(0)
        finally:
            if self._after_loop:
                await self._after_loop()


def loop(*, seconds: float = 0.0, minutes: float = 0.0, hours: float = 0.0, count: Optional[int] = None, reconnect: bool = True):
    def decorator(coro: Callable[..., Awaitable[Any]]) -> Loop:
        return Loop(
            coro,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            count=count,
            reconnect=reconnect,
        )

    return decorator


__all__ = [
    "Loop",
    "loop",
]
