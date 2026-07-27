# Межагентная связь: MQTT-мост флота (`fleet_text_bridge_ros2`)

Мост между MQTT-брокером и ROS 2. В документации «Сверх» аналог описан только для legacy-стека Clover (ESP-NOW + `skyros`); для ROS 2 это единственная известная реализация.

Зависимость: `python3-paho-mqtt`. Пакет **не имеет YAML-конфига по умолчанию** — идентичность и адрес сервера читаются из переменных окружения (либо переопределяются параметрами ноды через bringup).

## Запуск

```bash
export FLEET_ROBOT_ID='rover-01'
export FLEET_SERVER_IP='<адрес сервера>'
export FLEET_MQTT_HOST="$FLEET_SERVER_IP"
export FLEET_MQTT_PORT='1883'

colcon build --symlink-install --packages-up-to fleet_text_bridge_ros2
source install/setup.bash
ros2 launch fleet_text_bridge_ros2 bridge.launch.py
```

Мост вместе с агентом одной командой:

```bash
ros2 launch fleet_text_bridge_ros2 rover_agent_stack.launch.py
# либо в составе bringup:
ros2 launch rover_bringup robot.launch.py profile:=agent
```

## Топики MQTT

Префикс по умолчанию `fleet/v1/robots`, дальше — идентификатор робота:

| MQTT-топик | Направление | QoS | Retain |
|---|---|---|---|
| `fleet/v1/robots/<robot_id>/command` | сервер → робот | 1 | нет |
| `fleet/v1/robots/<robot_id>/answer` | робот → сервер | 1 | нет |
| `fleet/v1/robots/<robot_id>/status` | робот → сервер | 1 | нет |
| `fleet/v1/robots/<robot_id>/availability` | робот → сервер | 1 | **да** |

`availability` — retained-сообщение `{"robot_id": "...", "online": true}` при подключении и `{"online": false}` при штатном завершении ноды. Это даёт серверу актуальный список живых аппаратов сразу после подписки.

## Соответствие ROS ↔ MQTT

```text
MQTT .../command  → ROS /agent/text_command
ROS  /agent/status → MQTT .../status
ROS  /agent/answer → MQTT .../answer
```

## Формат конвертов

Команда (валидируется строго — все три поля обязаны быть непустыми строками):

```json
{"message_id": "0b0d3c49-1404-4546-b31a-31897bbe7a7a",
 "robot_id": "rover-01",
 "text": "Проедь вперёд и сообщи результат"}
```

Если `robot_id` в команде не совпадает с настройкой моста, сообщение отбрасывается.

Статус и ответ:

```json
{"message_id": "…", "robot_id": "rover-01", "status": "running",   "text": "Команда получена локальным агентом."}
{"message_id": "…", "robot_id": "rover-01", "status": "completed", "text": "Готово."}
```

Допустимые статусы ответа — только `completed` и `error`; промежуточные — `running`. Исходящий `robot_id` всегда берётся из конфигурации моста.

## Что делает мост, кроме перекладывания байтов

- **Дедупликация.** Кэш на 100 последних `message_id` (`duplicate_cache_size`) отсекает повторы при QoS 1.
- **Сериализация команд.** Одновременно исполняется одна команда; остальные ждут в очереди. Это нужно, чтобы корректно сопоставлять ответ с запросом, если агент прислал legacy-payload без `message_id`.
- **Таймаут.** Если агент не прислал финальный ответ за `agent_command_timeout_sec` (по умолчанию **300 с**), мост сам публикует в `answer` статус `error` с текстом «Локальный агент не прислал итоговый ответ за N с.» и переходит к следующей команде.
- **Нормализация legacy-вывода.** Принимаются: plain text в `/agent/answer`, старые JSON вида `{"event":"thinking"}`, JSON без `message_id`/`robot_id`. Текст ищется по ключам `text` → `message` → `reply` → `answer` → `event`. `event` из множества `error`/`busy`/`failed` или текст, начинающийся с «ошибка», превращаются в `status: error`.

## Параметры ноды

| Параметр | Переменная окружения | По умолчанию |
|---|---|---|
| `robot_id` | `FLEET_ROBOT_ID` | `rover-01` |
| `mqtt_host` | `FLEET_MQTT_HOST` → `FLEET_SERVER_IP` | `127.0.0.1` |
| `mqtt_port` | `FLEET_MQTT_PORT` | `1883` |
| `mqtt_topic_prefix` | `FLEET_MQTT_TOPIC_PREFIX` | `fleet/v1/robots` |
| `mqtt_username` | `FLEET_MQTT_USERNAME` | пусто |
| `mqtt_password_env` | `FLEET_MQTT_PASSWORD_ENV` | `FLEET_MQTT_PASSWORD` |
| `command_topic` | `AGENT_TEXT_COMMAND_TOPIC` | `/agent/text_command` |
| `answer_topic` | `AGENT_ANSWER_TOPIC` | `/agent/answer` |
| `status_topic` | `AGENT_STATUS_TOPIC` | `/agent/status` |
| `duplicate_cache_size` | `FLEET_DUPLICATE_CACHE_SIZE` | `100` |
| `agent_command_timeout_sec` | `FLEET_AGENT_COMMAND_TIMEOUT_SEC` | `300` |

Пароль передаётся **именем переменной окружения**, а не значением — сам пароль в конфиге не хранится.

## Что учесть для соревнования

- В `components/agent.yaml` зашит `mqtt_host: 10.63.18.111` — чужой адрес, переопределяйте своим брокером.
- Регламент запрещает обмен данными между командами. Общий брокер на площадке — риск: как минимум разводите префиксы топиков и включайте аутентификацию, как максимум поднимайте свой брокер.
- Протокол текстовый и уже содержит `message_id`/`robot_id`/`status` — на нём удобно строить требуемый регламентом лог сообщений агентов, ничего не дописывая.
- Модель «команда → один активный запрос → ответ» не рассчитана на высокочастотный обмен телеметрией: это канал для реплик агентов, а не для потока данных.
