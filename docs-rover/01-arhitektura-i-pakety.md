# Архитектура workspace и пакеты

## Раскладка репозитория

```text
sverk_rover/
├── deploy/
│   ├── systemd/                # rover-bringup.service, install.sh, .env
│   └── sudoers/                # правило для скрипта настройки Wi-Fi
├── hackathon_files/            # PDF документации и регламента (их отдаёт веб-страница «Хакатон»)
└── src/
    ├── agent/                  # LLM-агент, MCP-сервер, MQTT-мост флота
    │   ├── rover_agent_mcp/
    │   └── fleet_text_bridge_ros2/
    ├── motion/                 # одометрия и навигация
    │   ├── rover_wheel_odometry/
    │   └── rover_navigation/   # + maps/current и maps/archive
    ├── peripherals/            # драйверы железа
    │   ├── rover_base_driver/  rover_camera/  rover_device_manager/
    │   ├── rover_imu/  rover_led_strip/  rover_lidar_filter/
    │   ├── rover_octoliner/  rover_waveshare_audio/  sllidar_ros2/
    ├── system/                 # сборка системы и общесистемные ноды
    │   ├── rover_bringup/      # ← источник истины по конфигам
    │   ├── rover_description/  rover_interfaces/  rover_vision/
    └── ui/
        ├── rover_web/  rover_display/  rosboard/
```

Каталоги `src/agent`, `src/motion`, `src/peripherals`, `src/system`, `src/ui` — **не пакеты**, а группировка; colcon находит пакеты рекурсивно.

## Пакеты

| Пакет | Верс. | Группа | Назначение |
|---|---|---|---|
| `rover_bringup` | 0.4.3 | система | Главный launch и вся рабочая конфигурация ровера |
| `rover_interfaces` | 0.2.0 | система | Собственные msg/srv (энкодеры, лента, Octoliner, кадр, TTS) |
| `rover_description` | 0.4.2 | система | URDF/Xacro, TF-фреймы, конфиги RViz |
| `rover_vision` | 0.1.0 | система | Детекция объектов по кадрам камеры (SSD MobileNet / YOLOv5n) |
| `rover_base_driver` | 0.2.0 | движение | `/cmd_vel` → команды моторной плате, обратная связь энкодеров |
| `rover_wheel_odometry` | 0.2.0 | движение | Одометрия mecanum-базы из энкодеров + конфиги EKF |
| `rover_navigation` | 0.4.3 | навигация | Nav2, AMCL, SLAM Toolbox, менеджер карт `rover_map` |
| `rover_camera` | 0.1.0 | периферия | USB-камера, JPEG/MJPEG, сервис `get_frame` |
| `rover_imu` | 0.2.0 | периферия | Драйвер Yahboom 10-осевой IMU + нормализация |
| `sllidar_ros2` | 1.0.1 | периферия | Драйвер SLLIDAR/RPLIDAR (модель `sllidar_c1`) |
| `rover_lidar_filter` | — | периферия | Вырезает точки внутри корпуса: `/scan` → `/scan_filtered` |
| `rover_led_strip` | 0.1.0 | периферия | Адресная лента WS2812 по SPI, эффекты и пресеты |
| `rover_octoliner` | 0.1.0 | периферия | 8-канальный датчик линии Amperka Octoliner (I²C) |
| `rover_waveshare_audio` | 0.1.0 | периферия | ESP32-S3 Audio Board: Whisper STT + Piper TTS |
| `rover_device_manager` | 0.4.1 | периферия | Обнаружение serial-устройств и стабильные пути в `/tmp/rover_devices` |
| `rover_agent_mcp` | — | агент | Текстовый агент (LLM) и локальный MCP-сервер инструментов |
| `fleet_text_bridge_ros2` | — | агент | MQTT ↔ ROS 2 мост протокола флота |
| `rover_web` | 0.1.0 | UI | Веб-интерфейс, шлюз к ROS, исполнитель маршрутов |
| `rover_display` | 0.1.0 | UI | Полноэкранное приложение для дисплея Raspberry Pi |
| `rosboard` | 1.3.1 | UI | Сторонний ROSBoard, вендорнут в репозиторий |

## Исполняемые файлы (console_scripts)

```text
rover_agent_mcp:        agent_text_node, rover_mcp_server
fleet_text_bridge_ros2: bridge_node
rover_device_manager:   setup_devices, discover_devices
rover_navigation:       rover_map            # save / status / list / use
```

Остальные ноды запускаются под своими именами: `base_driver_node`, `wheel_odometry_node`, `yahboom_imu_node`, `sllidar_node`, `usb_camera_node`, `camera_detector_node`, `led_strip_node`, `octoliner_node`, `waveshare_audio_node`, `lidar_footprint_filter`, `web_gateway_node`, `rover_status_display_node`, `ekf_filter_node` (из `robot_localization`), `twist_mux`.

## TF-фреймы

Из `config/topics.yaml`:

```text
map → odom → base_link → { imu_link, lidar_link, camera_optical_frame, led_strip, octoliner_link }
```

Смещения датчиков заданы в `rover_v1.yaml`: IMU `[0.0332, -0.0837, 0.0435]` с рысканьем +90°, лидар `[0.0662, 0.0, 0.0837]` с разворотом на 180°. Именно поэтому фильтр корпуса работает через TF, а не через угловые маски.

## Что упоминается в PDF, но отсутствует на `main`

`rover_localization` и `rover_teleop` как пакеты не существуют. EKF-параметры лежат в `src/motion/rover_wheel_odometry/config/localization/` (примеры) и `src/system/rover_bringup/config/localization/` (рабочие). Телеоперация — только через веб-интерфейс.
