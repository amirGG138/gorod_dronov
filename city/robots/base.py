"""Контракт борта — один и тот же у мока, HTTP-клиента и железа.

Соответствие HTTP-контракту из PLAN.md:

    GET  /status  -> status()
    POST /takeoff -> takeoff(alt)      POST /land  -> land()
    POST /goto    -> goto(cell, alt)   GET  /shot  -> shot()
    POST /look    -> look(xy, alt)     POST /drive -> drive(cell)
    POST /led     -> led(mode, color)  POST /stop  -> stop()

/look отличается от /goto только единицами: точка задаётся в метрах поля, а не в
клетках. Она нужна для облёта: точки обзора монитора лежат МЕЖДУ клетками, и
округлять их до клетки — значит снимать не то место. Возврат на свою площадку —
тот же /look с координатами её метки.

Аппарат реализует только свои методы; остальные бросают Unsupported. Диспетчер
никогда не проверяет тип объекта — он проверяет роль в status()["role"].

Поле last_move в статусе — момент последнего движения по часам системы. Без него
нельзя доказать, что стоянка у башни прошла без движения, а это ровно то, что
регламент требует зафиксировать.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence


class RobotError(Exception):
    """Борт отказался выполнять команду."""


class Unsupported(RobotError):
    """Этот аппарат такого не умеет."""


class Robot(Protocol):
    role: str

    def status(self) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...


class Drone(Robot, Protocol):
    def takeoff(self, alt: float) -> dict[str, Any]: ...

    def land(self) -> dict[str, Any]: ...

    def goto(self, cell: Sequence[int], alt: float) -> dict[str, Any]: ...

    def look(self, xy: Sequence[float], alt: float) -> dict[str, Any]: ...

    def shot(self) -> bytes: ...


class Rover(Robot, Protocol):
    def drive(self, cell: Sequence[int]) -> dict[str, Any]: ...

    def led(self, mode: str, color: str | None = None) -> dict[str, Any]: ...
