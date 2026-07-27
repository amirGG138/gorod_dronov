# LLM-агент и MCP-сервер (`rover_agent_mcp`)

Это единственный известный пример того, как «Сверх» подключает языковую модель к аппарату. В документации `edu.sverk.tech` этого нет вообще.

## Схема

```text
/agent/text_command (std_msgs/String)
  → rover_agent_text_node
  → OpenAI-совместимый LLM API (native tool calls либо JSON-planner fallback)
  → rover_mcp_server, JSON-RPC POST http://127.0.0.1:8766/mcp
  → ROS 2 topics / services / actions
  → ровер
  → /agent/status (running) и /agent/answer (completed|error)
```

Модель **не получает** доступа к shell, файлам, ROS CLI или произвольным топикам. Единственный её интерфейс — 19 инструментов ниже. Это же свойство удобно для регламента: весь диалог «решение → действие» проходит через одну точку и уже сериализуется в JSON.

## Запуск

```bash
export OPENAI_BASE_URL=https://ai.sverk.io/v1     # или https://openrouter.ai/api/v1
export OPENAI_MODEL=qwen35                        # или deepseek/deepseek-v4-flash
export OPENAI_API_KEY=sk-...

ros2 launch rover_agent_mcp agent_mcp.launch.py \
  llm_api_key_env:=OPENAI_API_KEY \
  llm_model:=$OPENAI_MODEL \
  llm_base_url:=$OPENAI_BASE_URL \
  native_tool_mode:=auto
```

`llm_api_key_env` — **имя переменной окружения**, а не сам ключ. Частая ошибка: `llm_api_key_env:=$OPENAI_BASE_URL`.

`native_tool_mode`: `auto` (по умолчанию) пробует нативные tool calls модели, `false` принудительно включает JSON-планировщик — нужно для моделей со слабой поддержкой function calling.

Поддерживаются старые алиасы переменных: `OPENROUTER_API_KEY/MODEL/BASE_URL`, `SVERK_API_KEY/MODEL/BASE_URL`.

В составе полного стека агент поднимается вместе с остальным:

```bash
ros2 launch rover_bringup robot.launch.py profile:=agent   # только агент и мост
ros2 launch rover_bringup robot.launch.py profile:=full     # агент + железо + Nav2
```

Проверить связку с моделью без ровера можно обычным `curl` к `$OPENAI_BASE_URL/chat/completions` — отдельных тестовых нод в пакете нет.

## Параметры нод

`rover_agent_text_node` (значения по умолчанию берутся из окружения):

```text
robot_id (FLEET_ROBOT_ID, 'rover-01')       text_command_topic  status_topic  answer_topic
prompt_file (AGENT_PROMPT_FILE)             mcp_url (MCP_URL)   native_tool_mode
llm_base_url  llm_model  llm_api_key_env    app_title ('sverk-rover-agent')
timeout_s (LLM_TIMEOUT_SEC, 120)            max_tool_rounds (LLM_MAX_TOOL_ROUNDS, 8)
```

`max_tool_rounds: 8` — жёсткий потолок числа раундов «модель ↔ инструменты» на одну команду. Длинные сценарии надо укладывать в один `run_motion_sequence`, а не в восемь отдельных вызовов.

`rover_mcp_server` (через `ros_bridge`):

```text
cmd_vel_topic          /cmd_vel_test        led_set_state_service  /led_strip/set_state
led_state_topic        /led_strip/state     nav2_action_name       /navigate_to_pose
odom_topic             /odom                amcl_pose_topic        /amcl_pose
scan_topic             /scan_filtered
default_forward_distance_m 0.30             default_forward_speed_mps    0.12
default_lateral_speed_mps  0.10             default_angular_speed_degps  45.0
max_relative_distance_m    3.0              max_relative_turn_deg        720.0
max_drive_duration_s       40.0
motion_position_tolerance_m 0.025           motion_yaw_tolerance_deg     3.0
motion_command_rate_hz      20.0
```

Относительные перемещения ограничены 3 м и 720°, любое движение — 40 секундами. Точность закрытия по одометрии: 2.5 см и 3°.

## MCP endpoint

JSON-RPC 2.0 по `POST /mcp`. Методы: `initialize`, `tools/list`, `tools/call`. `GET /`, `/health`, `/mcp` возвращают health-check.

```bash
curl -s http://127.0.0.1:8766/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq

curl -s http://127.0.0.1:8766/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"set_led_preset","arguments":{"preset":"zima_blue"}}}' | jq
```

> Порт: README пакета и дефолт в коде говорят **8765**, но там сидит `rover_web`. Рабочий bringup поднимает MCP на **8766** (`components/agent.yaml`).

## Инструменты (19)

### Общие

| Инструмент | Аргументы | Что делает |
|---|---|---|
| `get_available_tools()` | — | Категории инструментов; ответ на «что ты умеешь?» |
| `wait(duration_s)` | 0…60, по умолч. 1.0 | Пауза внутри сценария |

### Светодиодная лента

| Инструмент | Аргументы |
|---|---|
| `set_led_strip(...)` | `enabled` (обяз.), `effect`, `brightness` 0…1 (0.35), `color` (`#16B8F3`), `secondary_color`, `effect_speed_hz` 0.05…20 |
| `set_led_preset(preset)` | один из пресетов ниже |
| `blink_led_strip(...)` | `color`, `times` 1…20 (3), `interval_s` 0.05…5 (0.35), `brightness`, `restore` = `off`\|`steady`\|`previous` |
| `get_led_strip_state()` | — |

```text
эффекты: fill, blink, blink_fast, fade, wipe, flash, rainbow, rainbow_fill
пресеты: off, idle, zima_blue, blue, cyan, green, red, white, yellow, purple,
         rainbow, thinking, navigation, manual_control, warning, blink_blue, success, error
```

Семантические пресеты (`thinking`, `navigation`, `success`, `error`, `warning`) — дешёвый способ показать судьям состояние агента без телеметрии.

### Относительное движение (mecanum)

| Инструмент | Аргументы |
|---|---|
| `drive_relative(forward_m, left_m, speed_mps, timeout_s)` | `+forward` вперёд, `+left` влево боком; можно диагональ |
| `turn_relative(angle_deg, angular_speed_degps, timeout_s)` | `+90` = налево, `−90` = направо |
| `stop_motion(cancel_navigation)` | мгновенный ноль в `/cmd_vel_test`, опционально отмена Nav2 |
| `drive_forward(distance_m, ...)` | алиас `drive_relative(forward_m=distance_m, left_m=0)` |

Движение закрывается **по `/odom`**, а не по времени: нода публикует скорость на 20 Гц и следит за фактическим смещением.

### Сценарии

`run_motion_sequence(steps, stop_on_error=true)` — главный инструмент для составных команд, от 1 до 20 шагов. Типы шагов:

```text
drive_relative, drive_forward, turn_relative, navigate_to_pose,
set_led_strip, set_led_preset, blink_led_strip, wait, stop_motion
```

```json
{
  "steps": [
    {"type": "drive_relative", "forward_m": 0.30, "left_m": 0.0, "speed_mps": 0.12},
    {"type": "turn_relative", "angle_deg": -90},
    {"type": "drive_relative", "forward_m": 0.0, "left_m": 0.20, "speed_mps": 0.10},
    {"type": "blink_led_strip", "color": "#16B8F3", "times": 3}
  ],
  "stop_on_error": true
}
```

Шаг `navigate_to_pose` внутри сценария по умолчанию ждёт результата действия Nav2 и продолжает сразу после `SUCCEEDED`/`ABORTED`/`CANCELED`; `timeout_s` работает только как страховка. Алиас `run_relative_sequence(steps)` оставлен для совместимости.

### Nav2

| Инструмент | Аргументы |
|---|---|
| `navigate_to_pose(x, y, yaw_deg, frame_id, wait_until_done, timeout_s)` | абсолютная цель, `frame_id` обычно `map`, `timeout_s` 60 |
| `cancel_navigation()` | — |
| `get_navigation_status()` | статус, последняя цель, feedback, поза |
| `is_navigation_ready()` | доступность action-сервера и позы |
| `get_robot_pose()` | приоритет источников: `/amcl_pose`, затем `/odom` |

### Диагностика

| Инструмент | Что возвращает |
|---|---|
| `get_laser_summary()` | минимальные дистанции спереди/слева/справа/сзади по `/scan_filtered` |
| `get_system_status()` | доступность LED-сервиса, action Nav2, `/odom`, `/amcl_pose`, `/scan`, состояния ленты. **Батарея намеренно не включена** |

## Промпты

Системный промпт задаётся файлом:

```bash
prompt_file:=$(ros2 pkg prefix rover_agent_mcp)/share/rover_agent_mcp/config/default_system_prompt.md
```

Готовые пресеты в том же каталоге: `preset_funny`, `preset_comedian`, `preset_elegant`, `preset_swearing_mechanic`, `preset_granny`, `preset_sarcastic`, `preset_pirate`, `preset_strict_engineer`. Базовый промпт заканчивает ответы фразой «Бип-буп.».

Пресеты меняют **только стиль финального ответа**. Имена инструментов, топиков и числовые параметры искажать нельзя — иначе ломается разбор вызовов.

## Формат сообщений

Вход — либо fleet-конверт, либо plain text (legacy):

```json
{"message_id": "0b0d3c49-…", "robot_id": "rover-01", "text": "проедь прямо 30 см"}
```

```bash
ros2 topic pub --once /agent/text_command std_msgs/msg/String \
  "{data: 'проедь прямо 30 сантиметров, потом вправо боком 20 и поморгай синим'}"
```

В LLM уходит **только `text`**. `message_id` сохраняется для корреляции, `robot_id` в ответах берётся из параметра ноды, а не из входящего сообщения — так испорченный payload с сервера не может подменить идентичность агента.

Выход:

```json
{"message_id":"…","robot_id":"rover-01","status":"running","text":"Команда получена локальным агентом."}
{"message_id":"…","robot_id":"rover-01","status":"completed","text":"Готово."}
```

При ошибке `status` = `error`. Подписка на оба топика (`ros2 topic echo /agent/status`, `/agent/answer`) даёт готовый журнал решений агента.
