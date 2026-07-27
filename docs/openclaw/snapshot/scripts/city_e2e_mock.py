#!/usr/bin/env python3
"""One-command MOCK end-to-end for city_missions (Город дронов, Архипелаг 2026).

Runs a full autonomous attempt against the city-1 fixture with NO robots and NO
LLM: plan mission order -> extinguish a level-N fire (N water cycles, 3 s LED
dwells) -> deliver a package (5 s load, escort ≤2 cells behind, no route through
an active fire) -> check it fits the 15-minute budget. Prints a replayable
evidence timeline and PASS/FAIL.

    python3 scripts/city_e2e_mock.py                 # city-1 fixture
    python3 scripts/city_e2e_mock.py test_fixtures/city-1/map.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from roles.city_world import load_world           # noqa: E402
from roles.city_executor import run_attempt        # noqa: E402


def main(argv):
    fx = Path(argv[1]) if len(argv) > 1 else ROOT / "test_fixtures" / "city-1" / "map.json"
    sm = json.loads(fx.read_text())
    world = load_world(sm)
    print(f"=== city_missions mock E2E — {sm.get('name', fx.stem)} "
          f"({world.w}×{world.h}, cell {world.cell_size_m} m) ===")
    print(f"fire={world.fire_cell} level={world.fire['level']}  "
          f"water={world.water_tower}  charge={world.charge_zone}  "
          f"delivery={world.delivery['pickup']}→{world.delivery['dropoff']}")
    res = run_attempt(world)

    print(f"\nmission order: {res['order']}")
    print("--- evidence timeline ---")
    for e in res["log"]:
        t = e.get("type")
        if t == "MISSION_ORDER":
            print(f"  plan: {e['order']}  ({e['reasons'].get('constraint','независимы')})")
        elif t == "CHARGED":
            print(f"  🔋 charged {e['seconds']}s -> energy {e['energy']}")
        elif t == "ACTION_COMPLETED":
            ev = e["evidence"]
            extra = (f"dwell {ev.get('stationary_seconds')}s led={ev.get('led')} "
                     f"counted={ev.get('counted')}" if "stationary_seconds" in ev
                     else (f"cycle {ev.get('cycle')}/{ev.get('of')}" if "cycle" in ev
                           else f"escort_lag≤{ev.get('escort_max_lag')}"))
            print(f"  ✓ {e['action_id']:22} @{ev.get('cell')}  {extra}")
        elif t == "PERSON_FOUND":
            print(f"  🧑 person found @{e['cell']} window={e['window']} (safety_drone)")
        elif t == "FIRE_EXTINGUISHED":
            print(f"  🔥→💧 fire OUT @{e['cell']} after {e['cycles']} cycles")
        elif t == "ESCORT_LAUNCHED":
            print(f"  🚁 escort launched @{e['drone_cell']}")
        elif t == "DELIVERY_DONE":
            print(f"  📦 delivered @{e['cell']} (escort max lag {e['escort_max_lag']})")
        elif t in ("ESCORT_VIOLATION", "SAFETY_VIOLATION", "REPLAN_NEEDED"):
            print(f"  ⚠ {t}: {e.get('reason') or e.get('lag')}")

    fire_ok = res["fire_ok"] is True
    del_ok = res["delivery_ok"] is True
    checks = [
        ("mission order chosen", bool(res["order"])),
        ("fire extinguished (level cycles)", fire_ok),
        ("person found by safety drone", res["person_found"] is True),
        ("delivery arrived", del_ok),
        ("no route through active fire", res["blocked"] is None),
        ("energy never negative", res["final_energy"] >= 0),
        (f"within 15 min ({res['sim_time_s']}s)", res["within_time"]),
    ]
    print("\n--- acceptance ---")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print(f"\n{'✅ E2E PASS' if ok else '❌ E2E FAIL'}  (sim time {res['sim_time_s']}s, "
          f"final energy {res['final_energy']})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
