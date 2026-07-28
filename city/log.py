"""Лог решений: одна строка JSONL в файл + человекочитаемая строка в консоль.

Регламент §2.1 требует описать «формат логов решений»; отдельных баллов за них
нет, но без них нечем закрыть 30 баллов техзащиты за принятие решений агентами.
Отсюда правило: у каждого события, которое хоть что-то решает, есть поле reason
по-русски. Ключи событий и полей остаются английскими — их читает код.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

# Все типы событий системы. Список закрытый: незнакомый тип — опечатка.
EVENT_TYPES = (
    "RUN_START",
    "ROBOT",
    "SCAN",
    "FIRE_SPOTTED",
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


def _fmt_cell(cell: Any) -> str:
    if cell is None:
        return "-"
    return f"[{cell[0]},{cell[1]}]"


class Log:
    def __init__(self, clock, run_dir: str = "logs", echo: bool = True) -> None:
        self.clock = clock
        self.echo = echo
        os.makedirs(run_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(run_dir, f"run-{stamp}.jsonl")
        self._fh = open(self.path, "w", encoding="utf-8")
        self.counts: dict[str, int] = {}

    def ev(self, type: str, **kw: Any) -> dict:
        if type not in EVENT_TYPES:
            raise ValueError(f"неизвестный тип события {type!r}")
        record = {"t": round(self.clock.now(), 2), "type": type}
        record.update(kw)
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
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
        if type_ == "FIRE_SPOTTED":
            return (
                f"{_fmt_cell(r.get('cell'))} голосов {r.get('votes')}/{r.get('total')} "
                f"огоньков={r.get('fire_count')} уровень={r.get('level')} "
                f"({r.get('level_source')})"
            )
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
        return " ".join(
            f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}"
            for k, v in r.items()
            if k not in ("t", "type", "reason")
        )

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
