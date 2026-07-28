"""Тот же контракт борта, но по сети.

Диспетчер об этом файле ничего не знает: методы называются так же, как у моков из
этапа 0, поэтому переезд на железо — это смена адреса в config.yaml, а не правка
логики миссий.

Только стандартная библиотека: на выданном ноутбуке может не оказаться ни pip, ни
интернета, а requests нам ничего не даёт — тут четыре типа запросов.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Sequence

from .base import RobotError

TIMEOUT = 3.0  # борт отвечает мгновенно: команда принимается, а не исполняется
RETRIES = 1  # одна повторная попытка — потеря пакета в Wi-Fi это норма
RETRY_PAUSE = 0.2


class HttpRobot:
    """Аппарат на другом конце сети. Роль узнаётся у него самого при подключении."""

    def __init__(self, url: str, name: str = "", role: str = "") -> None:
        self.url = url.rstrip("/")
        self.name = name or self.url
        self.role = role

    # --- транспорт ----------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        if method == "POST":
            # Один и тот же command_id на все попытки одной команды. Повторяем мы
            # молча, по потерянному ответу, — а борт по этому id узнаёт, что уже
            # исполняет её, и не издаёт второй navigate (второй взлёт).
            body = {**(body or {}), "command_id": uuid.uuid4().hex}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            req = urllib.request.Request(
                f"{self.url}{path}", data=data, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    payload = resp.read()
                return payload if raw else json.loads(payload or b"{}")
            except urllib.error.HTTPError as exc:
                # Отказ борта по существу («не соседняя клетка», «занят») повторять
                # бессмысленно — это ответ, а не потеря связи.
                detail = _explain(exc)
                raise RobotError(f"{self.name}: {method} {path} -> {exc.code} {detail}") from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last = exc
                if attempt < RETRIES:
                    time.sleep(RETRY_PAUSE)
        raise RobotError(f"{self.name}: нет связи с {self.url}{path} ({last})")

    # --- контракт -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        st = self._request("GET", "/status")
        if not self.role:
            self.role = st.get("role", "")
        return st

    def stop(self) -> dict[str, Any]:
        return self._request("POST", "/stop")

    def takeoff(self, alt: float) -> dict[str, Any]:
        return self._request("POST", "/takeoff", {"alt": float(alt)})

    def land(self) -> dict[str, Any]:
        return self._request("POST", "/land")

    def goto(self, cell: Sequence[int], alt: float) -> dict[str, Any]:
        return self._request("POST", "/goto", {"cell": [int(cell[0]), int(cell[1])], "alt": float(alt)})

    def shot(self) -> bytes:
        return self._request("GET", "/shot", raw=True)

    def drive(self, cell: Sequence[int]) -> dict[str, Any]:
        return self._request("POST", "/drive", {"cell": [int(cell[0]), int(cell[1])]})

    def led(self, mode: str, color: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"mode": mode}
        if color:
            body["color"] = color
        return self._request("POST", "/led", body)

    def __repr__(self) -> str:
        return f"HttpRobot({self.name} @ {self.url})"


def _explain(exc: urllib.error.HTTPError) -> str:
    """Вытащить человекочитаемую причину отказа из тела ответа."""
    try:
        body = json.loads(exc.read() or b"{}")
        return str(body.get("error") or body.get("reason") or exc.reason)
    except Exception:  # noqa: BLE001 — борт мог ответить не-JSON, причина не важнее связи
        return str(exc.reason)
    finally:
        exc.close()


def wait_online(robot: HttpRobot, seconds: float = 10.0) -> dict[str, Any]:
    """Дождаться, пока борт начнёт отвечать. Нужно при запуске: ROS поднимается небыстро."""
    deadline = time.monotonic() + seconds
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return robot.status()
        except RobotError as exc:
            last = exc
            time.sleep(0.3)
    raise RobotError(f"{robot.name}: борт не ответил за {seconds:g} с ({last})")
