# Painters / Studio — collaborative painting

Painter drones decide **what** to paint by talking, then paint **one** shared
canvas. The flagship is the decentralized **studio**; two older paint modes
remain selectable. (This doc replaced the original "one layer per painter:
sky/water/light/foreground" design — that model and its fixed Aurora/Cobalt
roster are gone.)

## Run it

```bash
make local-studio      # flagship, real brain from .env → http://localhost:8080/studio
make demo-studio       # the same flow containerized
make local-collab      # collab painting without the studio chat (PROPOSE/BUILD path)
make demo-painters     # docker, curated mode (default PAINT_MODE)
make down-painters     # stop the docker stack
python3 scripts/render_canvas.py   # headless: rasterize the canvas to PNG
```

The in-page **"↻ New run"** button works in the local keep-alive stacks
(`make local-*`); in docker a rerun is `make demo-…` again.

> Mock (`MODEL_PROVIDER=mock`) exercises the plumbing deterministically, but the
> arguing, persuasion and vote dynamics only exist with a real model. Verify
> changes on the real brain and read `blackboard/runs/<id>/llm.jsonl`.

## Emergent personalities (no fixed roster)

Each painter's **name, pigment (named colour), technique, temperament and
creative leaning** are generated per run from `agent_id + paint_seed`
(`agent/roles/personas.py`), spread around the hue wheel so colours stay
distinct for **any number** of painters. The coordinator publishes the resolved
roster to `config.yaml.json` at INIT so every process agrees. A soul file
(`souls/painter-*.md`) is an *optional override*, not the source of identity —
the bundled souls are deliberately identity-free. `painter-7` on a Pi joins
with a generated persona, no file edits.

## The studio flow (flagship)

`INIT → CHAT → CONVERGE → EXECUTE(collab) → REPORT → DONE`

| Phase | What happens |
|---|---|
| CHAT | Free stigmergic chat (`agent/roles/studio_chat.py`). Each drone decides locally when to speak: it opens with its idea, replies when addressed by name or when new arguments landed, can open private threads, and posts `done` when convinced. The chat ends on **done-consensus** — everyone's latest message is `done` — not on a turn cap (`STUDIO_CHAT_TURNS` is only a runaway guard, `DEADLINE_CHAT` the hard stop). |
| CONVERGE | The facilitator derives candidates from the chat and **clusters near-duplicate subjects** into one ballot line each (`agent/roles/ballot.py` — separate lines for the same idea split its votes), ranks the ballot by the drones' final stances, and calls the vote. Ballots are **enum-locked** (sampler-enforced `json_schema`): a drone physically cannot vote off-ballot. Each drone's vote prompt carries its own final chat position, so the vote reflects the debate; the tally is per-voter (last vote wins) and an unmatched write-in is an explicit abstain. |
| EXECUTE | `PAINT_MODE=collab`: each drone composes and renders **its own colour** as z-layered filled shapes (`agent/roles/collab_paint.py`). The facilitator assigns a role/region per pigment hue (blue→water/sky, green→foliage, amber→sun …) and a z-slot; the drone's local z is namespaced `slot*1000 + local_z` so layers never interleave across drones. Shapes are clamped: sizes to `COLLAB_MAX_FRAC` of the canvas, line lengths capped, malformed numbers tolerated. `COLLAB_FREE=1` gives every drone the whole canvas (more expressive), `=0` keeps role regions (cleaner). |
| REPORT | The coordinator certifies the canvas (`result="Картина готова: …"`), exports the point cloud, finalizes the run log. |

The viz composites every `shape` event (`{color, z, alpha, fill, polys}`) by
global z into one picture — the composite IS the deterministic integrator; no
one draws over anyone's pixels.

## Paint modes

| `PAINT_MODE` | Who draws | Character |
|---|---|---|
| `curated` (default for `make demo-painters`) | The coordinator composes ALL colours after the debate (`coordinator_paint.py`); N-dynamic validator, layers per painter from the roster | Most coherent, painters are idea-givers |
| `collab` (the studio's mode) | **Each drone its own colour**, z-namespaced into one scene | Authorship + coherence |
| `distributed` | Each drone sprays freely through the bridge (`move`/`spray`) | Expressive, incoherent (kept as a baseline) |

The curated/brick path (`PROPOSE(bricks) → BUILD → CONVERGE`) still exists and
runs when `STUDIO_CHAT=0` — see `docs/debugging-painters.md` for its debugging
guide.

## Жюри — VLM-оценка картины (центральный экран)

Как только художники берутся за холст (EXECUTE), агент-критик (`roles/critic.py`,
душа `souls/critic.md` — «Вернисаж») каждые `CRITIC_INTERVAL` секунд (по
умолчанию 2) смотрит на картину и оценивает её красоту **от 1 до 100**; когда
картина готова — выносит **финальный вердикт** (оценка + комментарий, также
постится сообщением REPORT). Центральный экран — **`:8080/critic`**: живой
холст, крупный счёт с градусником и спарклайном, лента комментариев, финальный
вердикт растягивается на весь экран.

* «Камера»: в симуляции — рендер холста из shape/stroke-событий
  (`agent/raster.py`, чистый stdlib); на железе задайте `CRITIC_CAMERA_URL`
  (любой URL, отдающий кадр PNG/JPEG) — остальное не меняется.
* «Мозг» жюри: настоящий VLM через `brain.see()` — `VISION_PROVIDER`
  (anthropic/openai из коробки; sverk/ollama при заданном `MODEL_VISION`,
  например `qwen2.5-vl`, когда он появится на гейтвее). Без VLM — честная
  детерминированная эвристика (покрытие, разнообразие цветов, баланс), так что
  mock-демо работает без ключей.
* Отключить: `CRITIC=0` (локальные запуски) или убрать сервис `critic` из
  compose. Состояние: `state/critic.json` (score, comment, final, history).

## Key knobs

| Env | Default | Effect |
|---|---|---|
| `STUDIO_CHAT` | 0 (1 in studio targets) | decentralized studio chat on/off |
| `STUDIO_CHAT_TURNS` | 8 | per-drone runaway cap (not the normal stop) |
| `DEADLINE_CHAT` | 180 | max seconds for the chat phase |
| `PAINT_MODE` | curated | `curated` / `collab` / `distributed` |
| `COLLAB_LLM_SHAPES` | 1 | 1 = drones compose their own shapes; 0 = scene skeleton |
| `COLLAB_FREE` | 0 | 1 = whole-canvas freedom; 0 = role regions |
| `COLLAB_SHAPES` | 4 | target shapes per drone |
| `COLLAB_MAX_FRAC` | 0.5 | max shape extent as fraction of the canvas |
| `LLM_JSON_SCHEMA` | 1 | sampler-enforced JSON on chat turns + votes (0 = off) |
| `KEEP_ALIVE` | 0 | 1 = agents survive DONE (enables "New run") |
| `CRITIC` | 1 | VLM-жюри on/off (local launchers) |
| `CRITIC_INTERVAL` | 2 | секунд между оценками жюри |
| `VISION_PROVIDER` / `MODEL_VISION` | — | провайдер/модель зрения для оценок (иначе эвристика) |
| `CRITIC_CAMERA_URL` | — | реальная камера (URL кадра) вместо рендера холста |

## Fixture

`test_fixtures/painters-1/map.json` sets `mode: painting`, the canvas size and
an `inspiration` list (mood words the drones riff on — they are told NOT to
copy them verbatim). Add `test_fixtures/painters-2/…` and run
`PAINTERS_SCENARIO=painters-2 make demo-painters` or
`SCENARIO=painters-2 make local-studio`.

## Inspecting a run

- `blackboard/messages/*.json` — the chat (seq-ordered filenames);
- `blackboard/state/{phase,decision,collaborative}.json` — ballot, variants,
  stances, votes, verdict;
- `blackboard/runs/<id>/llm.jsonl` — every LLM call + `"kind":"parse"` records
  (`parsed_ok` per attempt), `turns.jsonl` — fallback usage;
- `scripts/render_canvas.py` — the canvas as PNG, sorted by global z.
