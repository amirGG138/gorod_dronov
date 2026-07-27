"""Загрузка конфигурации попытки.

Конфиг лежит в YAML, потому что его правят руками на площадке и комментарии там
важнее краткости. PyYAML при этом не обязателен: если его нет на выданном
ноутбуке (а интернета может не быть тоже), включается свой разбор того плоского
подмножества YAML, которым написан наш config.yaml. Парсер намеренно узкий и
падает на всём, чего не понимает, — молча угадывать он не должен.
"""

from __future__ import annotations

import os
from typing import Any

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")


class ConfigError(Exception):
    pass


# --- разбор нашего подмножества YAML ----------------------------------------


def _strip_comment(line: str) -> str:
    """Убрать комментарий, не тронув '#' внутри кавычек."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


def _split_top(text: str) -> list[str]:
    """Разбить '1, [2, 3]' по запятым верхнего уровня."""
    parts, depth, quote, buf = [], 0, "", ""
    for ch in text:
        if quote:
            if ch == quote:
                quote = ""
            buf += ch
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts]


def _scalar(text: str, lineno: int) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("["):
        if not text.endswith("]"):
            raise ConfigError(f"строка {lineno}: незакрытый список: {text!r}")
        inner = text[1:-1].strip()
        return [] if not inner else [_scalar(p, lineno) for p in _split_top(inner)]
    low = text.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text.startswith("-") or text.startswith("{") or text.startswith("&"):
        raise ConfigError(
            f"строка {lineno}: {text!r} — этой конструкции YAML мини-парсер не знает. "
            "Либо перепишите её блочными отображениями, либо поставьте PyYAML."
        )
    return text


def parse_mini_yaml(text: str) -> dict:
    """Блочные отображения по отступам + инлайновые списки. Больше ничего."""
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if ":" not in body:
            raise ConfigError(f"строка {lineno}: ожидалось 'ключ: значение', получено {body!r}")
        key, _, value = body.partition(":")
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1]
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigError(f"строка {lineno}: сбились отступы")
        parent = stack[-1][1]
        if value.strip():
            parent[key] = _scalar(value, lineno)
        else:
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def parse_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        return parse_mini_yaml(text)
    return yaml.safe_load(text)


# --- обёртка с доступом по точке ---------------------------------------------


class Config:
    """Словарь конфига с доступом cfg.cells.tower и cfg.get('flags.use_vup')."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError:
            raise AttributeError(f"в конфиге нет ключа {name!r}") from None
        return Config(value) if isinstance(value, dict) else value

    def __getitem__(self, key: str) -> Any:
        value = self._data[key]
        return Config(value) if isinstance(value, dict) else value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def items(self):
        for key in self._data:
            yield key, self[key]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return Config(node) if isinstance(node, dict) else node

    def override(self, dotted: str, value: Any) -> None:
        """Точечная правка из аргументов командной строки."""
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def to_dict(self) -> dict:
        return self._data

    def __repr__(self) -> str:
        return f"Config({self._data!r})"


def load(path: str = CONFIG_PATH) -> Config:
    with open(path, encoding="utf-8") as fh:
        data = parse_yaml(fh.read())
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидалось отображение верхнего уровня")
    return Config(data)
