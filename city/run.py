"""Точка входа: python -m city.run --sim

Флаги закрывают то, что придётся менять на площадке в спешке, без правки
config.yaml: уровень и клетку пожара, наличие аппаратов.
"""

from __future__ import annotations

import argparse
import sys

from . import config as config_mod
from .clock import RealClock, SimClock
from .dispatcher import Dispatcher
from .field import Field
from .log import Log
from .robots.fleet import build_fleet


def _cell(text: str) -> list[int]:
    parts = text.replace("[", "").replace("]", "").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"клетка задаётся как col,row — получено {text!r}")
    return [int(parts[0]), int(parts[1])]


def _sim_cell(text: str) -> list[int] | str:
    """Клетка для нарисованного мира или слово «нет» — поле вовсе без очага."""
    if text.strip().lower() in ("нет", "none", "-"):
        return "none"
    return _cell(text)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="city.run", description="Диспетчер «Города дронов»")
    p.add_argument("--config", default=config_mod.CONFIG_PATH, help="путь к config.yaml")
    p.add_argument("--sim", action="store_true", default=True, help="виртуальное время (по умолчанию)")
    p.add_argument("--real", dest="sim", action="store_false", help="реальное время")
    p.add_argument("--drones", dest="drones", action="store_true", default=None)
    p.add_argument("--no-drones", dest="drones", action="store_false")
    p.add_argument("--vup", dest="vup", action="store_true", default=None)
    p.add_argument("--no-vup", dest="vup", action="store_false")
    # Бортовой вердикт про огонь — роскошь, а не звено управления: он сверяется со
    # своим разбором кадра и умеет только закрыть дырку. Выключается, если на
    # площадке борт от лишнего OpenCV начнёт терять метку под камерой.
    p.add_argument("--onboard-fire", dest="onboard_fire", action="store_true", default=None,
                   help="спрашивать у бортов их собственный вердикт про огонь (по умолчанию да)")
    p.add_argument("--no-onboard-fire", dest="onboard_fire", action="store_false",
                   help="не спрашивать борта: разбор кадров только у диспетчера")
    p.add_argument("--tell-rover-fire", dest="tell_rover_fire", action="store_true", default=None,
                   help="сообщать роверу квадрат огня (по умолчанию да)")
    p.add_argument("--no-tell-rover-fire", dest="tell_rover_fire", action="store_false",
                   help="не сообщать роверу квадрат огня")
    p.add_argument("--llm", dest="llm", action="store_true", default=None)
    p.add_argument("--no-llm", dest="llm", action="store_false")
    p.add_argument(
        "--llm-provider",
        choices=("mock", "sverk"),
        help="чем отвечает модель: mock — сама, без сети и ключа; sverk — живой шлюз",
    )
    p.add_argument("--llm-model", help="какую текстовую модель спрашивать, например qwen35")
    p.add_argument(
        "--net",
        action="store_true",
        help="командовать аппаратами по сети (моками или живыми бортами); включает реальное время",
    )
    p.add_argument("--monitors", help="какие дроны участвуют, например m1 или m1,m3")
    p.add_argument("--rover-url", help="адрес ровера, например http://192.168.1.50:8010")
    p.add_argument("--drone-url", help="адрес первого дрона-монитора (m1)")
    p.add_argument("--fire-cell", type=_cell, help="клетка пожара, например 4,2")
    p.add_argument("--fire-level", type=int, help="уровень пожара = число поездок за водой")
    p.add_argument(
        "--sim-fire-cell",
        type=_sim_cell,
        help="куда поставить очаг в НАРИСОВАННОМ мире (только с --sim --drones): "
        "проверка, что диспетчер верит кадрам, а не config.yaml. "
        "«нет» — поле без очага, проверка честного отказа разведки",
    )
    p.add_argument(
        "--sim-fire-count",
        type=int,
        help="сколько огоньков положить в НАРИСОВАННОМ мире (только с --sim --drones): "
        "проверка, что уровень пожара тоже считается по кадрам, а не берётся из config.yaml",
    )
    p.add_argument(
        "--sim-onboard-fire",
        help="ЗАДАННЫЙ бортовой вердикт про огонь у понарошечных дронов, например "
        "4,2x3 или «нет» (только с --sim --drones). Вердикт задаётся, а не считается: "
        "посчитанный тем же city/vision.py был бы фальшивым вторым источником. Так "
        "проверяются обе ветки сверки — согласие и расхождение",
    )
    p.add_argument("--logs", default="logs", help="каталог для лога попытки")
    p.add_argument("--quiet", action="store_true", help="не печатать таймлайн в консоль")
    return p


def apply_args(cfg, args) -> None:
    for flag, key in (
        ("drones", "flags.use_drones"),
        ("vup", "flags.use_vup"),
        ("llm", "flags.use_llm"),
        ("onboard_fire", "flags.ask_onboard_fire"),
        ("tell_rover_fire", "flags.tell_rover_fire"),
    ):
        value = getattr(args, flag)
        if value is not None:
            cfg.override(key, value)
    if args.net:
        cfg.override("robots.transport", "http")
    if args.llm_provider:
        cfg.override("llm.provider", args.llm_provider)
    if args.llm_model:
        cfg.override("llm.model", args.llm_model)
    if args.monitors:
        chosen = {name.strip() for name in args.monitors.split(",")}
        unknown = chosen - set(cfg.robots.monitors)
        if unknown:
            raise SystemExit(f"нет такого дрона: {', '.join(sorted(unknown))}")
        for name in cfg.robots.monitors:
            cfg.override(f"robots.monitors.{name}.enabled", name in chosen)
    if args.rover_url:
        cfg.override("robots.rover.url", args.rover_url)
    if args.drone_url:
        cfg.override("robots.monitors.m1.url", args.drone_url)
    if args.fire_cell:
        cfg.override("scenario.fire.cell", args.fire_cell)
    if args.fire_level is not None:
        cfg.override("scenario.fire.level", args.fire_level)
    if args.sim_fire_cell:
        cfg.override("sim.fire_cell", args.sim_fire_cell)
    if args.sim_fire_count is not None:
        cfg.override("sim.fire_count", args.sim_fire_count)
    if args.sim_onboard_fire:
        cfg.override("sim.onboard_fire", args.sim_onboard_fire)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_mod.load(args.config)
    apply_args(cfg, args)

    # По сети время всегда настоящее: ускорять его бессмысленно, ждать всё равно
    # придётся столько, сколько летит дрон и едет ровер.
    clock = RealClock() if (args.net or not args.sim) else SimClock()
    log = Log(clock, run_dir=args.logs, echo=not args.quiet)
    try:
        field = Field.from_config(cfg)
        # log в build_fleet включает обвязку сообщений: каждая команда аппарату
        # оставит событие MSG, и обмен станет видно в журнале и на дашборде.
        fleet = build_fleet(cfg, clock, log=log)
        code = Dispatcher(cfg, field, log, clock, fleet).run()
    finally:
        log.close()
    if not args.quiet:
        print(f"\nлог попытки: {log.path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
