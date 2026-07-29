"""Шлюз к LLM/VLM. Модель предлагает — правила проверяют — код решает.

Регламент §2.1 требует использовать LLM/VLM и объяснять решения агентов; за это
дают 30 баллов техзащиты. Но модель не должна оказаться в цепи управления: она
советует, а принимает решение `city/rules.py`. Отсюда два железных правила этого
файла:

* **ни один метод не бросает исключение.** Нет ключа, нет сети, таймаут, кривой
  JSON, 500 от шлюза — всё это `Answer(ok=False)` с причиной по-русски. Прогон
  обязан идти дальше детерминированным путём, а не падать из-за чужого сервера;
* **ничего не выдумываем.** Провайдер `mock` умеет рассуждать о переданных ему
  числах, но кадры он не видит и детекцию не сочиняет — на вопрос по картинке он
  честно отвечает отказом. Придуманная детекция человека в окне это ноль за
  попытку и провал на техзащите.

Шлюз «Сверх» (docs/openclaw/03-zhelezo-api-i-boevye-grabli.md): OpenAI-совместимый
`https://ai.sverk.tech/v1`, ключ в `SVERK_API_KEY`. Модели у нашего ключа —
`deepseek-v4-pro` (текст) и `gemma4-vlm` (текст и картинки); `qwen35` из чужой
документации нашему ключу закрыт (HTTP 403 `key_model_access_denied`, проверено
29.07.2026).

Запросы уходят через `subprocess` + `curl`, а не `urllib`: на рабочем ноутбуке
`urllib` падает с `SSL: CERTIFICATE_VERIFY_FAILED` (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field as dc_field
from typing import Any

# Требовать русский приходится явно, иначе Qwen отвечает по-английски. Оговорка
# про ключи и координаты не украшение: без неё модель переводит "approach" в
# "подъезд" и ломает разбор ответа (docs/openclaw/03, грабли промптинга).
RU = (
    "Отвечай только по-русски: и рассуждения, и поле reason. "
    "НЕ переводи ключи JSON, значения enum, идентификаторы, имена клеток и числа — "
    "они читаются программой. Координата клетки записывается как [col, row], "
    "col и row целые, отсчёт с нуля."
)

# Ответы у нас короткие, но лимит считается вместе с размышлениями модели, если
# они всё-таки просочатся (см. ключи глушения в `_remote`). 1200 — запас на это,
# при котором ответ всё ещё успевает прийти до llm.timeout.
MAX_TOKENS = 1200
RETRY_PAUSE = 0.5


@dataclass
class Answer:
    """Результат одного обращения к модели — то, что уходит в лог событием LLM."""

    use: str  # plan | explain | see
    model: str
    ok: bool = False
    ms: int = 0
    data: dict = dc_field(default_factory=dict)
    text: str = ""
    error: str = ""


# --- схемы ответов ------------------------------------------------------------
#
# Схема не подсказка, а грамматика: по проверке авторов OpenClaw шлюз реально
# принуждает json_schema, тогда как json_object схемо-безразличен. Поэтому
# «попроси ответить JSON-ом» здесь не используется нигде.

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "approach": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
        },
        "charge_budget": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["approach", "charge_budget", "reason"],
    "additionalProperties": False,
}

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {"reason": {"type": "string"}},
    "required": ["reason"],
    "additionalProperties": False,
}

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {"type": "boolean"},
        "confidence": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["person", "confidence", "note"],
    "additionalProperties": False,
}

FIRE_SCHEMA = {
    "type": "object",
    "properties": {
        "fire": {"type": "boolean"},
        "confidence": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["fire", "confidence", "note"],
    "additionalProperties": False,
}


class Brain:
    """Разговор с моделью. Создаётся всегда, работает только при flags.use_llm."""

    def __init__(self, cfg) -> None:
        self.provider = str(cfg.get("llm.provider", "mock"))
        self.base = str(cfg.get("llm.base", "https://ai.sverk.tech/v1")).rstrip("/")
        self.key_env = str(cfg.get("llm.key_env", "SVERK_API_KEY"))
        self.model = str(cfg.get("llm.model", "deepseek-v4-pro"))
        self.vlm_model = str(cfg.get("llm.vlm_model", "gemma4-vlm"))
        self.timeout = float(cfg.get("llm.timeout", 30))
        self.enabled = bool(cfg.get("flags.use_llm", False))
        self._uses = {
            "plan": bool(cfg.get("llm.advise_plan", True)),
            "explain": bool(cfg.get("llm.explain", True)),
            "see": bool(cfg.get("llm.see", True)),
        }
        self.confirm_fire = bool(cfg.get("llm.confirm_fire", True))

    def wants(self, use: str) -> bool:
        """Включено ли это применение модели. Каждое гасится отдельно."""
        return self.enabled and self._uses.get(use, False)

    @property
    def key(self) -> str:
        return os.environ.get(self.key_env, "")

    def name(self, use: str) -> str:
        if self.provider == "mock":
            return "mock"
        return self.vlm_model if use == "see" else self.model

    # --- три применения -----------------------------------------------------

    def advise_plan(self, facts: dict) -> Answer:
        """Предложить клетку подъезда к пожару и бюджет предзарядки.

        Ответ ничего не решает: его проверяет rules.check_proposal, и при отказе
        работает детерминированный план.
        """
        question = (
            "Ты диспетчер соревнования «Город дронов». Ровер тушит пожар: он ездит "
            "за водой к башне и возвращается к горящему дому столько раз, каков "
            "уровень пожара. В саму клетку пожара въезжать нельзя — тушат с соседней. "
            "Игровой заряд: 1 секунда стоянки в зоне зарядки = 1 переезд в соседнюю "
            "клетку, на нуле ровер стоит.\n"
            f"Обстановка: {json.dumps(facts, ensure_ascii=False)}\n"
            "Выбери approach — клетку подъезда строго из списка candidates — и "
            "charge_budget: сколько единиц заряда набрать перед стартом. Меньше "
            "base_budget брать нельзя, больше вдвое — тоже (каждая единица это "
            "секунда попытки, а вся попытка 15 минут). Объясни выбор в reason."
        )
        return self._ask("plan", self.model, question, PLAN_SCHEMA)

    def explain(self, topic: str, facts: dict) -> Answer:
        """Короткое объяснение решения по-русски — материал для техзащиты."""
        question = (
            "Ты диспетчер соревнования «Город дронов». Объясни судье одним-двумя "
            f"предложениями решение «{topic}». Опирайся только на факты ниже, ничего "
            "не додумывай и не предлагай других действий.\n"
            f"Факты: {json.dumps(facts, ensure_ascii=False)}"
        )
        return self._ask("explain", self.model, question, EXPLAIN_SCHEMA)

    def see_person(self, jpeg: bytes, cell) -> Answer:
        """Есть ли человек в окне горящего здания. Кадр — вид сверху с монитора."""
        question = (
            "Это снимок игрового поля сверху с дрона-монитора. В клетке "
            f"{list(cell)} горит дом. Виден ли на снимке человек — фигурка человека "
            "в окне или рядом со зданием? Если не уверен, отвечай person=false и "
            "объясни в note, что именно мешает. Не выдумывай."
        )
        return self._ask("see", self.vlm_model, question, PERSON_SCHEMA, image=jpeg)

    def see_fire(self, jpeg: bytes) -> Answer:
        """Подтверждение очага на кадре. Клетку определяет vision.py, не модель."""
        question = (
            "Это снимок игрового поля сверху с дрона-монитора. Есть ли на нём очаг "
            "пожара — маленькая тёмно-красная фигурка «огонька» около 4-5 см? "
            "Крупные бледно-розовые области это цветные районы поля, а не очаг. "
            "Если не уверен, отвечай fire=false и объясни в note."
        )
        return self._ask("see", self.vlm_model, question, FIRE_SCHEMA, image=jpeg)

    # --- собственно вызов ---------------------------------------------------

    def _ask(
        self, use: str, model: str, question: str, schema: dict, image: bytes | None = None
    ) -> Answer:
        t0 = time.monotonic()
        ans = Answer(use=use, model=self.name(use))
        try:
            if self.provider == "mock":
                data, error = _mock_reply(use, question, image)
            elif self.provider == "sverk":
                data, error = self._remote(model, question, schema, image)
            else:
                data, error = None, (
                    f"неизвестный провайдер {self.provider!r}: бывает mock или sverk"
                )
        except Exception as exc:  # noqa: BLE001 — сбой модели не повод ронять попытку
            data, error = None, f"{type(exc).__name__}: {exc}"
        ans.ms = int((time.monotonic() - t0) * 1000)
        if data is None:
            ans.error = error
            return ans
        ans.ok = True
        ans.data = data
        ans.text = str(data.get("reason") or data.get("note") or "")
        return ans

    def _remote(
        self, model: str, question: str, schema: dict, image: bytes | None
    ) -> tuple[dict | None, str]:
        if not self.key:
            return None, (
                f"нет ключа {self.key_env}: модель недоступна, работаем без неё. "
                f"Поставьте ключ в окружение или переключитесь на llm.provider: mock"
            )
        content: Any = question
        if image is not None:
            content = [
                {"type": "text", "text": question},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64," + base64.b64encode(image).decode()
                    },
                },
            ]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": RU},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": schema},
            },
            # Три способа сказать «не думай вслух», потому что модели их понимают
            # по-разному, а лишние ключи шлюз молча игнорирует. Первые два — от
            # Qwen3 (docs/openclaw/03); `deepseek-v4-pro` слушается только третьего
            # (проверено 29.07.2026: без него он тратит на размышления 2000 токенов,
            # упирается в лимит и возвращает finish=length без ответа за 40-55 с,
            # с ним — 0 токенов размышлений и готовый JSON за 14 с).
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning": {"enabled": False},
        }
        body, error = self._curl(payload)
        if body is None:
            return None, error
        return _parse_reply(body)

    def _curl(self, payload: dict) -> tuple[dict | None, str]:
        """POST на шлюз. Повтор только на сетевой сбой: 4xx повторять бессмысленно."""
        cmd = [
            "curl", "-sS", "-m", str(int(self.timeout)),
            "-X", "POST", f"{self.base}/chat/completions",
            "-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {self.key}",
            "-w", "\n%{http_code}",
            "--data-binary", "@-",
        ]
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last = ""
        for attempt in range(2):
            try:
                proc = subprocess.run(
                    cmd, input=data, capture_output=True, timeout=self.timeout + 5
                )
            except subprocess.TimeoutExpired:
                last = f"модель не ответила за {self.timeout:g} с"
                time.sleep(RETRY_PAUSE)
                continue
            except FileNotFoundError:
                return None, "на этой машине нет curl — без него запросы к шлюзу не уходят"
            out = proc.stdout.decode("utf-8", "replace")
            text, _, code = out.rpartition("\n")
            if proc.returncode != 0 or not code.strip().isdigit():
                last = f"curl не дозвонился до {self.base}: {proc.stderr.decode('utf-8', 'replace').strip() or proc.returncode}"
                time.sleep(RETRY_PAUSE)
                continue
            status = int(code)
            if 400 <= status < 500:
                return None, f"шлюз отказал: HTTP {status} {_short(text)}"
            if status >= 500:
                last = f"шлюз ответил HTTP {status} {_short(text)}"
                time.sleep(RETRY_PAUSE)
                continue
            try:
                return json.loads(text), ""
            except json.JSONDecodeError:
                last = f"шлюз ответил не JSON-ом: {_short(text)}"
                time.sleep(RETRY_PAUSE)
        return None, last or "модель недоступна"


# --- разбор ответа ------------------------------------------------------------


def _short(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _parse_reply(body: dict) -> tuple[dict | None, str]:
    """Вытащить структурный ответ из OpenAI-совместимого тела."""
    try:
        choice = body["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, f"в ответе шлюза нет choices[0].message.content: {_short(json.dumps(body, ensure_ascii=False))}"
    if choice.get("finish_reason") == "length":
        return None, (
            "модель упёрлась в лимит токенов и не дошла до ответа: размышления "
            f"вслух съели весь бюджет {MAX_TOKENS} токенов"
        )
    data = _extract_json(content or "")
    if data is None:
        return None, f"ответ модели не разобрать как JSON: {_short(content or '')}"
    return data, ""


def _extract_json(text: str) -> dict | None:
    """Ответ бывает обёрнут в ```json ... ``` или в текст — достаём объект из него."""
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


# --- провайдер mock -----------------------------------------------------------


def _mock_reply(use: str, question: str, image: bytes | None) -> tuple[dict | None, str]:
    """Ответ без сети и без ключа: рассуждаем о числах, картинок не видим.

    Нужен затем, чтобы вся обвязка — промпты, проверка правилами, лог решений —
    работала и проверялась там, где интернета нет. Отказ на вопрос по кадру здесь
    принципиален: провайдер, который «увидел» человека, не видя картинки, — это
    выдуманная детекция.
    """
    if image is not None or use == "see":
        return None, (
            "провайдер mock кадры не видит и детекцию не выдумывает — "
            "для зрения нужен llm.provider: sverk и ключ"
        )
    facts = _extract_json(question) or {}
    if use == "plan":
        candidates = facts.get("candidates") or []
        if not candidates:
            return None, "в фактах нет ни одной клетки подъезда — предлагать нечего"
        budget = int(facts.get("base_budget", 0))
        return {
            "approach": list(candidates[0]),
            "charge_budget": budget,
            "reason": (
                f"подъезд с клетки {list(candidates[0])}: она свободна и ближе других "
                f"к башне {facts.get('tower')}, поэтому цикл «башня — пожар» короче. "
                f"Заряд {budget} ед. — это расчётный минимум с резервом"
            ),
        }, ""
    if use == "explain":
        return {
            "reason": "решение принято детерминированными правилами регламента; "
            f"исходные данные: {json.dumps(facts, ensure_ascii=False)}"
        }, ""
    return None, f"провайдер mock не умеет отвечать на «{use}»"


# --- проверка с площадки ------------------------------------------------------


def _load(path: str | None):
    from . import config as config_mod

    return config_mod.load(path or config_mod.CONFIG_PATH)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="city.brain", description="Проверка связи с моделью перед попыткой"
    )
    p.add_argument("--config", default=None, help="путь к config.yaml")
    p.add_argument("--provider", choices=("mock", "sverk"), help="чем отвечать")
    p.add_argument(
        "--ping",
        action="store_true",
        help="жива ли модель и валиден ли ключ (это же делается и без ключей)",
    )
    p.add_argument("--see", metavar="КАДР", help="спросить VLM про очаг на этом снимке")
    args = p.parse_args(argv)

    cfg = _load(args.config)
    cfg.override("flags.use_llm", True)
    if args.provider:
        cfg.override("llm.provider", args.provider)
    brain = Brain(cfg)

    if args.see:
        with open(args.see, "rb") as fh:
            ans = brain.see_fire(fh.read())
    else:
        ans = brain.explain("проверка связи", {"вопрос": "ответь одним словом «готов»"})

    print(f"провайдер {brain.provider}, модель {ans.model}, {ans.ms} мс")
    if ans.ok:
        print("ответ:", json.dumps(ans.data, ensure_ascii=False))
        return 0
    print("модель недоступна:", ans.error)
    return 1


if __name__ == "__main__":
    sys.exit(main())
