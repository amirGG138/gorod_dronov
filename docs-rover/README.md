# Ровер «Сверх»: выжимка по репозиторию `sverk_rover`

Локальная выгрузка из **https://github.com/wodocanal/sverk_rover** (ветка `main`, HEAD `9a4e7cc` от 2026-07-21), сделана 2026-07-27. Это единственный известный источник по роверу: в официальной документации `edu.sverk.tech` (см. `docs-sverk/`) ровера нет вообще.

Перенесена текстовая часть репозитория: README всех пакетов, конфиги, launch-файлы, msg/srv, deploy, исходники агента. Не перенесены: SDK лидара (`sllidar_ros2/sdk`), веб-ассеты rosboard, модели нейросетей (~37 МБ), бинарники карт, прошивки ESP32.

**Читайте эту страницу целиком, прежде чем грепать разделы.** Ниже — всё, что нужно, чтобы не спутать ровер с Обриком и не наступить на расхождения в апстримной документации.

- [`01-arhitektura-i-pakety.md`](01-arhitektura-i-pakety.md) — раскладка workspace, 19 ROS-пакетов, что где лежит.
- [`02-zapusk-profili-i-konfigi.md`](02-zapusk-profili-i-konfigi.md) — сборка, профили, launch-аргументы, иерархия конфигов, systemd.
- [`03-topiki-servisy-i-interfeysy.md`](03-topiki-servisy-i-interfeysy.md) — все топики, сервисы, `rover_interfaces`, TF-фреймы, twist_mux.
- [`04-agent-mcp-i-llm.md`](04-agent-mcp-i-llm.md) — LLM-агент, MCP-сервер, полный список из 19 инструментов.
- [`05-fleet-mqtt-i-mezhagentnaya-svyaz.md`](05-fleet-mqtt-i-mezhagentnaya-svyaz.md) — MQTT-протокол флота, конверты сообщений, корреляция.
- [`06-navigaciya-slam-i-karty.md`](06-navigaciya-slam-i-karty.md) — Nav2, AMCL, SLAM Toolbox, EKF, работа с картами.
- [`07-periferiya-i-zhelezo.md`](07-periferiya-i-zhelezo.md) — шасси, IMU, лидар, камера, лента, Octoliner, звук, device manager.
- [`08-diagnostika-i-tipovye-problemy.md`](08-diagnostika-i-tipovye-problemy.md) — проверки, симптомы, чек-лист.
- [`_pdf-polnaya-dokumentaciya.md`](_pdf-polnaya-dokumentaciya.md) — расшифровка официального PDF от 12.07.2026 (**архив**, описывает старую раскладку).
- `sverk_rover_full_documentation.pdf` — сам PDF из `hackathon_files/`.

## Что это за аппарат

| Поле | Значение |
|---|---|
| Платформа | 4-колёсный **mecanum**-ровер на Raspberry Pi 5 |
| ROS | **ROS 2 Jazzy** (у Обрика — Humble; пакеты несовместимы) |
| Workspace | `~/sverk_rover`, сборка `colcon build --symlink-install` |
| Пакеты интерфейсов | `rover_interfaces` (у Обрика — `sverk_interfaces`) |
| Габариты шасси | 0.2006 × 0.199 × 0.0532 м — с запасом влезает в регламентные 0,5 × 0,5 м |
| Колесо | r = 0.03 м, база 0.13961 м, колея 0.181 м |
| Footprint для Nav2 | `[[0.125, 0.130], [0.125, -0.130], [-0.125, -0.130], [-0.125, 0.130]]` |
| Идентичность | `robot.id: rover-01`, `serial_number: SVR-0001` (`config/rover_v1.yaml`) |
| Предел скорости | `max_wheel_speed_mps: 0.35`; Nav2 `max_vel_x 0.25`, `max_vel_y ±0.18`, `max_vel_theta 0.55` |

Система координат — обычная ROS-овская **FLU**: `base_link`, +X вперёд, +Y влево, поворот «+» = против часовой (влево). Никакой инверсии Z, как у микродрона, здесь нет; высота вообще не участвует (`two_d_mode: true` в EKF).

## Ключевые адреса и порты

| Что | Адрес | Комментарий |
|---|---|---|
| Веб-интерфейс `rover_web` | `http://<ip>:8765` | `web_gateway_node`, слушает `0.0.0.0` |
| Веб-терминал ttyd | `http://<ip>:7681` | запускается из `ui.launch.py` |
| ROSboard | `http://<ip>:8888` | отдельная страница просмотра графа |
| MCP-сервер агента | `http://127.0.0.1:8766/mcp` | только localhost; JSON-RPC POST |
| MQTT-брокер флота | `<mqtt_host>:1883` | префикс топиков `fleet/v1/robots` |
| SSH | `pi@<ip>` | сервис systemd работает от пользователя `pi` |

## Три вещи, о которые проще всего споткнуться

**1. `/scan` — это не то, что едет в Nav2.** Лидар публикует сырой `/scan`, нода `rover_lidar_filter` вырезает точки внутри корпуса и публикует `/scan_filtered`. Nav2, SLAM, AMCL и MCP-инструмент `get_laser_summary` подписаны на `/scan_filtered`. В `topics.yaml` это закреплено ключами `scan_raw: /scan` и `scan: /scan_filtered` — то есть `@topics.scan` означает **отфильтрованный** скан.

**2. Ехать можно в три разных топика, и они не равны.** Всё сводит `twist_mux` в `/cmd_vel`:

| Вход | Приоритет | Кто пишет |
|---|---|---|
| `/cmd_vel_teleop` | 100 | ручное управление, веб-джойстик |
| `/cmd_vel_test` | 75 | **MCP-инструменты агента** |
| `/cmd_vel_nav` | 50 | Nav2 |

Агент публикует в `/cmd_vel_test` и потому перебивает Nav2, но не перебивает teleop. Если писать напрямую в `/cmd_vel`, вы обходите мультиплексор — так делать не надо.

**3. Заряда батареи в процентах нет.** `base_driver_node` публикует `/battery_voltage` (`std_msgs/Float32`, опрос платы раз в 5 с). А `topics.yaml` и экранное приложение ждут `/battery/state` — **этот топик не публикует никто**. Регламентная проверка «заряд ≥ 40 % перед попыткой» упирается в вольтаж, который придётся пересчитывать самим.

## Как это закрывает пробелы из `CLAUDE.md`

Репозиторий разом отвечает на все три вопроса, которых нет в документации «Сверх»:

- **Ровер** — вся аппаратная и программная часть здесь, включая моторную плату, одометрию, Nav2 и карты.
- **LLM на борту** — есть работающая схема: ROS-нода `rover_agent_text_node` ходит в OpenAI-совместимый endpoint (по умолчанию `https://ai.sverk.io/v1`, модель `qwen35`; поддерживается OpenRouter), а исполняет действия только через whitelist MCP-инструментов. Прямого доступа к shell/ROS CLI у модели нет.
- **Межагентная связь для ROS 2** — MQTT-протокол `fleet/v1/robots/<robot_id>/{command,answer,status,availability}`. Это готовый аналог `skyros`/ESP-NOW из legacy-стека Clover, только поверх брокера.

Отдельно полезно для баллов за логи: агент сам публикует `/agent/status` и `/agent/answer` JSON-конвертами с `message_id` и `robot_id`. Это фактически готовый формат журнала решений и сообщений агентов — его дешевле принять как есть, чем изобретать свой.

## Замеченные проблемы в апстримной документации

Проверяйте по этому списку, прежде чем воспроизводить команду со страницы дословно.

1. **Порт MCP расходится.** `src/agent/rover_agent_mcp/README.md` и дефолт в коде говорят `http://127.0.0.1:8765/mcp`, но 8765 занят веб-интерфейсом. Реальный bringup (`components/agent.yaml`) поднимает MCP на **8766** и туда же указывает `mcp_url`. Дефолт из README сработает только при выключенном `rover_web`.
2. **PDF описывает раскладку, которой больше нет.** `sverk_rover_full_documentation.pdf` от 12.07.2026 ссылается на `src/rover_bringup/...`, пакеты `rover_localization`, `rover_teleop`, каталоги `maps/` и `firmware/` в корне. На `main` всё переехало в `src/{system,motion,peripherals,agent,ui}/`, пакетов `rover_localization` и `rover_teleop` **не существует** (EKF-конфиги живут в `rover_wheel_odometry` и `rover_bringup`). Пути конфигов вида `src/rover_bringup/config/rover.yaml` устарели — актуально `src/system/rover_bringup/config/rover_v1.yaml`.
3. **`environment.example.sh` не существует.** README агента отсылает «см. корневой `environment.example.sh`» — в репозитории такого файла нет. Переменные окружения собирайте из `deploy/systemd/rover-bringup.env` и README `fleet_text_bridge_ros2`.
4. **Битая внутренняя ссылка.** `AGENT_MCP_QUICKSTART.md` указывает на `src/rover_agent_mcp/README.md`; реальный путь — `src/agent/rover_agent_mcp/README.md`.
5. **Чужие IP захардкожены.** `components/agent.yaml` содержит `mqtt_host: 10.63.18.111`, README моста предлагает `FLEET_SERVER_IP=10.194.179.111`. Оба — адреса из чужих сетей, обязательно переопределяйте.
6. **Батарея (см. выше)** — `/battery/state` объявлен, но не публикуется.
7. **Разнобой в написании бренда.** В `fleet_text_bridge_ros2` — «SVERH fleet protocol», каталог планов веба — `~/.local/share/sverh-rover-web/plans`, всё остальное — SVERK/«Сверх». При грепе учитывайте оба написания.
8. **README агента упоминает `/scan`**, тогда как код и bringup работают с `/scan_filtered` (п. 1 «трёх вещей» выше).
9. **PDF описывает `rover_teleop` и WASD-телеоперацию** как отдельный пакет — сейчас ручное управление живёт только в веб-интерфейсе (`/cmd_vel_teleop`).

## Как обновить эту выгрузку

Клонирование целиком на этой машине отваливается по таймауту (58 МБ, в основном модели и SDK). Рабочий путь — GitHub API + `curl` (у `urllib` здесь `SSL: CERTIFICATE_VERIFY_FAILED`, см. `CLAUDE.md`):

```bash
curl -sS "https://api.github.com/repos/wodocanal/sverk_rover/git/trees/main?recursive=1" -o tree.json
# отобрать текстовые пути из tree.json, затем по одному:
curl -sS -o "<path>" "https://raw.githubusercontent.com/wodocanal/sverk_rover/main/<path>"
```

Параллельность выше ~10 запросов приводит к `Recv failure: Connection reset by peer` — делайте повторный проход по пустым файлам. PDF читается через временный venv с `pypdf` (`poppler`/`pdftotext` на машине нет).
