# Отладка дронов-художников

> **Внимание:** этот документ описывает **curated**-путь художников (куратор
> рисует всё). Флагманский **studio**-поток (CHAT → CONVERGE → EXECUTE collab)
> описан в [`docs/painters.md`](painters.md); запускается через
> `make local-studio`. Запуски разбирай через
> `blackboard/runs/<id>/llm.jsonl`, включая записи `"kind":"parse"`
> (поле `parsed_ok`).

Инструкция для агента или человека: как разобрать один запуск `make up-painters`, почему
голосование/рисование пошло не так, и где лежат полные логи.

## Быстрый старт

```bash
# поднять стек
make up-painters

# дашборд
open http://localhost:8080   # или порт из compose

# логи контейнеров
docker compose -f docker-compose.painters.yml logs -f coordinator painter-1
```

Переменные в `.env` / compose:

| Переменная | Назначение |
|------------|------------|
| `RUN_LOG=1` | писать папку запуска в `blackboard/runs/` |
| `RUN_LOG_FULL=1` | в `llm.jsonl` — полный system/messages/response |
| `PAINT_BUILD_ROUNDS=2` | раунды фазы СБОРКА |
| `LLM_CONTEXT_TOKENS=32000` | окно контекста |
| `LLM_OUTPUT_CURATED=8192` | лимит ответа куратора при рисовании |

## Фазы (новый поток)

1. **PROPOSE (кирпичи)** — каждый дрон даёт *кусочек* картины (`BRICK`), не целый сюжет.
2. **BUILD (сборка)** — 2 раунда: дополняют общий черновик (`BUILD`), координатор склеивает в `collaborative.json`.
3. **CONVERGE (голос)** — голосуют за 1–3 *общих* финальных названия из `candidates`, не за «чужие сюжеты».
4. **EXECUTE** — рисование (куратор или слои).
5. **REPORT → DONE** — архив запуска в `runs/<run_id>/`.

На дашборде: панель «Совместная идея» + «Голосование».

## Где логи одного запуска

Координатор при INIT создаёт:

```
blackboard/runs/<run_id>/
  run.json          # метаданные (seed, painters, paint_mode)
  events.jsonl      # все SSE-события
  llm.jsonl         # каждый вызов LLM (если RUN_LOG_FULL=1 — полный промпт)
  turns.jsonl       # ходы агентов (line, fallback_used)
  messages/         # копия сообщений (в конце)
  collaborative.json
  decision.json
  phase.json
  summary.json      # итог при DONE
```

Указатель текущего запуска:

```bash
docker exec coordinator cat /blackboard/state/current_run.json
```

Читать из хоста (если volume смонтирован):

```bash
RUN=$(docker exec coordinator jq -r .dir /blackboard/state/current_run.json)
docker exec coordinator ls -la "$RUN"
docker exec coordinator tail -20 "$RUN/llm.jsonl"
docker exec coordinator jq . "$RUN/summary.json"
```

## Типичные проблемы

### 1. «Все проголосовали в круг» / странный победитель

Смотри `messages` фазы `CONVERGE` и `decision.json`:

```bash
docker exec coordinator jq . /blackboard/state/decision.json
```

- Победитель: сначала **число голосов** (`endorse_counts`), при ничьей — **сумма scores** из payload голосов, затем seed.
- В collaborative-режиме голос **не** отменяется как «за себя» — кандидаты общие.

В `llm.jsonl` ищи записи с `phase=CONVERGE` у painter-* — поле `endorse` в ответе LLM.

### 2. Дроны не обсуждают, а шлют шаблон

В `turns.jsonl` смотри `fallback_used: true` — LLM вернул мусор в `line`, сработал запасной текст.

Причины: утечка рассуждений в `line`, слишком длинный ответ, невалидный JSON.
Сырой ответ — в `llm.jsonl` → `response`.

### 3. Картина процедурная / «запасной план»

Ошибки LLM при **рисовании** попадают на дашборд («Ошибки рисования») только для контекстов:

- `curated_compose` — куратор рисует всё
- `stroke_compose` — план мазков художника

В `llm.jsonl`:

```bash
docker exec coordinator grep '"context":"curated_compose"' "$RUN/llm.jsonl" | tail -3
```

Частые причины: таймаут (`MODEL_TIMEOUT`, `CURATED_COMPOSE_TIMEOUT`), пустой JSON, обрезанный ответ (проверь `LLM_OUTPUT_CURATED`).

Процедурный fallback — `procedural_curated_layers(subject)` в `agent/roles/paint_shapes.py`.

### 4. Фаза зависла

```bash
docker exec coordinator jq . /blackboard/state/phase.json
```

Дедлайны в `agent/loop.py` → `deadlines`: propose 30s, build 45s, converge 30s, execute 120s.
Координатор переводит фазу при дедлайне или когда все дроны ответили.

Счётчики в thought координатора: `КИРПИЧИ: 3/4`, `Сборка 1/2`, `ГОЛОСОВАНИЕ: 2/4`.

### 5. Сборка пустая

```bash
curl -s http://localhost:8080/collaborative.json | jq .
```

Должны быть `bricks`, `draft`, `candidates`. Если `bricks` пуст — нет `BRICK` в messages.
Если `candidates` пуст до CONVERGE — BUILD не завершился.

## Полезные API дашборда

| URL | Содержимое |
|-----|------------|
| `/messages` | все сообщения доски |
| `/collaborative.json` | черновик и кандидаты |
| `/run.json` | текущий run_id и путь |
| `/state/decision.json` | итоговый subject |
| `/agents/painter-1/transcript` | мысли + чат одного дрона |

## Чеклист для другого агента

1. Прочитать `current_run.json` → открыть папку `runs/<id>/`.
2. `phase.json` — на какой фазе остановились.
3. `collaborative.json` — кирпичи, черновик, кандидаты.
4. `messages/*.json` или `/messages` — типы `BRICK`, `BUILD`, `VOTE`, `CONSENSUS`.
5. `turns.jsonl` — были ли fallback на переговорах.
6. `llm.jsonl` — сбои LLM; фильтр по `context` и `error`.
7. `events.jsonl` — `llm_error`, `stroke`, `decision`.
8. `summary.json` — финальный subject и число мазков.

## Перезапуск с чистой доской

```bash
docker compose -f docker-compose.painters.yml down
docker volume rm openclaw-stack_blackboard   # имя volume уточни: docker volume ls
make up-painters
```

Или `bb.reset_runtime` при рестарте агентов (очищает messages, collaborative, current_run pointer).

## Ключевые файлы кода

> **Рендер (новое).** В curated EXECUTE координатор шлёт события `shape`
> `{color, z, alpha, fill, polys:[[x,y]…], shape:{type,…}}`. Дашборд рисует их
> как SVG `<polygon>/<polyline>` в `#paintsvg`, сортируя по `z` (фон → перёд) —
> чистая картинка вместо спрей-каши. Состав художников (имя/цвет/техника/характер)
> генерится по seed в `agent/roles/personas.py` и публикуется в
> `config.yaml.json → roster`; `souls/painter-*.md` — лишь опциональный оверрайд.
> Подробный аудит и список багов: [`docs/audit-report.md`](audit-report.md).

| Файл | Роль |
|------|------|
| `agent/roles/personas.py` | seed-персоны (имя/цвет/техника/характер), N-динамично |
| `agent/run_log.py` | логирование запуска |
| `agent/roles/collaborative.py` | кирпичи → draft → candidates |
| `agent/roles/coordinator.py` | фазовая машина |
| `agent/roles/painter_agent.py` | `compose_brick`, `compose_build`, `compose_vote` |
| `agent/roles/painter.py` | шаги дрона по фазам |
| `agent/roles/studio_chat.py` | studio: свободный чат студии (done-консенсус) |
| `agent/roles/collab_paint.py` | studio: каждый дрон рисует свой цвет z-слоями |
| `agent/roles/ballot.py` | кластеризация голосов; write-in → явный abstain |
| `agent/roles/phase_util.py` | общие хелперы фазовой машины |
| `agent/llm_retry.py` | retry JSON только для рисования |
| `viz/index.html` | UI кирпичи/сборка/голос |
