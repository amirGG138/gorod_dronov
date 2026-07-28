"""Аппараты в памяти: тот же контракт, но без сети и без железа.

Мок намеренно придирчив — отказывает на переезд не в соседнюю клетку и на
команду во время движения. Диспетчер, отлаженный на всепрощающем моке, на поле
разваливается; лучше ловить это здесь.
"""

from __future__ import annotations

import base64
import math
from typing import Any, Sequence

from ..field import Cell, Field, as_cell
from .base import RobotError, Unsupported

# Настоящий (хоть и крохотный) JPEG 16x16: /shot обязан отдавать картинку уже на
# этапе 0. Файл из мок-прогона должен открываться просмотрщиком, иначе непонятно,
# сломана камера или сломана запись кадра.
BLANK_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABsSFBcUERsXFhceHBsgKEIrKCUlKFE6PTBCYFVlZF9VXVtqeJmB"
    "anGQc1tdhbWGkJ6jq62rZ4C8ybqmx5moq6T/2wBDARweHigjKE4rK06kbl1upKSkpKSkpKSkpKSkpKSkpKSk"
    "pKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKT/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAA"
    "AAAAAAAAAAAAAAP/xAAaEAACAgMAAAAAAAAAAAAAAAAEEgAREyJB/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/E"
    "ABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJDD522Va5cEj4F2Zr5UDEYG1Zq7UEkZ11Vb7cD/"
    "2Q=="
)


class _Fake:
    role = "fake"

    def __init__(self, clock, cell: Sequence[int] = (0, 0), name: str = "") -> None:
        self.clock = clock
        self.cell: Cell = as_cell(cell)
        self.name = name or self.role
        self.state = "idle"
        self._last_move = clock.now()
        self.stopped = False
        self.busy = False  # исполняется ли прямо сейчас команда (важно по сети)
        self.current = ""  # какая именно

    def status(self) -> dict[str, Any]:
        # since_move — сколько секунд назад аппарат двигался в последний раз.
        # Именно «сколько назад», а не «когда»: у борта и у ноутбука свои часы,
        # и абсолютные метки времени сравнивать между машинами нельзя.
        return {
            "ok": True,
            "role": self.role,
            "name": self.name,
            "state": self.state,
            "cell": list(self.cell),
            "since_move": round(self.clock.now() - self._last_move, 3),
            "busy": self.busy,
        }

    def stop(self) -> dict[str, Any]:
        self.state = "idle"
        self.stopped = True
        return {"accepted": True}

    def _step(self, cell: Cell, seconds: float) -> None:
        self.state = "moving"
        self.clock.sleep(seconds)
        self.cell = cell
        self._last_move = self.clock.now()
        self.state = "idle"


class FakeRover(_Fake):
    role = "rover"

    def __init__(self, clock, cell: Sequence[int] = (3, 3), move_time: float = 1.2) -> None:
        super().__init__(clock, cell, name="rover")
        self.move_time = float(move_time)
        self.led_mode = "off"

    def status(self) -> dict[str, Any]:
        st = super().status()
        st["led"] = self.led_mode
        return st

    def check_drive(self, cell: Sequence[int]) -> Cell:
        """Проверка команды без исполнения: отказ должен приходить сразу, а не в конце."""
        target = as_cell(cell)
        dist = abs(target[0] - self.cell[0]) + abs(target[1] - self.cell[1])
        if dist > 1:
            raise RobotError(
                f"rover: {list(self.cell)} -> {list(target)} не соседняя клетка "
                "(диспетчер обязан ехать по одной клетке)"
            )
        if self.state == "moving":
            raise RobotError("rover: уже едет, вторая команда движения отклонена")
        return target

    def drive(self, cell: Sequence[int]) -> dict[str, Any]:
        """Переезд ровно в соседнюю клетку: так же считается игровой заряд."""
        target = self.check_drive(cell)
        if target != self.cell:
            self._step(target, self.move_time)
        return {"accepted": True, "cell": list(self.cell)}

    def led(self, mode: str, color: str | None = None) -> dict[str, Any]:
        if mode not in ("on", "off", "blink"):
            raise RobotError(f"rover: неизвестный режим ленты {mode!r}")
        self.led_mode = mode
        return {"accepted": True, "led": mode}


class FakeDrone(_Fake):
    role = "drone"

    def __init__(self, clock, cell: Sequence[int] = (1, 1), name: str = "m1", scene=None) -> None:
        super().__init__(clock, cell, name=name)
        self.alt = 0.0
        self.pad: Cell = as_cell(cell)
        # scene — нарисованный мир (city/robots/scene.py). Есть он — дрон «снимает»
        # поле с той точки, где висит; нет — отдаёт заглушку. Дрон о содержимом
        # сцены ничего не знает: очаг на кадре ищет уже диспетчер.
        self.scene = scene
        # Без сцены геометрия берётся по умолчанию (6x6 по 0,8 м): статус обязан
        # называть осмысленные метры, даже когда рисовать кадры нечем.
        field = scene.field if scene is not None else Field()
        self.xy = field.cell_to_m(self.pad)

    def status(self) -> dict[str, Any]:
        st = super().status()
        st["alt"] = self.alt
        st["xy"] = [round(v, 3) for v in self.xy]
        return st

    def takeoff(self, alt: float) -> dict[str, Any]:
        self.state = "taking_off"
        self.clock.sleep(3.0)
        self.alt = float(alt)
        self._last_move = self.clock.now()
        self.state = "hover"
        return {"accepted": True, "alt": self.alt}

    def land(self) -> dict[str, Any]:
        self.state = "landing"
        self.clock.sleep(3.0)
        self.alt = 0.0
        self._last_move = self.clock.now()
        self.state = "landed"
        return {"accepted": True}

    def check_goto(self, cell: Sequence[int]) -> Cell:
        if self.state != "hover":
            raise RobotError(f"{self.name}: goto до взлёта")
        return as_cell(cell)

    def goto(self, cell: Sequence[int], alt: float) -> dict[str, Any]:
        target = self.check_goto(cell)
        dist = abs(target[0] - self.cell[0]) + abs(target[1] - self.cell[1])
        self._step(target, max(1.0, dist * 0.8))
        if self.scene is not None:
            self.xy = self.scene.field.cell_to_m(target)
        self.state = "hover"
        self.alt = float(alt)
        return {"accepted": True, "cell": list(self.cell)}

    def check_look(self, xy: Sequence[float]) -> tuple[float, float]:
        if self.state != "hover":
            raise RobotError(f"{self.name}: точка обзора до взлёта")
        return (float(xy[0]), float(xy[1]))

    def look(self, xy: Sequence[float], alt: float) -> dict[str, Any]:
        """Зависнуть над точкой поля в метрах: так дрон облетает свой угол."""
        target = self.check_look(xy)
        dist = math.hypot(target[0] - self.xy[0], target[1] - self.xy[1])
        self.state = "moving"
        self.clock.sleep(max(0.5, dist * 1.5))  # примерно 0,65 м/с
        self.xy = target
        self.alt = float(alt)
        self._last_move = self.clock.now()
        self.state = "hover"
        if self.scene is not None:
            self.cell = self.scene.field.m_to_cell(*target)
        return {"accepted": True, "xy": [round(v, 3) for v in self.xy]}

    def shot(self) -> bytes:
        if self.state not in ("hover", "idle"):
            raise RobotError(f"{self.name}: кадр во время манёвра")
        self.clock.sleep(0.3)
        if self.scene is not None:
            frame = self.scene.render(self.xy, max(self.alt, 0.5))
            if frame is not None:
                return frame
        return BLANK_JPEG


class FakeVup(FakeDrone):
    role = "vup"

    def __init__(self, clock, cell: Sequence[int] = (3, 3), name: str = "vup", scene=None) -> None:
        super().__init__(clock, cell, name=name, scene=scene)


__all__ = ["FakeRover", "FakeDrone", "FakeVup", "BLANK_JPEG", "RobotError", "Unsupported"]
