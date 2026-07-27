"""Часы попытки.

Всё измерение времени в системе идёт через этот объект и только через него:
ни dispatcher, ни моки не зовут time.sleep напрямую. Благодаря этому полная
15-минутная попытка проигрывается в тестах и на демо за доли секунды, а на
железе тот же код работает в реальном времени сменой одного класса.
"""

from __future__ import annotations

import time


class RealClock:
    name = "real"

    def __init__(self) -> None:
        self._t0 = time.monotonic()

    def now(self) -> float:
        """Секунды от старта попытки."""
        return time.monotonic() - self._t0

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class SimClock:
    name = "sim"

    def __init__(self, t0: float = 0.0) -> None:
        self._t = t0

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._t += seconds
