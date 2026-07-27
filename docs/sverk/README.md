# Документация платформы «Сверх» — локальная копия

Полная выгрузка https://edu.sverk.tech/documentation по состоянию на **2026-07-24**.
145 страниц в трёх независимых разделах.

| Раздел | Каталог | Страниц | Стек |
|---|---|---|---|
| Обрик ROS 2 | [`obrik-ros-2/`](obrik-ros-2/) | 65 | PX4 + ROS 2 Humble + Docker, актуальная платформа |
| Микродрон (Whoop) | [`mikrodron-whoop/`](mikrodron-whoop/) | 27 | PX4 + `simple_offboard_py`, оптический поток, YOLO на NPU |
| Обрик ROS 1 (Clover) | [`obrik-ros-1-clover/`](obrik-ros-1-clover/) | 53 | ROS Noetic + MAVROS, RPi CM4, legacy |

- Постраничный список — [`_INDEX.md`](_INDEX.md)
- Каждый раздел целиком одним файлом — `<каталог>/_ВСЁ.md`
- Сырые JSON из API — [`_raw/`](_raw/)

Ссылки на изображения сохранены как есть (`https://api.edu.sverk.tech/api/storage/file?key=...`) — сами картинки не выгружались.

---

## Как обновить выгрузку

Сайт — Next.js SPA, `curl`/WebFetch отдают пустую оболочку. Контент берётся через публичный REST API без авторизации:

```bash
# дерево модулей и уроков + оглавление в data.metadata.summaryNavigation
curl -s https://api.edu.sverk.tech/api/courses/obrik-ros-2

# HTML страницы в data.lesson.theory.contentHtml
curl -s https://api.edu.sverk.tech/api/courses/obrik-ros-2/lessons/readme
```

Слаги курсов: `obrik-ros-2`, `whoop`, `clover-2`. В общий листинг `GET /api/courses`
они **не попадают** (`isDocumentation: true`) — запрашивать только по слагу.

Из Python использовать `subprocess` + `curl`: `urllib` на этой машине падает с
`SSL: CERTIFICATE_VERIFY_FAILED`.

Исходники документации: https://git.sverk.io/SES/docs

---

# Шпаргалка

## Обрик ROS 2 — главное

**Архитектура.** Полётный контроллер Matek H743 на PX4 ↔ бортовой Linux-компьютер.
Связь по **uXRCE-DDS через UART** (`MicroXRCEAgent`). Отдельно `mavlink-routerd`
ретранслирует MAVLink на UDP **14550** для QGroundControl.

**Docker — ключевой момент.** Весь ROS 2 живёт в контейнере `sverk_ros2`.

| Куда | Команда |
|---|---|
| Контейнер (по умолчанию, тут вся работа) | `ssh sverk@<IP>` — порт 22, пароль `sverk` |
| Хост (только чтобы включить UART/SPI/PWM/I²C в конфиге загрузки) | `ssh -p 2222 <user>@<IP>` |

Пользователь хоста зависит от платы: `pi` / `orangepi` / `rock` / `sunrise`.
Проверить, где вы: `hostname` → `sverk_ros2` значит внутри контейнера.

**Автозапуск.** `sverk_ws/src/sverk_drone/main_package/launch_system/launch/full_system_real.launch.py`
поднимается сам при включении. Флаги в начале файла:

```python
ENABLE_ARUCO / ENABLE_CAMERA / ENABLE_VIO / ENABLE_MAVLINKROUTER
ENABLE_WEB / ENABLE_LED / ENABLE_AI / ENABLE_LIDAR
MK_NAME = "RPI"   # RPI | RADXA | RDX | ORANGE | ORANGE_3W
```

Уже запущено ядром: камера, ArUco (детект/карта/локализация), VIO, `offboard_control`,
`led_control`, веб. **Запускать вручную не нужно.**
НЕ в автозапуске: серво, VL53L1X, Arduino, лидар, `camera_calibration`.

**Цикл применения правок:**
```bash
# 1) в контейнере
cd ~/sverk_ws && colcon build --packages-select launch_system && source install/setup.bash
# 2) на хосте (порт 2222)
sudo systemctl restart sverk-ros2-docker
```
Имя сервиса в systemd всегда `sverk-ros2-docker`, различаются только исходные
`.service`-файлы в репозитории и пользователь хоста.

**Python API — `sverk_interfaces`:**

```python
import sverk_interfaces
drone = sverk_interfaces.init(Nodename="my_program")
try:
    drone.control.navigate(x=0, y=0, z=1.5, yaw=0.0, speed=0.5,
                           frame_id="body", auto_arm=True)
    drone.control.land()
finally:
    drone.close()
```

- `drone.control` — `navigate`, `navigate_wait(tolerance, timeout)`, `land`,
  `get_telemetry(frame_id)`, `set_altitude`, `set_yaw`, `set_yaw_rate`,
  `clear_yaw_override`, `set_position`, `set_velocity`, `set_attitude`,
  `set_rates`, `flip`, `configure_defaults`
- `drone.image` — `take_picture()` / `stream(cb, duration)` отдают **numpy BGR сразу**
  (`raw=True` для `sensor_msgs/Image`), `publish()` → `/out_detection`,
  `detect_qr()`, `to_cv2` / `to_ros`, `calibration.*`
- `drone.gpio` — `pin_on/pin_off/pin_read/pin_release`, `servo_enable/servo_set_angle/
  servo_center/servo_disable/servo_select_channel`, `magnet_on/magnet_off`
- `drone.led` — `set_effect(effect, r, g, b)`, `set_leds([...])`, `get_state()`
- `drone.topic` — `subscribe`, `create_publisher`, `wait_for_message`, `spin`, `spin_once`
- `drone.fcu` — `disarm`, `force_disarm`, `kill_switch`, `calibrate_*`

`auto_arm=True` нужен **только первой** команде взлёта — она переводит в OFFBOARD
и армит. `navigate` не блокирует, `navigate_wait` ждёт прилёта.

**Системы координат:**

| frame_id | Что это |
|---|---|
| `body` | Корпус дрона, FLU: X вперёд, Y влево, Z вверх. Взлёт, «пролети 2 м вперёд» |
| `map` | Мировая ENU, начало — точка включения. Квадраты, возврат в старт |
| `terrain` | Высота над поверхностью под дроном |
| `aruco_map` | Карта ArUco-маркеров |
| `aruco_<N>` | Относительно конкретного маркера с ID=N |

При `frame_id='body'` и `yaw=0.0` курс НЕ меняется. Пересчёт делает tf2 внутри `offboard_control`.

**Навигация в помещении** — ArUco-поле на полу, без GPS. Камера вниз → `aruco_detect_node`
→ `aruco_loc_node` (RANSAC + solvePnP) → `/aruco_map/pose_cov` → `px4_local_pose_publisher`
→ EKF2 в PX4. Компас по умолчанию **выключен** (помехи в помещении), вместо него MicroAir MTF-02.

Генерация карты: `ros2 run aruco_pose genmap.py LENGTH X Y DIST_X DIST_Y FIRST_ID [-o map.txt]`.
Карта из комплекта: `genmap.py 0.3 3 2 0.5 0.5 42 -o sverk.txt` (метки 42–47).
Файл: `~/sverk_ws/src/sverk_drone/odomerty/aruco/aruco_map/config/sverk.txt`.

**Ключевые топики/сервисы:** `/camera_1/image_raw`, `/markers`, `/aruco_map/pose_cov`,
`/out_detection`, `/led/state`, `/navigate`, `/land`, `/get_telemetry`.

**Предполётная проверка:** `ros2 run self_check selfcheck.py`.
Критично зелёное: **ArUco, Local position, FMU, Velocity estimation (VPE)**.

**Веб-интерфейс:** `http://<IP>` — СВЕРХ WEB (VSCode, файловый менеджер, Butterfly-терминал,
Aruco Map Editor, Flight Review, web_video_server, ROSboard, ROS-сервисы).
`http://<IP>:5173` — Sverk Drone Tools (телеметрия, виджеты).

**Настройка PX4 через QGC (порядок при первой настройке):**
QGC по Wi-Fi (UDP 14550) → аппаратура ELRS (Binding Phrase одинаковая на TX и RX)
→ Vehicle Configuration → загрузка файла параметров (Tools → Load from file for review)
→ Reboot → калибровка гироскопа / акселерометра (**Autopilot Orientation: Pitch 180°, Yaw 90°**)
/ уровня горизонта → калибровка аппаратуры (Mode 2) → полётные режимы → питание.

Каналы: 1 Roll, 2 Pitch, 3 Throttle, 4 Yaw, 5 SA (**Arm**), 6 SB (**режимы**),
7 SC, 8 SD (**Kill Switch**), 9 SE, 10 S1.
Режимы на SB: Flight Mode 1 = Stabilized, 4 = Position, 6 = Altitude.

**АКБ 3S LiHV:** полный заряд 13.05 В (4.35 В/ячейка), минимум в полёте 10.65 В
(3.55 В), хранение 11.85 В (3.95 В). В QGC мониторинг: cells 3, Empty 3.30 В,
Full 4.20 В, Voltage divider ≈ 11 (или Calculate по индикатору).
Горящий LiPo **не тушить водой** — песок или порошковый огнетушитель класса D.

**Порядок включения/выключения (ТБ):** аппаратура → АКБ → …полёт… → посадка →
Disarm → отключить АКБ → выключить аппаратуру. Пропеллеры ставятся **последними**
перед взлётом. Все настройки и калибровки — **без пропеллеров**.

**Пути `/dev` по платам** (`52-boards-overview.md`):

| Интерфейс | RPi CM5 | Orange Pi Zero 3W | Orange Pi 5 Pro |
|---|---|---|---|
| UART_A (PX4, **занят**) | `/dev/ttyAMA0` | `/dev/ttyS2` | `/dev/ttyS0` |
| UART_B (свободен) | `/dev/ttyAMA10` | `/dev/ttyS6` | `/dev/ttyS1` |
| SPI (LED-лента) | `/dev/spidev1.0` | `/dev/spidev3.0` | `/dev/spidev1.0` |
| GPIO | `/dev/gpiochip0` | `/dev/gpiochip0` | `/dev/gpiochip0` |
| CSI-камера | cam0 (videocore) | CAM1 (vin_v4l2) | CAM1 (rkisp1) |

Топик камеры `/camera_1/image_raw` одинаков везде — код от платы не зависит.
GPIO 3.3 В, ≤16 мА на пин; GPIO 14/15 заняты UART, GPIO 20 — SPI1 MOSI (лента).
PWM для серво: GPIO12 (pwm0) и GPIO13 (pwm1).

## Микродрон (Whoop) — чем отличается

**Совершенно другой API**, не `sverk_interfaces`:

```python
from simple_offboard_py import SimpleOffboard, Frame
drone = SimpleOffboard()
drone.takeoff(0.7)
drone.navigate(1.0, 0.0, -0.7, frame=Frame.BODY_NED, yaw=0.0,
               tolerance=0.1, time_limit=10.0)
drone.land()
```

- Фреймы `Frame.BODY_NED` / `Frame.LOCAL_NED` — **ось Z направлена ВНИЗ**:
  высота 0.7 м это `z = -0.7`. (В Обрике ROS 2 наоборот, Z вверх.)
- Нужно задать ровно один из `yaw` / `yaw_rate`, иначе команда игнорируется.
- `get_position()` → `x, y, z, roll, pitch, yaw`; `get_detections()` → объекты YOLO.
- Позиционирование — **оптический поток**, не ArUco. В `drone selfcheck` пункт
  **gps = FAIL это норма**; важен `vision position`. Нужна текстурированная,
  хорошо освещённая матовая поверхность.
- Подключение по проводу: SSH на фиксированный **`10.10.1.1`**, логин/пароль `root`.
  Wi-Fi настраивается правкой `/etc/wpa_supplicant.conf`.
- QGC — UDP 14550 на `10.10.1.1`.
- АКБ **1S** LiHV 850 mAh (не 3S!): Empty 3.55 В, Full 4.35 В. ЗУ GEPRC WooPower W63.
- Камера 1280×720, центр кадра (640, 360).

**Компьютерное зрение:** YOLO11n → Roboflow (экспорт в формате YOLOv11) → обучение
(`ultralytics`, Colab) → конвертация `.pt` → ONNX → `.mlir` → **`.cvimodel`** под NPU
`cv181x` (тулкит Sophgo tpu-mlir, готовый ноутбук
`git.sverk.io/tiny_control/edu/ml/-/blob/master/yolo_train_and_export.ipynb`).
Запуск на борту: `/root/packages/yolo_detector model.cvimodel 3 0.3 0.3 1 1`.
Инференс 3–10 FPS на CPU, только nano-модели.

## Обрик ROS 1 (Clover) — чем отличается

- ROS **Noetic** + MAVROS, `rospy.ServiceProxy('navigate', srv.Navigate)`.
  `navigate_wait` не входит в API — копируется в скрипт руками.
- IP **`192.168.11.1`**, Wi-Fi `Sverk-xxxxx` / пароль `sverkwifi`,
  SSH `pi@192.168.11.1` / `raspberry`. QGC по **TCP:5760** (в ROS 2 — UDP:14550).
- Веб-интерфейс на `http://192.168.11.1`, web_video_server на `:8080`,
  Blockly на `/sverk_blocks/`.
- Конфигурация — `.launch`-файлы в `~/catkin_ws/src/sverk/sverk/launch/`,
  перезапуск `sudo systemctl restart sverk`.
- GPIO через `pigpio` (демон `pigpiod`), а не libgpiod.
- Позиционирование: Optical Flow (требует дальномер VL53L1X) и/или ArUco через VPE.
- Фрейм **`navigate_target`** — координаты относительно последней цели, на нём
  построен `navigate_wait`. В ROS 2 такого фрейма нет.
- **Уникальный раздел, которого нет в ROS 2: рой на ESP-NOW**
  (`23-swarm.md`) — ESP32-C3 + Python-библиотека `skyros`, телеметрия,
  предотвращение столкновений, мастер-слейв координация.
- Есть подробная статья по настройке PID PX4 (`44-pid-tuning.md`) и по
  виртуальной машине Clover VM для Gazebo.

---

## Замеченные проблемы в документации

- **ROS 1 и ROS 2 версии Обрика несовместимы по API**, но слаги и заголовки статей
  местами совпадают — легко перепутать, о какой платформе речь.
- `16-os-image-flash.md`: ссылка на образ ROS 2 отсутствует («появится здесь»).
- `46-simulation.md`: локальный Gazebo-симулятор — «раздел в разработке».
- В статьях по платам в примерах `nmcli` лежат **реальные пароли** от рабочих
  Wi-Fi-сетей (`Poletka`, `Sverk_5G`).
- `obrik-ros-1-clover/27-first-automy-fly.md`: у `navigate_wait` сломаны отступы —
  скопированный как есть скрипт не запустится.
- Расхождение путей: `52-boards-overview.md` даёт для RPi CM5 UART_A `/dev/ttyAMA0`,
  а `62-devices-raw.md` — `/dev/ttyAMA2`. Также `59-docker-architecture.md`
  упоминает топик камеры `/drone/image/raw` вместо `/camera_1/image_raw`.

## Поддержка

Телеграм техподдержки: [@sverk_support](https://t.me/sverk_support)
