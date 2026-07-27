#!/usr/bin/env python3
"""Налить testnet TON на facilitator — единственный кошелёк, который нельзя
пополнить изнутри стека (admin ему потом доливает сам bootstrap).

    python3 scripts/ton_faucet.py              # показать баланс и дефицит
    python3 scripts/ton_faucet.py --claim      # запросить у фаусета Chainstack
    python3 scripts/ton_faucet.py --claim --watch   # долить за несколько суток

Фаусету нужен ключ: CHAINSTACK_API_KEY (бесплатная регистрация на
console.chainstack.com, ключ там же). Без ключа фаусеты не наливают — это их
защита от сибил-атак, обойти её нечем и не нужно: скрипт просто покажет, куда
и сколько перевести руками.

Порог берётся из кода бутстрапа, а не с потолка:
  FACILITATOR_RESERVE_NANO   = 1.2 TON  (остаётся на расчёты фасилитатора)
  INITIAL_ADMIN_TARGET_NANO  = 0.63 TON (уходит на admin при fund-admin)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_TON = ROOT / ".env.ton"
IMAGE = "archipelago-payments:local"

NANO = 1_000_000_000
# 1.2 резерва + 0.63 админу + запас на комиссии внешних сообщений
TARGET_NANO = 1_900_000_000
CHAINSTACK_URL = "https://api.chainstack.com/v1/faucet/ton-testnet"
CLAIM_COOLDOWN_H = 24  # Chainstack: 1 TON раз в 24 часа


def die(msg: str, code: int = 1) -> None:
    print(f"!! {msg}", file=sys.stderr)
    raise SystemExit(code)


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        die(f"нет {path.name}. Создай кошельки:\n"
            f"   docker run --rm -v \"$(pwd):/workspace\" -w /workspace {IMAGE} \\\n"
            f"     python -m payments.ton_wallets")
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def facilitator_address() -> str:
    """Адрес деривится из мнемоники внутри образа — мнемоника наружу не выходит."""
    out = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{ROOT}:/workspace", "-w", "/workspace",
         IMAGE, "python", "-m", "payments.ton_wallets"],
        capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        die(f"не удалось получить адрес facilitator:\n{out.stderr.strip()[:400]}")
    for line in out.stdout.splitlines():
        if line.startswith("facilitator="):
            return line.split("=", 1)[1].strip()
    die(f"payments.ton_wallets не напечатал facilitator=:\n{out.stdout[:300]}")
    raise AssertionError  # недостижимо, для тайпчекера


def balance_nano(address: str, provider: str, api_key: str) -> int:
    url = f"{provider.rstrip('/')}/api/v2/getAddressBalance?address={address}"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            die("toncenter ограничил запросы — подожди минуту или задай "
                "TONCENTER_API_KEY в .env.ton")
        die(f"toncenter вернул HTTP {e.code}: {e.read()[:200].decode(errors='replace')}")
    except Exception as e:  # noqa: BLE001
        die(f"toncenter недоступен: {e}")
    if not body.get("ok"):
        die(f"toncenter: {str(body)[:200]}")
    return int(body["result"])


def claim(address: str, key: str) -> tuple[bool, str]:
    """True = фаусет принял заявку. False = отказ, вторым полем причина."""
    req = urllib.request.Request(
        CHAINSTACK_URL,
        data=json.dumps({"address": address}).encode(),
        headers={"authorization": f"Bearer {key}",
                 "content-type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode(errors="replace")
        try:
            return True, json.loads(body).get("url", body)[:300]
        except json.JSONDecodeError:
            return True, body[:300]
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        reason = {
            400: "фаусет не принял адрес",
            401: "CHAINSTACK_API_KEY недействителен",
            403: "ключ отвергнут (недействителен или заблокирован Cloudflare)",
            429: f"лимит исчерпан — следующая заявка через ~{CLAIM_COOLDOWN_H}ч",
        }.get(e.code, f"HTTP {e.code}")
        return False, f"{reason}: {detail}"
    except Exception as e:  # noqa: BLE001
        return False, f"фаусет недоступен: {e}"


def fmt(nano: int) -> str:
    return f"{nano / NANO:.3f} TON"


def manual_hint(address: str, deficit: int) -> None:
    print(f"\nНалить руками {fmt(deficit)} на:\n  {address}\n")
    print("  · @testgiver_ton_bot в Telegram — 2 TON за раз, но там капча,")
    print("    её проходит только человек (обходить не буду и не надо)")
    print("  · faucet.chainstack.com/ton-testnet-faucet — 1 TON / 24ч")
    print("  · faucet.tonxapi.com — 1 раз / 12ч")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claim", action="store_true",
                    help="запросить монеты у Chainstack (нужен CHAINSTACK_API_KEY)")
    ap.add_argument("--watch", action="store_true",
                    help="повторять заявки, пока не наберётся порог (сутки между попытками)")
    ap.add_argument("--target", type=float, default=TARGET_NANO / NANO,
                    help=f"целевой баланс в TON (по умолчанию {TARGET_NANO / NANO})")
    args = ap.parse_args()

    env = read_env(ENV_TON)
    provider = env.get("TON_PROVIDER_URL") or "https://testnet.toncenter.com"
    if "testnet" not in provider:
        die(f"TON_PROVIDER_URL={provider} — это не testnet, отказываюсь")
    if (env.get("TON_NETWORK") or "tvm:-3") != "tvm:-3":
        die(f"TON_NETWORK={env.get('TON_NETWORK')} — демо только testnet (tvm:-3)")

    target = int(args.target * NANO)
    api_key = env.get("TONCENTER_API_KEY", "")
    addr = facilitator_address()
    print(f"facilitator: {addr}")

    have = balance_nano(addr, provider, api_key)
    print(f"баланс:      {fmt(have)}   нужно: {fmt(target)}")
    if have >= target:
        print("\n✅ хватает. Дальше:  make ton-jton-bootstrap && make payments-ton-demo")
        return 0

    deficit = target - have
    print(f"дефицит:     {fmt(deficit)}")

    if not args.claim:
        manual_hint(addr, deficit)
        print("\nИли с ключом:  CHAINSTACK_API_KEY=... python3 scripts/ton_faucet.py --claim")
        return 1

    key = os.environ.get("CHAINSTACK_API_KEY", "").strip()
    if not key:
        die("нужен CHAINSTACK_API_KEY (console.chainstack.com → API keys).\n"
            "   Фаусеты не наливают анонимно — это их анти-сибил.")

    while True:
        ok, detail = claim(addr, key)
        print(f"\nфаусет: {'принял' if ok else 'отказал'} — {detail}")
        if ok:
            print("жду зачисления (до 3 мин)…")
            for _ in range(18):
                time.sleep(10)
                have = balance_nano(addr, provider, api_key)
                if have >= target:
                    print(f"✅ {fmt(have)} — хватает. "
                          "Дальше: make ton-jton-bootstrap && make payments-ton-demo")
                    return 0
            print(f"текущий баланс {fmt(have)}, ещё нужно {fmt(target - have)}")
        if not args.watch:
            manual_hint(addr, max(0, target - have))
            return 1
        print(f"следующая попытка через {CLAIM_COOLDOWN_H}ч "
              "(Ctrl-C чтобы бросить; прогресс на блокчейне не потеряется)")
        time.sleep(CLAIM_COOLDOWN_H * 3600)


if __name__ == "__main__":
    sys.exit(main())
