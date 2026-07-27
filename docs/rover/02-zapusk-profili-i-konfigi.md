# Сборка, запуск, профили и конфигурация

## Сборка

```bash
cd ~/sverk_rover
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

На самом ровере полезно собирать с `PYTHONNOUSERSITE=1` — пользовательские pip-пакеты (в первую очередь NumPy 2.x) конфликтуют с системными ROS/OpenCV:

```bash
PYTHONNOUSERSITE=1 colcon build --symlink-install
```

Один раз на свежесобранном ровере:

```bash
ros2 run rover_device_manager setup_devices
```

Команда создаёт постоянную конфигурацию serial-устройств (`~/.config/rover/devices.json`) и симлинки в `/tmp/rover_devices/{motor_controller,imu,lidar}`.

## Профили запуска

Главная точка входа — `robot.launch.py` с аргументом `profile`:

```bash
ros2 launch rover_bringup robot.launch.py profile:=full
```

| Профиль | Что включено |
|---|---|
| `full` | база, одометрия, description, EKF, twist_mux, IMU, лидар, лента, web, display, rosboard, агент, fleet-мост, камера, **Nav2** |
| `minimal` | база, одометрия, description — и всё |
| `hardware` | только железо, без UI-надстроек |
| `navigation` | железо + Nav2 (`components.nav2: true`) |
| `mapping` | железо + SLAM Toolbox (`components.slam: true`) + web |
| `agent` | **только** LLM-агент, MCP-сервер и MQTT-мост, без железа и без serial-discovery |

Профиль `agent` особенно удобен для отладки логики агента на ноутбуке: `base`, `odometry`, `lidar`, `web` и всё остальное там `false`.

В `full` выключены `octoliner`, `waveshare_audio`, `vision` и `slam`.

## Аргументы `robot.launch.py`

```text
profile  profile_file  config_file  peripherals_config_file  ui_config_file  runtime_dir
use_base  use_odometry  use_description  use_localization  use_imu  use_lidar
use_camera  use_vision  use_display  use_led_strip  use_octoliner  use_waveshare_audio
use_web  use_rosboard  use_agent  use_fleet_bridge  use_nav2  use_slam  use_twist_mux
use_sim_time  use_rviz  rosboard_port  nav2_start_delay  slam_start_delay
motor_device  imu_device  lidar_device
```

Любой компонент профиля переопределяется из командной строки:

```bash
ros2 launch rover_bringup robot.launch.py profile:=full use_camera:=false
ros2 launch rover_bringup robot.launch.py profile:=full use_agent:=false
ros2 launch rover_bringup robot.launch.py profile:=navigation use_nav2:=false
```

`navigation.launch.py`, `mapping.launch.py` и `update_map.launch.py` принимают тот же набор `use_*` плюс `discovery_mode`, а `update_map.launch.py` — ещё `start_mode`, `initial_x`, `initial_y`, `initial_yaw`.

Диагностические под-launch'и остаются доступны отдельно: `hardware.launch.py`, `peripherals.launch.py`, `ui.launch.py`, а также `rover_navigation/{slam,navigation,update_map}.launch.py` и `rover_description/display_*.launch.py` (модель, лидар, одометрия, SLAM, навигация в RViz).

## Иерархия конфигов

Источник истины для собранного ровера — `src/system/rover_bringup/config/`:

```text
config/
├── rover_v1.yaml       # идентичность робота, геометрия, калибровка колёс/энкодеров/IMU
├── topics.yaml         # общие имена топиков и TF-фреймов
├── profiles/           # какие компоненты включены в каждом режиме
├── components/         # рабочие параметры каждого компонента
├── localization/       # ekf_wheel_only.yaml, ekf_with_imu.yaml
└── navigation/         # nav2_params.yaml, slam_toolbox_params.yaml
```

Файлы `config/*.default.example.yaml` внутри пакетов — **только примеры** для автономного запуска пакета. Реальные значения правьте в `rover_bringup/config`.

Порядок разрешения параметров (по возрастанию приоритета):

1. дефолты нод в коде;
2. `config/*.default.example.yaml` пакета (когда пакет запущен отдельно);
3. `rover_bringup/config/components/*.yaml`;
4. `rover_bringup/config/rover_v1.yaml` (геометрия и калибровка);
5. явные launch-аргументы (`use_lidar:=false`).

### Ссылки внутри конфигов

Компонентные конфиги умеют ссылаться на уже загруженные значения:

| Синтаксис | Откуда берётся |
|---|---|
| `@robot.id` | `rover_v1.yaml`, секция `robot` |
| `@topics.cmd_vel_test` | `topics.yaml` |
| `@mcp.url` | собирается из `mcp_host`/`mcp_port` |
| `@paths.default_agent_prompt` | установленный `share/rover_agent_mcp/config/default_system_prompt.md` |
| `@env.FLEET_MQTT_USERNAME` | переменная окружения; если не задана — пустая строка |

## Автозапуск через systemd

```bash
cd ~/sverk_rover
deploy/systemd/install.sh
```

Создаёт `/etc/systemd/system/rover-bringup.service` и `/etc/default/rover-bringup`. Сервис работает от пользователя `pi`, `WorkingDirectory=/home/pi/sverk_rover`, при падении перезапускается через 5 с, останавливается по `SIGINT` с таймаутом 20 с.

Настройки в `/etc/default/rover-bringup`:

```bash
ROVER_WS=/home/pi/sverk_rover
ROVER_PROFILE=full
ROVER_DISCOVERY_MODE=configured        # configured | verify | full
ROS_DOMAIN_ID=0
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ROVER_LAUNCH_ARGS="use_camera:=false use_agent:=false"

# секреты держать здесь, не в git:
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
FLEET_MQTT_USERNAME=
FLEET_MQTT_PASSWORD=
```

Управление:

```bash
sudo systemctl start|stop|restart rover-bringup
systemctl status rover-bringup
journalctl -u rover-bringup -f
sudo systemctl enable|disable rover-bringup      # автозапуск при загрузке
```

`ROS_DOMAIN_ID` здесь важен вдвойне: на соревновании в одном сегменте сети будут чужие аппараты, а регламент запрещает обмен данными между командами. Домены разных команд обязаны различаться.
