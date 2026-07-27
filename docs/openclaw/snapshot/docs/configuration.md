# Configuration reference

All configuration is via environment variables (compose auto-loads `.env`; the
no-Docker mode also sources `.env`). Copy `.env.example` → `.env`.

## Identity & topology

| var | default | used by | meaning |
|---|---|---|---|
| `AGENT_ID` | — (required) | agent, bridge | unique id, e.g. `drone-1`, `rover`, `coordinator` |
| `ROLE` | — (required) | agent | `coordinator` \| `scout` \| `rover` \| `painter` \| `debater` \| `moderator` |
| `TASK` | `safe_passage` | agent | `safe_passage` \| `painting` \| `debate` |
| `BRIDGE_URL` | — | scout/rover | the robot's bridge, e.g. `http://bridge:9000` |
| `SOUL` | `./souls/<id>.md` | agent | path to the SOUL.md |
| `SCOUTS` | `drone-1..4` | coordinator | scout ids (fallback when no registry) |
| `ROVER` | `rover` | coordinator | rover id (fallback) |
| `SECTORS` | `A,B,C,D` | coordinator | sector ids to assign |
| `POLL_INTERVAL` | `1.0` | agent | loop cadence (seconds) |

## Blackboard / scenario

| var | default | meaning |
|---|---|---|
| `BLACKBOARD` | `./blackboard` | board root (a Docker volume in containers) |
| `FIXTURES` | `./test_fixtures` | scenario fixtures path |
| `SCENARIO` | `scenario-1` | which fixture set the bridges serve |
| `NAV_STEP_SEC` | `0.15` | simulated rover step time (pose streaming) |

## Convergence / quality

| var | default | meaning |
|---|---|---|
| `CONVERGENCE` | `score` | convergence rule: `score` \| `majority` \| `weighted` \| `coordinator` |
| `NOVELTY_MIN` | `0.3` | drop free-form messages below this information gain |
| `COVERAGE_MIN` | `0.9` | min per-sector coverage to count as covered |

## Chat phases (scout negotiation / painting studio)

| var | default | meaning |
|---|---|---|
| `SCOUT_CHAT` | `1` | safe_passage: scouts negotiate the sector split in an open CHAT; `0` = legacy PROPOSE/CONVERGE |
| `STUDIO_CHAT` | `0` | painting: free studio CHAT before the vote (`1` in `make local-studio` / `demo-studio`) |
| `STUDIO_CHAT_TURNS` | `8` | per-drone runaway cap on chat turns |
| `STUDIO_CHAT_MIN` | `1` | min chat turns each drone speaks before done-consensus counts |

## Painting / collab mode

| var | default | meaning |
|---|---|---|
| `PAINT_MODE` | `curated` | `curated` (coordinator paints all) \| `collab` (each drone paints its own colour, z-layered shapes) \| `distributed` (free spray) |
| `COLLAB_LLM_SHAPES` | `1` | collab: drones compose their shapes via the LLM (`0` = procedural skeleton only) |
| `COLLAB_FREE` | `0` | collab: `1` = the whole canvas is every drone's zone (no hard regions) |
| `COLLAB_SHAPES` | `4` | collab: target shapes per drone |
| `COLLAB_MAX_FRAC` | `0.5` | collab: max shape size as a fraction of canvas width |
| `COLLAB_COMPOSE_TIMEOUT` | `120` | collab: per-drone compose call timeout (s) |

## Phase deadlines (seconds)

| var | default | meaning |
|---|---|---|
| `DEADLINE_PROPOSE` / `BUILD` / `CONVERGE` | `90` / `150` / `90` | negotiation phases |
| `DEADLINE_EXECUTE` / `REPORT` | `240` / `90` | execution + reporting |
| `DEADLINE_CHAT` | `180` | the CHAT phase (scout negotiation / studio) |
| `DEADLINE_OPENING` / `DEBATE` / `FLOOR` / `VOTE` | `90` / `120` / `60` / `90` | debate phases + per-turn floor timeout |

## Debate

| var | default | meaning |
|---|---|---|
| `DEBATERS` | `debater-1,debater-2,debater-3` | participant ids (auto-discovered from the hub registry in distributed mode) |
| `DEBATE_TURNS` | `moderated` | `moderated` \| `round_robin` \| `parallel` |
| `DEBATE_MIN_ROUNDS` | `1` | floor on debate rounds |
| `DEBATE_MAX_ROUNDS` | `3` | ceiling on debate rounds |
| `DEBATE_RULE` | `majority` | `majority` \| `weighted` (by soul `vote_weight`) |
| `DEBATE_CONSENSUS` | `1.0` | stance share that ends the debate early (1.0 = unanimity) |

See [debate-system](debate-system.md).

## Survey (поиск груза)

| var | default | meaning |
|---|---|---|
| `SURVEY_CHAT` | `1` | zone negotiation chat before the sweep; `0` = round-robin zones |
| `SURVEY_CELLS_PER_TURN` | `2` | cells photographed per turn (fly→wait→photo per cell) |
| `SURVEY_WAIT_SEC` | `20` | flight-time model: seconds per cell hop («подождать 20 сек») |
| `SURVEY_WAIT_MAX` | `60` | cap on a single wait action |
| `WAIT_SCALE` | `1.0` | scales all waits (sim demos use `0.05`; hardware `1.0`) |
| `VERIFY_QUORUM` | `2` | yes-votes to confirm a find |
| `VERIFY_ALL` | `1` | every other drone verifies in turn before ruling |
| `VERIFY_LEG_SEC` | `240` | one verifier's timeout (skip is reversible — a late vote counts) |
| `SURVEY_STEAL` | `1` | finished drones take over a STALE neighbour's cells |
| `SURVEY_STALE_SEC` | `240` | owner heartbeat age that frees its zone for stealing |
| `SURVEY_MAX_ROUNDS` | `2` | EXECUTE reopen rounds for coverage gaps |
| `ZONES` | `Z1,Z2,Z3,Z4` | zone labels (cells come from the fixture or auto-split) |

See [survey](survey.md).

## Critic / жюри (painting)

| var | default | meaning |
|---|---|---|
| `CRITIC` | `1` | запускать VLM-жюри в painting-лаунчерах (`0` = без жюри) |
| `CRITIC_INTERVAL` | `2` | секунд между оценками (реальный VLM сам замедлит темп своей латентностью) |
| `VISION_PROVIDER` | = `MODEL_PROVIDER` | канал зрения: `anthropic` / `openai` / `sverk` / `ollama` |
| `MODEL_VISION` | — | VLM-модель (обязательна для sverk/ollama; напр. `qwen2.5-vl`) |
| `CRITIC_CAMERA_URL` | — | URL кадра реальной камеры; иначе рендер холста из событий |
| `CRITIC_PX` | `240` | разрешение рендера, подаваемого VLM |

Экран жюри: `:8080/critic`. Без VLM оценка — детерминированная эвристика
(покрытие/цвета/баланс), см. [painters](painters.md).

## Fleet / привязка (несколько команд в одной сети)

| var | default | meaning |
|---|---|---|
| `HANDLER_ID` | — | идентификатор хендлера (хаба) команды; едет в регистрации дронов |
| `FLEET` | из `TASK` | `city` \| `painter` — категория дронов и режим bridge-ноды |
| `BIND_FILE` | `/data/binding.json` | постоянная память привязки на борту |
| `BRIDGE_MODE` | = `FLEET` | режим единой ROS2-ноды (city \| painter) |
| `BRIDGE_FRAME` | `aruco_map` | кадр телеметрии/навигации — ВСЁ движение по aruco-маркерам поля |
| `TAKEOFF_BODY_FALLBACK` | `1` | аварийный body-подскок на взлёте, если маркеры с земли не видны |
| `CELL_SIZE_M` / `FIELD_ORIGIN_X/Y` | `0.8` / `0` | сетка клеток ↔ метры |
| `FLIGHT_ALT_M` / `PAINT_ALT_M` | `1.5` / `1.0` | рабочие высоты |
| `ROS2_MCP_URL` | `http://localhost:9092` | бортовой VLM (ros2_mcp) для `/analyze` |
| `SPRAY_ON_DEG` / `SPRAY_OFF_DEG` | `60` / `0` | серво краскопульта |

Страница регистрации: `:8080/fleet`. См. [fleet](fleet.md).

## Brain (LLM)

| var | default | meaning |
|---|---|---|
| `MODEL_PROVIDER` | `mock` | `mock` \| `sverk` \| `anthropic` \| `openai` \| `ollama` |
| `MODEL` | per-provider | model id; blank → provider default (`sverk`→`qwen35`, `anthropic`→`claude-opus-4-8`, `openai`→`gpt-4o-mini`, `ollama`→`qwen2.5:3b`) |
| `MODEL_TIMEOUT` | `45` | per-call timeout (seconds) |
| `MODEL_MAX_TOKENS` | `256` | max tokens per reasoning step (how much CoT streams) |

Structured output & retries:

| var | default | meaning |
|---|---|---|
| `LLM_JSON_SCHEMA` | `1` | sampler-enforced `response_format: json_schema` on small calls (chat turns, enum-locked votes); `0` = kill switch |
| `LLM_GUIDED_JSON` | `0` | legacy `json_object` mode; superseded by `LLM_JSON_SCHEMA` |
| `LLM_JSON_RETRIES` | `3` | attempts when a call must return valid JSON |
| `LLM_RETRY_WALL_SEC` | `300` | wall-clock cap on the whole retry loop (s) |
| `LLM_RETRY_RAW_CHARS` | `6000` | max chars of the bad raw reply echoed back per retry |
| `LLM_THINKING` | `0` | request model thinking on LLM calls |

Keys (only the one for your provider is needed; never baked into images):

| var | for |
|---|---|
| `SVERK_API_KEY` | sverk gateway |
| `SVERK_API_BASE` | sverk base URL (default `https://ai.sverk.tech/v1`) |
| `ANTHROPIC_API_KEY` | Anthropic |
| `OPENAI_API_KEY` / `OPENAI_API_BASE` | OpenAI-compatible |
| `OLLAMA_BASE` | Ollama (default `http://localhost:11434`) |

## Logging & lifecycle

| var | default | meaning |
|---|---|---|
| `RUN_LOG` | `1` | write a per-run folder under `blackboard/runs/` |
| `RUN_LOG_FULL` | `1` | log full system/messages/response per LLM call in `llm.jsonl` |
| `KEEP_ALIVE` | `0` | keep agents polling after DONE so `POST /rerun` can start a fresh run |

## Distributed / hub

| var | default | used by | meaning |
|---|---|---|---|
| `HUB_URL` | — | drone agent | central hub URL; **its presence selects `HttpBoard`** |
| `HUB_TOKEN` | — | hub + drones | shared Bearer token gating hub POSTs |
| `HUB_MODE` | `0` | hub server | `1` enables the write gateway (vs read-only dashboard) |
| `PORT` | `8080` (viz) / `9000` (bridge) | server | listen port |

## Notes

* In `.env`, set `MODEL=qwen35` exactly (the sverk gateway rejects `qwen-35`).
* For a real provider in Docker, agents need egress — `make demo-sverk` adds
  `docker-compose.egress.yml`; in distributed/drone compose the agents are on an
  egress-capable network already. See [security](security.md).
* `MODEL_MAX_TOKENS` trades reasoning depth for run speed: more tokens = longer
  visible thinking but slower phases.
