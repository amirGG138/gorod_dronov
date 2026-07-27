# Диагностика и типовые проблемы

## Быстрые проверки

```bash
ros2 node list
ros2 topic list
ros2 service list

ros2 topic echo /cmd_vel
ros2 topic echo /wheel/encoders
ros2 topic echo /odom
ros2 topic echo /battery_voltage
```

Камера и детекция:

```bash
ros2 topic hz /image_raw
ros2 topic echo /detections
ros2 service call /usb_camera_node/get_frame rover_interfaces/srv/GetFrame "{}"
```

Лидар и фильтр — сравните оба топика, если Nav2 «видит» корпус:

```bash
ros2 topic hz /scan
ros2 topic hz /scan_filtered
```

Лента, Octoliner, голос:

```bash
ros2 topic echo /led_strip/state
ros2 service list | grep led
ros2 topic echo /octoliner/reading
ros2 service call /octoliner/optimize_on_black std_srvs/srv/Trigger "{}"
ros2 topic echo /voice/text
ros2 topic echo /waveshare_audio/status
```

Агент:

```bash
ros2 topic echo /agent/status
ros2 topic echo /agent/answer
curl -s http://127.0.0.1:8766/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools[].name'
```

Логи сервиса:

```bash
journalctl -u rover-bringup -f
```

## Типовые проблемы

| Симптом | Причина и что делать |
|---|---|
| `Configured motor_controller path is unavailable` | Сменился USB-путь. Проверить кабели, заново выполнить `ros2 run rover_device_manager setup_devices` (или запустить с `discovery_mode:=full`) |
| `cv2` падает из-за NumPy 2.x | Пользовательские pip-пакеты перекрывают системные. Запускать и собирать с `PYTHONNOUSERSITE=1` |
| Веб не открывается | Проверить `http://<ip>:8765`, firewall, что `web_gateway_node` слушает `0.0.0.0`, что ноутбук в той же сети |
| Терминал «reconnecting» | Проверить ttyd, `tools/rover_terminal_shell.sh`, рабочий каталог и права пользователя `pi` |
| Лента не светит | Проверить SPI bus/device, линию MOSI выбранного SPI, питание ленты, общую землю, `led_count: 16`. Данные не должны сидеть на `GPIO2` |
| Octoliner не стартует из-за board revision | Использовать текущий драйвер без старого определения ревизии Pi; проверить шину и адрес I²C (bus 1, 0x2a) |
| Whisper не грузится | Проверить `openai-whisper`/`torch`, совместимость `setuptools`/`coverage`, наличие `/dev/waveshare_audio` |
| Карта в вебе не совпадает с роботом | Веб-визуализация использует `/odom` как координаты карты. Стартовать из origin либо учитывать трансформацию `map→odom` |
| Nav2 упирается в «препятствие» под собой | Убедиться, что источник — `/scan_filtered`, а не `/scan`, и что `lidar_footprint_filter` запущен |
| Агент отвечает, но ровер не едет | `/cmd_vel_test` перебивается только teleop (приоритет 100). Проверить, что веб-джойстик не удерживает команду, и что `twist_mux` запущен |
| Агент «сдался» на середине сценария | Упёрлись в `max_tool_rounds: 8`. Складывать шаги в один `run_motion_sequence`, а не в цепочку отдельных вызовов |
| Мост шлёт `error` «не прислал итоговый ответ за 300 с» | Агент завис или LLM недоступна; смотреть `/agent/status` и логи `rover_agent_text_node` |
| MCP не отвечает на 8765 | Там `rover_web`. Актуальный порт агента — **8766** |

## Чек-лист перед попыткой

- Собрать workspace, `source install/setup.bash`.
- Проверить стабильные пути устройств через `rover_device_manager`.
- Поднять `ui.launch.py`, открыть веб с ноутбука.
- Первый прогон моторов — **с вывешенными колёсами**, на малой скорости.
- Проверить `/image_raw`, `/detections`, `/scan_filtered`, `/odom`, `/led_strip/state`, `/octoliner/reading`, `/voice/text`.
- Проверить `/battery_voltage` и пересчитать в проценты — регламент требует ≥ 40 % перед зачётной попыткой, готового процента система не отдаёт.
- Проверить `ROS_DOMAIN_ID` и адрес MQTT-брокера: чужие значения из репозитория (`10.63.18.111`) обязаны быть заменены.
- Убедиться, что `/agent/status` и `/agent/answer` пишутся в лог — за них начисляются баллы.
- Положить регламент и справочные файлы в `hackathon_files/`, карту — в `maps/current`.
