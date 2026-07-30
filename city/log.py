"""Лог решений: одна строка JSONL в файл + человекочитаемая строка в консоль.

Регламент §2.1 требует описать «формат логов решений»; отдельных баллов за них
нет, но без них нечем закрыть 30 баллов техзащиты за принятие решений агентами.
Отсюда правило: у каждого события, которое хоть что-то решает, есть поле reason
по-русски. Ключи событий и полей остаются английскими — их читает код.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any

# Все типы событий системы. Список закрытый: незнакомый тип — опечатка.
EVENT_TYPES = (
    "RUN_START",
    "ROBOT",
    "MSG",
    "SCAN",
    "COVERAGE",
    "FIRE_CHECK",
    "FIRE_SPOTTED",
    "FIRE_TARGET",
    "SURVEY",
    "PLAN_CHOSEN",
    "PLAN",
    "LLM",
    "CHARGED",
    "MOVE",
    "DWELL",
    "LED",
    "FIRE_CYCLE",
    "FIRE_EXTINGUISHED",
    "PERSON_FOUND",
    "VUP_ABSENT",
    "ENERGY_BLOCK",
    "SAFETY",
    "ERROR",
    "DONE",
)

# MSG — это ТРАНСПОРТ: кто кому какую команду отдал и сколько это заняло. Он
# нужен визуализации (city/viz.py рисует по нему стрелки между агентами) и
# отвечает на вопрос «дошло ли». О том, ПОЧЕМУ команда отдана, по-прежнему
# говорят события-решения: FIRE_CHECK, FIRE_TARGET, PLAN_CHOSEN и остальные.
# Разделение намеренное: грепом по FIRE_TARGET находится момент, когда ровер
# узнал цель, а среди пятидесяти MSG он бы утонул.
#
# Опрос /status в MSG НЕ ПИШЕТСЯ — см. city/robots/talk.py.
MSG_DIRECTIONS = ("out", "in")  # команда аппарату / ответ от аппарата


def _fmt_cell(cell: Any) -> str:
    if cell is None:
        return "-"
    return f"[{cell[0]},{cell[1]}]"


def _kv(payload: Any) -> str:
    """Короткие пары ключ=значение. Тела сообщений читают глазами, а не кодом."""
    if not isinstance(payload, dict):
        return "" if payload is None else str(payload)
    return " ".join(
        f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}"
        for k, v in payload.items()
    )


class Log:
    def __init__(self, clock, run_dir: str = "logs", echo: bool = True) -> None:
        self.clock = clock
        self.echo = echo
        os.makedirs(run_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(run_dir, f"run-{stamp}.jsonl")
        self._fh = open(self.path, "w", encoding="utf-8")
        self.counts: dict[str, int] = {}
        # Пишут несколько потоков: четыре монитора работают одновременно, каждый
        # в своём (этап 8), а аварийная остановка рассылает «стоп» всем аппаратам
        # параллельно (city/robots/fleet.py), и каждая команда теперь оставляет
        # запись MSG. Без замка строки JSONL склеиваются посреди слова — и ломается
        # ровно тот файл, который сдают как лог решений.
        self._lock = threading.Lock()

    def ev(self, type: str, **kw: Any) -> dict:
        if type not in EVENT_TYPES:
            raise ValueError(f"неизвестный тип события {type!r}")
        record = {"t": round(self.clock.now(), 2), "type": type}
        record.update(kw)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            self._fh.write(line)
            self._fh.flush()
            self.counts[type] = self.counts.get(type, 0) + 1
            if self.echo:
                print(self.human(record))
        return record

    # --- вывод в консоль ----------------------------------------------------

    @staticmethod
    def human(rec: dict) -> str:
        t, type_ = rec["t"], rec["type"]
        body = Log._body(type_, rec)
        reason = rec.get("reason")
        line = f"[{t:7.1f}с] {type_:<18} {body}"
        return f"{line}  — {reason}" if reason else line

    @staticmethod
    def _body(type_: str, r: dict) -> str:
        if type_ == "MSG":
            # Самый частый тип, поэтому проверяется первым. Стрелка направлена по
            # потоку ИНФОРМАЦИИ: «кадр» и «вердикт про огонь» летят от борта, хотя
            # HTTP-запрос делает диспетчер.
            line = f"{r.get('frm')} -> {r.get('to')}  {r.get('verb')}"
            args, answer = _kv(r.get("args")), _kv(r.get("answer"))
            if args:
                line += f" {args}"
            if answer:
                line += f" -> {answer}"
            return line + f"  {r.get('ms', 0)}мс" + ("" if r.get("ok", True) else "  ОТКАЗ")
        if type_ == "MOVE":
            return f"{_fmt_cell(r.get('from'))} -> {_fmt_cell(r.get('cell'))}  заряд={r.get('energy')}"
        if type_ == "DWELL":
            counted = "засчитано" if r.get("counted") else "НЕ ЗАСЧИТАНО"
            return (
                f"{_fmt_cell(r.get('cell'))} {r.get('seconds')}с лента={r.get('led')} "
                f"{counted}"
            )
        if type_ == "SCAN":
            if r.get("fire_cell"):
                seen = f"очаг {_fmt_cell(r.get('fire_cell'))} огоньков={r.get('fire_count')}"
            else:
                seen = "пусто"
            return (
                f"{r.get('drone')} точка ({r.get('xy', ['?', '?'])[0]}, {r.get('xy', ['?', '?'])[1]}) "
                f"привязка={r.get('anchor')} {seen}"
            )
        if type_ == "COVERAGE":
            seen, blind = r.get("seen") or [], r.get("blind") or []
            body = f"сняли: {', '.join(seen) or '—'}"
            if blind:
                body += f"; НЕ СНЯЛИ: {', '.join(blind)}"
            return f"{body}; клеток видно {r.get('cells_seen')}/{r.get('cells_total')}"
        if type_ == "FIRE_SPOTTED":
            return (
                f"{_fmt_cell(r.get('cell'))} голосов {r.get('votes')}/{r.get('total')} "
                f"огоньков={r.get('fire_count')} уровень={r.get('level')} "
                f"({r.get('level_source')})"
            )
        if type_ == "FIRE_CHECK":
            agree = r.get("agree")
            verdict = (
                "СОВПАЛО" if agree else ("РАСХОЖДЕНИЕ" if agree is False else "вердикта нет")
            )
            def seen(cell: Any, count: Any) -> str:
                # «x3» дописывается только когда огоньки сосчитаны: «xNone» в консоли
                # читается как ошибка, хотя «клетку вижу, счёт не вышел» — норма.
                return _fmt_cell(cell) + (f"x{count}" if count else "")

            return (
                f"{r.get('drone')} борт {seen(r.get('onboard_cell'), r.get('onboard_count'))}"
                f" / диспетчер {seen(r.get('my_cell'), r.get('my_count'))}  {verdict}"
                + (f" (заполнено: {r.get('filled')})" if r.get("filled") else "")
            )
        if type_ == "FIRE_TARGET":
            what = (
                "квадрат снят"
                if r.get("clear")
                else f"квадрат {_fmt_cell(r.get('cell'))} уровень={r.get('level')}"
            )
            got = "принят" if r.get("ok") else f"НЕ ДОШЁЛ ({r.get('error')})"
            return f"{what} -> ровер: {got}" + (f" [{r['via']}]" if r.get("via") else "")
        if type_ == "ROBOT":
            return f"{r.get('name')} ({r.get('role')}) {r.get('url')} {_fmt_cell(r.get('cell'))}"
        if type_ == "CHARGED":
            return f"+{r.get('units')} ед. (стоянка {r.get('seconds')}с)"
        if type_ == "PLAN_CHOSEN":
            return f"миссия={r.get('mission')}"
        if type_ == "LLM":
            if not r.get("ok"):
                verdict = "НЕ ОТВЕТИЛА"
            elif r.get("accepted") is None:
                verdict = "ответила"
            else:
                verdict = "предложение принято" if r.get("accepted") else "предложение отклонено"
            return f"{r.get('use')} {r.get('model')} {r.get('ms', 0) / 1000:.1f}с {verdict}"
        if type_ == "LED":
            return f"мигалка={r.get('mode')}"
        if type_ in ("FIRE_CYCLE", "FIRE_EXTINGUISHED", "PERSON_FOUND"):
            extra = " ".join(f"{k}={v}" for k, v in r.items() if k not in ("t", "type", "reason"))
            return extra
        if type_ == "DONE":
            return (
                f"миссии={','.join(r.get('missions', []))} "
                f"заряд потрачен={r.get('energy_spent')} остаток={r.get('energy_left')}"
            )
        return _kv({k: v for k, v in r.items() if k not in ("t", "type", "reason")})

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
