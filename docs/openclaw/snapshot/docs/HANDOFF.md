# Project handoff — start here

> **This file was rewritten on 2026-07-02.** The previous handoff described the
> pre-audit state; its §4 "known issues" are all fixed and its architecture
> notes drifted. History lives in git; current truth is below and in the linked
> docs.

## What this repo is

**OpenClaw stack** — a multi-agent demo where drones coordinate **only through
a shared blackboard** (`agent/bb.py`: file-based locally, HTTP to a hub when
distributed; messages carry a board-global monotonic `seq`). A pluggable
`Brain` (`agent/brain.py`) supplies LLM reasoning: `mock` runs deterministically
with no key; the real provider in `.env` is `sverk` (vLLM gateway, model
`qwen35`). Four task flows on the same primitives:

1. **`safe_passage` — the city of drones.** Scouts negotiate the sector split
   in an open CHAT (claim/argue/trade, `agent/roles/scout_chat.py`), photograph
   their sectors, a rover crosses the certified map. `make local` / `make demo`.
2. **`painting` — the studio (flagship).** Free stigmergic chat → clustered
   ballot + enum-locked vote → each drone paints its own colour as z-layered
   shapes into one canvas. `make local-studio` / `make demo-studio`.
3. **`debate` — reusable decisions.** First-class `moderator` role, dynamic
   rounds, voting-only conclusion, write-ins resolve onto the ballot.
   `make local-debate`.
4. **`survey` — поиск груза (город дронов v2, added 2026-07-07).** Zone chat →
   per-turn JSON action plans over a 5×5 cell grid (fly_to/wait/photo_analyze,
   closed-loop pose) → FOUND verified by the other drones ONE AT A TIME
   (quorum; decoys rejected) → rover drives to the confirmed cell.
   `make local-survey` / `make demo-survey`, стенд `:8080/survey`,
   docs: `docs/survey.md`.

## Read next, in order

0. `docs/audit-2026-07-07.md` — the 2026-07-07 audit: the NTFS corruption
   incident (what was lost/recovered — READ THIS before touching `frontend/`),
   survey system verification, updated SOTA adoption plan.
1. `docs/audit-2026-07/README.md` — the full 2026-07 audit (what was broken).
2. `docs/audit-2026-07/IMPLEMENTED.md` — what was fixed, how it was verified
   (live sverk runs, canvases, gateway probes). The de-facto changelog.
3. `docs/HANDOFF-vllm-upgrade.md` — the next big task: gateway upgrade +
   LLM-layer overhaul (schemas on large calls, delete the regex repair).
4. `docs/` — architecture, protocol, running, configuration, per-topic.

## Ground rules that still hold

* **Verify on the real brain.** `mock` only exercises plumbing; every
  consensus/quality bug found so far was real-brain-only. After ANY change run
  the relevant `make local-*` flow on sverk and read
  `blackboard/runs/<id>/llm.jsonl` (`"kind":"parse"` records must show
  `parsed_ok:true`, transport errors 0).
* **Don't break the `shape` event contract** (`{color, z, alpha, fill, polys}`)
  — `frontend/src/Canvas.tsx` and `scripts/render_canvas.py` both composite by
  global z.
* **Single-writer discipline**: only the phase-machine owner (coordinator or
  moderator) writes `phase/decision/assignments`.
* Nothing here is committed until you commit it — check `git status`.

## Open items

* **Пауза на железе**: механизм паузы/замены АКБ готов и проверен на моке
  (`docs/pause.md`); осталось привязать `/land`/`/takeoff`/`/pose` в
  `bridge/ros2/bridge_node.py` к **переделанной ROS2-репе проекта** (с доп.
  функциями takeoff/land) — ждём ссылку на репозиторий от владельца.

* vLLM upgrade + LLM overhaul → `docs/HANDOFF-vllm-upgrade.md`.
* **TODO(crypto):** agent-to-agent payments (sector swaps, commissioned
  layers) — design sketch in `agent/roles/scout_chat.py`; needs a payment rail
  decision first.
* Multi-host `HttpBoard` end-to-end run (crash-loops fixed, ids hardened, but
  a real two-host session hasn't been exercised since).
* VLM on the gateway would unlock canvas-grounded painting
  (`docs/audit-2026-07/research-full.md` §8b).
