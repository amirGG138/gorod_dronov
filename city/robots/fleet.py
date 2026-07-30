"""Сборка флота: аппараты в памяти или по сети.

Одно место, где решается, кем командовать. Диспетчер получает объекты с
одинаковыми методами и не знает, мок это, отдельная программа или живой борт.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from . import talk
from .base import RobotError
from .fake import FakeDrone, FakeRover, FakeVup, parse_verdict
from .http_robot import HttpRobot, wait_online

STOP_TIMEOUT = 8.0  # сколько ждать «стоп» от одного аппарата, с


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

    def stop_all(self) -> list[dict[str, Any]]:
        """Аварийная остановка всех аппаратов. Возвращает, кого удалось остановить.

        Два правила, оба выведены из того, что это аварийный путь:

        * ошибки не глушатся. Аппарат, не принявший «стоп», — это повод жать KILL
          SWITCH руками, и молчание здесь опаснее любого исключения. Отказ одного
          при этом не отменяет остановку остальных, поэтому он попадает в отчёт,
          а не наверх;
        * команды уходят параллельно. По сети каждая ждёт ответа секундами, а
          останавливать аппараты по очереди в аварии — это терять их друг за другом.
        """
        robots = self.all()
        report: list[dict[str, Any]] = [
            {
                "name": getattr(r, "name", "?"),
                "role": getattr(r, "role", "?"),
                "stopped": False,
                "error": f"аппарат не ответил на «стоп» за {STOP_TIMEOUT:g} с",
            }
            for r in robots
        ]

        def stop_one(entry: dict[str, Any], robot) -> None:
            try:
                robot.stop()
            except Exception as exc:  # noqa: BLE001 — отказ любого рода это «не остановлен»
                entry["error"] = str(exc)
            else:
                entry["stopped"] = True
                entry.pop("error", None)

        threads = [
            threading.Thread(target=stop_one, args=(entry, robot), daemon=True)
            for entry, robot in zip(report, robots)
        ]
        for t in threads:
            t.start()
        # Срок общий на всех: потоки стартовали вместе, значит и истекает он вместе,
        # а не по STOP_TIMEOUT на каждого по очереди.
        deadline = time.monotonic() + STOP_TIMEOUT
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        return report


def _monitors_enabled(cfg) -> list[str]:
    return [
        name
        for name, mon in cfg.robots.monitors.items()
        if mon.get("enabled", True) is not False
    ]


def build_fleet(cfg, clock, transport: str | None = None, log=None) -> Fleet:
    """Собрать флот по конфигу: `fake` — объекты в памяти, `http` — команды по сети.

    log — журнал попытки. Передан: каждая команда аппарату оставит в нём событие MSG
    (city/robots/talk.py), и обмен станет видно — этим живёт дашборд. Не передан:
    обвязки нет вовсе, поведение прежнее. Обвязка живёт ровно здесь потому, что это
    единственное место, где известны и все аппараты, и способ связи: диспетчер
    получает объекты с одинаковыми методами и не должен знать, кто их слушает.
    """
    transport = transport or cfg.get("robots.transport", "fake")
    if transport == "http":
        fleet = _build_http(cfg)
    elif transport == "fake":
        fleet = _build_fake(cfg, clock)
    else:
        raise ValueError(f"неизвестный способ связи {transport!r}: бывает fake или http")
    if log is not None:
        for robot in fleet.all():
            talk.attach(robot, log)
    return fleet


def _build_fake(cfg, clock) -> Fleet:
    move_time = float(cfg.get("sim.move_time", 1.2))
    scene = _scene(cfg)
    # Бортовой вердикт про огонь у понарошечных дронов ЗАДАЁТСЯ ключом
    # --sim-onboard-fire, а не считается: посчитанный тем же city/vision.py был бы
    # фальшивым вторым источником — расхождений в симуляции не бывает по построению.
    told = str(cfg.get("sim.onboard_fire", "") or "")
    verdict = parse_verdict(told) if told else None
    rover = FakeRover(clock, cfg.cells.rover_start, move_time=move_time)
    vup = FakeVup(clock, cfg.cells.charge, scene=scene) if cfg.get("flags.use_vup", False) else None
    monitors = {}
    if cfg.get("flags.use_drones", False):
        for name in _monitors_enabled(cfg):
            monitors[name] = FakeDrone(
                clock, cfg.robots.monitors[name].pad, name=name, scene=scene,
                fire_verdict=verdict,
            )
    return Fleet(rover=rover, vup=vup, monitors=monitors, transport="fake")


def _scene(cfg):
    """Нарисованный мир для кадров понарошечных дронов, или None без OpenCV.

    Диспетчер к нему не обращается: сцена — это то, что стоит на поле, а не то, что
    он знает. Он видит только кадры.
    """
    try:
        from .scene import SceneSpec

        return SceneSpec.from_config(cfg)
    except Exception:  # noqa: BLE001 — без картинок система обязана работать
        return None


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
