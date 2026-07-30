"""Обвязка сообщений: каждая команда аппарату оставляет след в журнале (событие MSG).

Зачем. Журнал писал РЕШЕНИЯ («выбран план тушения», «очаг в клетке [4,2]»), но не
сам обмен: по нему нельзя было ни нарисовать, кто с кем разговаривал, ни ответить
на вопрос «команда до ровера дошла или нет». MSG закрывает и то и другое: по нему
city/viz.py рисует стрелки между агентами, а разбор сбоя перестаёт быть гаданием.

Почему подмена методов на самом экземпляре, а не обёртка-прокси. Прокси — это
другой объект, и он ломает две вещи сразу: `isinstance(robot, HttpRobot)` в
Fleet.connect (там по нему решается, ждать ли борт при подключении) и обращения
вида `getattr(robot, "url", ...)`. Подкласс тоже не годится: у HttpRobot есть одна
точка входа `_request`, а у моков в памяти её нет вовсе — пришлось бы держать два
разных механизма для одного и того же. Подмена атрибутов оставляет тот же объект:
проверки типа живы, поля живы, а Fleet.all()/stop_all() ничего не знают.

Правило, которое здесь важнее остальных: запись в журнал НЕ ИМЕЕТ ПРАВА отменить
команду. Визуализация не главнее ровера, поэтому сбой журнала гасится, а команда
уходит. Исключение самой команды, наоборот, пробрасывается наверх как раньше —
диспетчер обязан его увидеть.
"""

from __future__ import annotations

import time
from typing import Any

DISPATCHER = "ДИСП"  # как диспетчер зовётся в ленте обмена

# Глагол -> (русская подпись, направление потока ИНФОРМАЦИИ).
#
# Направление именно информационное, а не «кто сделал HTTP-запрос». Кадр и вердикт
# про огонь запрашивает диспетчер, но содержимое летит ОТ борта, и на схеме обмена
# стрелка обязана смотреть от аппарата: иначе картинка будет утверждать, что
# диспетчер сам себе прислал детекцию.
VERBS: dict[str, tuple[str, str]] = {
    "takeoff": ("взлёт", "out"),
    "land": ("посадка", "out"),
    "look": ("точка обзора", "out"),
    "goto": ("перелёт", "out"),
    "trim": ("сдвиг прицела", "out"),
    "drive": ("переезд", "out"),
    "led": ("лента", "out"),
    "stop": ("стоп", "out"),
    "tell_fire": ("квадрат огня", "out"),
    "shot": ("кадр", "in"),
    "fire": ("вердикт про огонь", "in"),
}

# status() ЗДЕСЬ НЕТ НАМЕРЕННО, И ДОБАВЛЯТЬ ЕГО НЕЛЬЗЯ. Диспетчер опрашивает статус
# в каждом ожидании переезда, стоянки и состояния борта (_wait_cell, _hold,
# _wait_state) — десятки раз в секунду. Журнал, утонувший в опросах, перестаёт быть
# материалом техзащиты, а он именно им и является. Живость связи и так видна: по
# свежести последнего MSG и по полю link в статусе.

# Имена позиционных аргументов команд: в MSG кладётся «cell=[3,2]», а не «arg0».
SIGNS: dict[str, tuple[str, ...]] = {
    "takeoff": ("alt",),
    "look": ("xy", "alt"),
    "goto": ("cell", "alt"),
    "trim": ("fwd", "left"),
    "drive": ("cell", "fire", "fire_level"),
    "led": ("mode", "color"),
    "tell_fire": ("payload",),
}

# Что оставить от ответа аппарата. Ответы короткие, но в ленте нужна одна строка,
# а не весь статус.
ANSWER_KEYS = (
    "accepted", "cell", "found", "count", "level", "alt", "led",
    "cleared", "deduplicated", "known", "command",
)


def _short(value: Any) -> Any:
    """Значение, пригодное для JSONL: кортежи в списки, дроби покороче."""
    if isinstance(value, dict):
        return {k: _short(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_short(v) for v in value]
    if isinstance(value, float):
        return round(value, 2)
    return value


def _args(verb: str, args: tuple, kwargs: dict) -> dict | None:
    named = {n: v for n, v in zip(SIGNS.get(verb, ()), args) if v is not None}
    named.update({k: v for k, v in kwargs.items() if v is not None})
    if verb == "tell_fire":
        # Целиком payload здесь не нужен: он же лежит в событии FIRE_TARGET вместе
        # с причиной. В ленте обмена важно только, что именно ушло роверу.
        payload = named.get("payload") or {}
        named = {k: payload[k] for k in ("cell", "level", "clear") if k in payload}
    return _short(named) or None


def _answer(verb: str, result: Any) -> dict | None:
    if verb == "shot":
        # Кадр — это байты. В журнал идёт длина, а не картинка: сама она лежит
        # рядом в logs/shots, и путь к ней пишет событие SCAN.
        size = len(result) if isinstance(result, (bytes, bytearray)) else None
        return {"bytes": size}
    if not isinstance(result, dict):
        return None
    return _short({k: result[k] for k in ANSWER_KEYS if k in result}) or None


def _reason(label: str, name: str, direction: str, error: str) -> str:
    if error:
        return f"{label}: {name} не выполнил — {error}"
    return f"{label}: {name} принял команду" if direction == "out" else f"{label}: {name} ответил"


def _write(log, **fields: Any) -> None:
    """Запись обмена. Молча гасит свои сбои — см. правило в докстринге модуля."""
    try:
        log.ev("MSG", **fields)
    except Exception:  # noqa: BLE001 — журнал не вправе отменить команду аппарату
        pass


def _talking(call, verb: str, label: str, direction: str, name: str, who: str, log):
    frm, to = (who, name) if direction == "out" else (name, who)

    def talking(*args: Any, **kwargs: Any):
        started = time.monotonic()
        common = {"dir": direction, "frm": frm, "to": to, "verb": verb}
        try:
            result = call(*args, **kwargs)
        except Exception as exc:
            _write(
                log,
                **common,
                args=_args(verb, args, kwargs),
                ms=round((time.monotonic() - started) * 1000),
                ok=False,
                error=str(exc),
                reason=_reason(label, name, direction, str(exc)),
            )
            raise  # отказ аппарата обязан дойти до диспетчера, как и раньше
        _write(
            log,
            **common,
            args=_args(verb, args, kwargs),
            answer=_answer(verb, result),
            ms=round((time.monotonic() - started) * 1000),
            ok=True,
            reason=_reason(label, name, direction, ""),
        )
        return result

    talking.__name__ = verb
    talking.__doc__ = getattr(call, "__doc__", None)
    return talking


def attach(robot, log, who: str = DISPATCHER) -> list[str]:
    """Обвязать команды аппарата записью в журнал. Меняет сам экземпляр.

    Возвращает список обвязанных глаголов: у ровера не будет взлёта, у дрона —
    переезда, и это норма (аппарат реализует только свои методы, city/robots/base).
    Повторный вызов ничего не делает — иначе обвязка обвязала бы обвязку и каждая
    команда писалась бы дважды.
    """
    if getattr(robot, "_talks", False):
        return []
    name = getattr(robot, "name", "") or getattr(robot, "role", "аппарат")
    done: list[str] = []
    for verb, (label, direction) in VERBS.items():
        call = getattr(robot, verb, None)
        if not callable(call):
            continue
        setattr(robot, verb, _talking(call, verb, label, direction, name, who, log))
        done.append(verb)
    robot._talks = True
    return done
