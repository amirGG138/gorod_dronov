# Топики, сервисы и интерфейсы

Канонический список имён — `src/system/rover_bringup/config/topics.yaml`. Ноды берут имена оттуда, поэтому переименование топика делается в одном месте.

## Движение

| Топик | Тип | Кто пишет / читает |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | выход `twist_mux` → `base_driver_node` |
| `/cmd_vel_teleop` | `geometry_msgs/Twist` | веб-управление, приоритет **100** |
| `/cmd_vel_test` | `geometry_msgs/Twist` | MCP-инструменты агента, приоритет **75** |
| `/cmd_vel_nav` | `geometry_msgs/Twist` | Nav2, приоритет **50** |
| `/wheel/encoders` | `rover_interfaces/WheelEncoders` | моторная плата → одометрия |
| `/wheel/commands` | `rover_interfaces/WheelCommand` | целевые скорости колёс |
| `/wheel/odometry` | `nav_msgs/Odometry` | сырая одометрия колёс, вход EKF |
| `/odom` | `nav_msgs/Odometry` | выход EKF; его читают Nav2, веб и агент |
| `/battery_voltage` | `std_msgs/Float32` | напряжение с моторной платы, опрос раз в 5 с |

Таймаут команды у базы — 0.5 с (`command_timeout_sec`), при пропаже команд включается удержание позиции (`hold_position_on_zero_cmd: true`, `stale_brake_hold_sec: 0.35`). Есть ограничения по ускорению и рывку: `max_accel_x 0.8`, `max_decel_x 1.2`, `max_accel_y 0.6`, `max_accel_z 2.0 рад/с²`, `max_jerk_x 4.0`.

> `topics.yaml` объявляет `battery_state: /battery/state`, и на него подписан экран, **но публикатора у этого топика нет**. Проценты заряда придётся считать из `/battery_voltage` самостоятельно.

## Сенсорика

| Топик | Тип | Комментарий |
|---|---|---|
| `/scan` | `sensor_msgs/LaserScan` | сырой выход `sllidar_node` |
| `/scan_filtered` | `sensor_msgs/LaserScan` | после `rover_lidar_filter`; **это и есть `@topics.scan`** |
| `/imu/data` | `sensor_msgs/Imu` | Yahboom, 100 Гц |
| `/imu/mag` | `sensor_msgs/MagneticField` | магнитометр |
| `/imu/euler` | — | углы Эйлера |
| `/imu/valid_frame_count` | — | счётчик валидных кадров, полезен для диагностики |
| `/image_raw`, `/image_raw/compressed` | `sensor_msgs/Image`, `CompressedImage` | 1280×720 @ 30 FPS, MJPEG, JPEG q=85 |
| `/image_processed`, `/image_processed/compressed` | то же | кадры с нарисованными рамками |
| `/detections` | `std_msgs/String` | JSON: class, confidence, bbox |
| `/octoliner/reading` | `rover_interfaces/OctolinerReading` | 8 аналоговых каналов + производные |
| `/octoliner/{analog,pattern,line_position,tracked_line_position,line_visible,sensitivity}` | — | отдельные срезы того же |
| `/led_strip/state` | `rover_interfaces/LedStripState` | состояние ленты и превью кадра |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | сводная диагностика |

Фильтр корпуса заменяет отсечённые лучи на `+inf`, сохраняя индексы и геометрию `LaserScan`, — это корректно для Nav2 и SLAM.

## Голос и агент

| Топик | Тип | Назначение |
|---|---|---|
| `/voice/text` | `std_msgs/String` | распознанный Whisper текст |
| `/voice/transcript` | `std_msgs/String` | JSON с метаданными транскрипции |
| `/waveshare_audio/status` | `std_msgs/String` | статус соединения и STT |
| `/agent/text_command` | `std_msgs/String` | **вход** агента: fleet-конверт или plain text |
| `/agent/status` | `std_msgs/String` | промежуточный JSON-статус (`running`) |
| `/agent/answer` | `std_msgs/String` | итоговый JSON (`completed` / `error`) |
| `/agent/text` | `std_msgs/String` | текст для экранного приложения |
| `/amcl_pose` | `geometry_msgs/PoseWithCovarianceStamped` | поза от AMCL, приоритетный источник для агента |

## Сервисы

| Сервис | Тип | Назначение |
|---|---|---|
| `/led_strip/set_state` | `rover_interfaces/SetLedStripState` | основной способ управления лентой |
| `/led/set_effect` | `rover_interfaces/SetLEDEffect` | нативный эффект драйвера |
| `/led/set_leds` | `rover_interfaces/SetLEDs` | пиксельное управление |
| `/octoliner/set_sensitivity` | `rover_interfaces/SetSensitivity` | чувствительность датчика линии |
| `/octoliner/optimize_on_black` | `std_srvs/Trigger` | калибровка по чёрному |
| `get_frame` (в неймспейсе `usb_camera_node`) | `rover_interfaces/GetFrame` | один кадр без подписки на поток |
| `/voice/say` | `rover_interfaces/SpeakText` | синтез речи через Piper и воспроизведение на плате |

## Действия (actions)

`/navigate_to_pose` (`nav2_msgs/action/NavigateToPose`) — единственное действие, которым пользуется агент. Плюс стандартный набор Nav2: `navigate_through_poses`, `spin`, `backup`, `drive_on_heading`, `wait`.

## `rover_interfaces`

```text
msg/WheelEncoders.msg      Header header, int64[4] total_counts, float64[4] measured_mps,
                           uint32 sequence, bool valid
msg/WheelCommand.msg       Header header, float64[4] target_mps, int32[4] board_command_mm_s
msg/OctolinerReading.msg   Header header, float32[8] analog_values, uint8 pattern,
                           uint8 dark_sensor_count, bool line_visible,
                           float32 line_position, float32 tracked_line_position,
                           float32 sensitivity
msg/LedStripState.msg      Header, connected, enabled, led_count, lit_count, brightness,
                           effect, effect_speed_hz, gpio_pin, pixel_order, backend,
                           status_message, transport, spi_bus, spi_device, RGB,
                           вторичный RGB, uint32[] preview_colors (0xRRGGBB на пиксель)
msg/LEDState.msg           uint32 index, uint8 r, uint8 g, uint8 b
msg/LEDStateArray.msg      LEDState[] leds

srv/GetFrame.srv           → success, message, sensor_msgs/CompressedImage frame,
                             width, height, age_sec
srv/SetLedStripState.srv   enabled, brightness, effect, effect_speed_hz, RGB, вторичный RGB
                           → success, message
srv/SetLEDEffect.srv       effect, r, g, b → success
srv/SetLEDs.srv            LEDState[] leds → success
srv/SetSensitivity.srv     sensitivity → success, message, applied_sensitivity
srv/SpeakText.srv          text → accepted, message
```

Порядок колёс в массивах — `[front_left, front_right, rear_left, rear_right]`. Перестановка и знаки моторов задаются в `rover_v1.yaml` (`motor_command_order: [3,1,2,0]`, все знаки `-1`) — это компенсация фактической разводки, руками её не «исправляйте».
