# Навигация, SLAM, локализация и карты

## Локализация: EKF

`robot_localization/ekf_node` (`ekf_filter_node`), конфиги в `rover_bringup/config/localization/`.

```text
frequency: 50 Гц        sensor_timeout: 0.25 с        two_d_mode: true
world_frame: odom       map_frame: map                base_link_frame: base_link
publish_tf: true        reset_on_time_jump: true
odom0: /wheel/odometry  → берутся только vx, vy
imu0:  /imu/data        → берётся только угловая скорость по yaw
```

Вариант `ekf_wheel_only.yaml` — без IMU. Выход EKF идёт в `/odom`; именно его читают Nav2, веб-визуализация и MCP-инструменты относительного движения.

Ковариации сырой одометрии заданы в `components/base.yaml`: по позиции `[0.03, 0.08, 999, 999, 999, 0.15]`, по скорости `[0.02, 0.06, 999, 999, 999, 0.12]` — «999» на неиспользуемых осях (z, roll, pitch) для плоской модели.

## Nav2

Параметры — `rover_bringup/config/navigation/nav2_params.yaml`.

| Компонент | Настройка |
|---|---|
| AMCL | `robot_model_type: nav2_amcl::OmniMotionModel`, `scan_topic: /scan_filtered`, `global_frame_id: map` |
| Планировщик | `nav2_navfn_planner::NavfnPlanner` |
| Контроллер | `dwb_core::DWBLocalPlanner` |
| Сглаживание | `nav2_smoother::SimpleSmoother` |
| Поведения | `Spin`, `BackUp`, `DriveOnHeading`, `Wait`, `rotational_acc_lim: 2.0` |
| BT-навигаторы | `NavigateToPoseNavigator`, `NavigateThroughPosesNavigator` |

Скоростные пределы DWB:

```text
max_vel_x  0.25      min_vel_x  -0.20
max_vel_y  0.18      min_vel_y  -0.18      # mecanum умеет боком
max_vel_theta 0.55
acc_lim_x 0.8   acc_lim_y 0.6   acc_lim_theta 2.0
```

Костмапы: разрешение 0.05 м/клетка, footprint `[[0.125,0.130],[0.125,-0.130],[-0.125,-0.130],[-0.125,0.130]]`, `inflation_radius: 0.28`. Локальный костмап в `odom`, глобальный в `map`, оба слушают `/scan_filtered` (`observation_sources: scan`). Слои: static (только глобальный), obstacle, inflation.

`odom_topic: /odom`, `map_topic: /map`.

## SLAM Toolbox

`rover_bringup/config/navigation/slam_toolbox_params.yaml`:

```text
mode: mapping           resolution: 0.05         max_laser_range: 8.0
scan_topic: /scan_filtered
map_frame: map          odom_frame: odom         base_frame: base_link
enable_interactive_mode: true
```

Дальность 8 м как раз перекрывает регламентное поле 8×8 м, но по диагонали (≈11.3 м) — нет. Для куба 8×8 карту придётся строить, объезжая площадку, а не из одной точки.

**Одновременно SLAM Toolbox и AMCL запускать нельзя.**

## Построение карты

Терминал 1:

```bash
ros2 launch rover_bringup mapping.launch.py
```

Терминал 2 (опционально, RViz):

```bash
ros2 launch rover_description display_slam.launch.py
```

Двигайте ровер веб-интерфейсом, инструментами Nav2 или любым публикатором в `/cmd_vel`. Сохраняйте карту, **пока SLAM ещё работает**:

```bash
ros2 run rover_navigation rover_map save room
```

Прочие команды менеджера карт:

```bash
ros2 run rover_navigation rover_map status
ros2 run rover_navigation rover_map list
ros2 run rover_navigation rover_map use <имя_каталога_в_archive>
```

`rover_map save` обновляет и исходники, и установленную копию пакета, поэтому навигацию можно запускать без пересборки.

## Структура карт

```text
src/motion/rover_navigation/maps/
├── current/            # карта, которую Nav2 берёт по умолчанию
│   ├── map.yaml        # resolution, origin, пороги
│   ├── map.pgm         # occupancy grid
│   ├── map.posegraph   # SLAM Toolbox: граф поз
│   ├── map.data        # SLAM Toolbox: данные сканов
│   └── map_info.json   # label, created_at, posegraph_saved
└── archive/            # предыдущие версии
```

Текущая карта в репозитории (`label: room`, снята 2026-06-19):

```yaml
image: map.pgm
mode: trinary
resolution: 0.050
origin: [-4.333, -7.700, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.196
```

`map.yaml` + изображение нужны Map Server и AMCL; `map.posegraph` + `map.data` — чтобы **продолжить** картирование.

## Навигация по готовой карте

```bash
ros2 launch rover_bringup navigation.launch.py
ros2 launch rover_description display_navigation.launch.py   # опционально
```

В RViz перед первой целью задайте стартовую позу инструментом `2D Pose Estimate`. Первый прогон моторов под Nav2 делайте с вывешенными колёсами.

Из кода/агента цель ставится действием `/navigate_to_pose` или инструментом `navigate_to_pose(x, y, yaw_deg)`.

## Дополнение существующей карты

Требуются `map.posegraph` и `map.data` в `current/` (их создаёт `rover_map save`).

Ровер стоит в исходной первой позе карты:

```bash
ros2 launch rover_bringup update_map.launch.py
```

Ровер стоит в известной точке карты:

```bash
ros2 launch rover_bringup update_map.launch.py \
  start_mode:=given initial_x:=1.2 initial_y:=0.5 initial_yaw:=1.57
```

После дополнения сохраните под новым именем:

```bash
ros2 run rover_navigation rover_map save room_updated
```
