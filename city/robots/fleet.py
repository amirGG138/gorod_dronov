"""Сборка флота: аппараты в памяти или по сети.

Одно место, где решается, кем командовать. Диспетчер получает объекты с
одинаковыми методами и не знает, мок это, отдельная программа или живой борт.
"""

from __future__ import annotations

from typing import Any

from .base import RobotError
from .fake import FakeDrone, FakeRover, FakeVup
from .http_robot import HttpRobot, wait_online


class Fleet:
    """Набор аппаратов попытки. Отсутствующий аппарат — None, а не заглушка."""

    def __init__(self, rover=None, vup=None, monitors=None, transport: str = "fake") -> None:
        self.rover = rover
        self.vup = vup
        self.monitors = monitors or {}
        self.transport = transport

    def all(self):
        out = []
        if self.rover:
            out.append(self.rover)
        if self.vup:
            out.append(self.vup)
        out.extend(self.monitors.values())
        return out

    def connect(self, wait: float = 0.0) -> list[dict[str, Any]]:
        """Опросить каждый борт и вернуть, кто ответил. Пустой список ошибок = все живы.

        Признак `dry` в ответе означает, что на том конце программа-заглушка: она
        отвечает как аппарат, но ничего не делает. Это обязано попасть в лог.
        """
        report: list[dict[str, Any]] = []
        for robot in self.all():
            entry: dict[str, Any] = {
                "name": getattr(robot, "name", "?"),
                "role": getattr(robot, "role", "?"),
                "url": getattr(robot, "url", "в памяти"),
            }
            try:
                st = wait_online(robot, wait) if wait and isinstance(robot, HttpRobot) else robot.status()
                entry.update(state=st.get("state"), cell=st.get("cell"), dry=bool(st.get("dry")))
            except RobotError as exc:
                entry.update(state="нет связи", error=str(exc))
            report.append(entry)
        return report

    def stop_all(self) -> None:
        for robot in self.all():
            try:
                robot.stop()
            except Exception:  # noqa: BLE001 — на аварийной остановке глушим всё
                pass


def _monitors_enabled(cfg) -> list[str]:
    return [
        name
        for name, mon in cfg.robots.monitors.items()
        if mon.get("enabled", True) is not False
    ]


def build_fleet(cfg, clock, transport: str | None = None) -> Fleet:
    """Собрать флот по конфигу: `fake` — объекты в памяти, `http` — команды по сети."""
    transport = transport or cfg.get("robots.transport", "fake")
    if transport == "http":
        return _build_http(cfg)
    if transport != "fake":
        raise ValueError(f"неизвестный способ связи {transport!r}: бывает fake или http")
    return _build_fake(cfg, clock)


def _build_fake(cfg, clock) -> Fleet:
    move_time = float(cfg.get("sim.move_time", 1.2))
    rover = FakeRover(clock, cfg.cells.rover_start, move_time=move_time)
    vup = FakeVup(clock, cfg.cells.charge) if cfg.get("flags.use_vup", False) else None
    monitors = {}
    if cfg.get("flags.use_drones", False):
        for name in _monitors_enabled(cfg):
            monitors[name] = FakeDrone(clock, cfg.robots.monitors[name].pad, name=name)
    return Fleet(rover=rover, vup=vup, monitors=monitors, transport="fake")


def _build_http(cfg) -> Fleet:
    rover = HttpRobot(cfg.robots.rover.url, name="rover", role="rover")
    vup = (
        HttpRobot(cfg.robots.vup.url, name="vup", role="vup")
        if cfg.get("flags.use_vup", False)
        else None
    )
    monitors = {}
    if cfg.get("flags.use_drones", False):
        for name in _monitors_enabled(cfg):
            monitors[name] = HttpRobot(cfg.robots.monitors[name].url, name=name, role="drone")
    return Fleet(rover=rover, vup=vup, monitors=monitors, transport="http")
