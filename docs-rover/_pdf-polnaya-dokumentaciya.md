# SVERK Rover — полная техническая документация (расшифровка PDF)

> **Архивный документ.** Это очищенная расшифровка `sverk_rover_full_documentation.pdf` (16 страниц, дата документа — **12 июля 2026**), лежащего в репозитории в `hackathon_files/`. К моменту выгрузки (HEAD `9a4e7cc` от 2026-07-21) репозиторий был реорганизован, и часть путей и пакетов здесь **устарела**: см. пункт 2 раздела «Замеченные проблемы» в [`README.md`](README.md). Актуальное состояние описано в файлах `01`–`08`.
>
> Таблицы восстановлены из плоского текста PDF; смысл сохранён, вёрстка — нет.

| Поле | Значение |
|---|---|
| Платформа | 4-колёсный mecanum rover на Raspberry Pi 5 |
| ROS | ROS 2 Jazzy |
| Основной workspace | `~/sverk_rover` |
| Дата документа | 12 июля 2026 |
| Назначение | Справочник для хакатона, разработки, диагностики и запуска робота |

Документ сформирован из файлов репозитория и описывает реализованные ROS-пакеты, launch-файлы, конфиги, веб-интерфейс, экран, периферию, навигацию, карты, прошивку аудиомодуля и типовые команды запуска.

## 1. Краткая сводка

SVERK Rover — учебно-хакатонная робототехническая платформа на Raspberry Pi 5 с ROS 2 Jazzy. В workspace собраны базовый драйвер шасси, одометрия, локализация, навигация, SLAM, камера, детекция объектов, лидар, Octoliner, светодиодная лента, голосовой ввод, веб-интерфейс, экранное приложение и диагностические средства.

Основные возможности:

- Запуск всего робота через `rover_bringup` с разделением на hardware, peripherals и ui launch-файлы.
- Управление mecanum-базой через `/cmd_vel` и драйвер моторной платы.
- Одометрия колёс, EKF-локализация и Nav2/SLAM Toolbox для карты и навигации.
- USB-камера с JPEG/MJPEG, сервисом `get_frame` и отдельной нодой детекции объектов.
- Веб-интерфейс для мониторинга ROS graph, управления движением, камеры, лидара, света, Octoliner, голосового распознавания, терминала, карт и hackathon-файлов.
- Экран Raspberry Pi с IP/hostname, статусом, технической информацией, настройками Wi-Fi и полноэкранной консолью.
- Поддержка Waveshare ESP32-S3 Audio Board как аудиоисточника для распознавания речи через Whisper.

Ключевые порты и страницы:

| Компонент | По умолчанию | Назначение |
|---|---|---|
| `rover_web` | `http://<ip>:8765` | основная веб-морда ровера |
| `ttyd` | `http://<ip>:7681` | веб-терминал робота |
| `rosboard` | `http://<ip>:8888` | отдельная страница просмотра ROS graph и сообщений |

## 2. Архитектура workspace

> Раскладка ниже — **устаревшая**. Актуальная — в [`01-arhitektura-i-pakety.md`](01-arhitektura-i-pakety.md).

```text
sverk_rover/
  src/
    rover_bringup/         # launch/config точка сборки системы
    rover_interfaces/      # custom msg/srv
    rover_description/     # URDF/Xacro и модель робота
    rover_navigation/      # Nav2, SLAM, карты/маршруты
    rover_localization/    # EKF конфиги
    rover_teleop/          # keyboard/mux управление
    rover_wheel_odometry/  # одометрия колёс
    rover_vision/          # обработка камеры и нейросети
    peripherals/           # драйверы внешних модулей
    ui/                    # веб-интерфейс, экран, rosboard
  maps/                    # карты Nav2/web-визуализации
  firmware/                # прошивки внешних модулей
  hackathon_files/         # регламенты, справочные файлы, этот PDF
```

Основные launch-файлы:

| Файл | Что запускает |
|---|---|
| `rover_bringup/launch/robot.launch.py` | Главный запуск: аппаратная часть, периферия, UI и системные ноды |
| `rover_bringup/launch/hardware.launch.py` | Базовое железо: моторная плата, IMU, лидар |
| `rover_bringup/launch/peripherals.launch.py` | Камера, детектор, лента, Octoliner, аудио |
| `rover_bringup/launch/ui.launch.py` | Веб, ttyd, rosboard, экранное приложение |
| `rover_bringup/launch/mapping.launch.py` | SLAM Toolbox для построения карты |
| `rover_bringup/launch/navigation.launch.py` | Nav2-навигация |
| `rover_bringup/launch/update_map.launch.py` | Обновление/сохранение карты |
| `rover_description/launch/display_*.launch.py` | Виды RViz: модель, лидар, одометрия, SLAM, навигация |
| `rover_localization/launch/localization.launch.py` | EKF |
| `peripherals/*/launch/*.launch.py` | Ленты, Octoliner, аудиомодуля |
| `ui/*/launch/*.launch.py` | Веб, экран, rosboard |

## 3. Запуск и режимы работы

```bash
cd ~/sverk_rover
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 launch rover_bringup robot.launch.py
```

| Команда | Назначение |
|---|---|
| `ros2 launch rover_bringup ui.launch.py` | Только веб-интерфейс, rosboard, ttyd и экран |
| `ros2 launch rover_bringup peripherals.launch.py` | Только периферия |
| `ros2 launch rover_bringup navigation.launch.py` | Nav2-навигация по карте |
| `ros2 launch rover_bringup mapping.launch.py` | SLAM и построение карты |
| `ros2 run rover_device_manager setup_devices` | Создание стабильных путей устройств |

Сборка:

```bash
cd ~/sverk_rover
PYTHONNOUSERSITE=1 colcon build --symlink-install
source install/setup.zsh
```

`PYTHONNOUSERSITE=1` полезен на ровере: пользовательские pip-пакеты конфликтуют с системными ROS/OpenCV/NumPy.

## 4. Пакеты ROS 2

19 пакетов (версии на 12.07.2026):

| Пакет | Версия | Назначение |
|---|---|---|
| `rover_base_driver` | 0.2.0 | `cmd_vel` → команды четырём моторам, обратная связь энкодеров |
| `rover_camera` | 0.1.0 | Драйвер USB-камеры |
| `rover_device_manager` | 0.4.1 | Автоопределение и проверка serial-устройств |
| `rover_imu` | 0.2.0 | Драйвер 10-осевой IMU Yahboom и нормализация |
| `rover_led_strip` | 0.1.0 | Драйвер адресной ленты |
| `rover_octoliner` | 0.1.0 | Драйвер датчика линии Amperka Octoliner |
| `rover_waveshare_audio` | 0.1.0 | Мост Whisper STT для ESP32-S3-AUDIO-Board |
| `sllidar_ros2` | 1.0.1 | Драйвер RPLIDAR A2/A1, A3/S1 |
| `rover_bringup` | 0.4.3 | Верхнеуровневый launch и конфигурация |
| `rover_description` | 0.4.2 | URDF/Xacro, TF-фреймы, виды RViz |
| `rover_interfaces` | 0.2.0 | Собственные интерфейсы |
| `rover_localization` | 0.2.0 | Конфигурация EKF (**пакета больше нет**) |
| `rover_navigation` | 0.4.3 | Nav2, AMCL, SLAM Toolbox |
| `rover_teleop` | 0.4.2 | WASD-телеоперация из терминала (**пакета больше нет**) |
| `rover_vision` | 0.1.0 | Обработка кадров и YOLO-подобная детекция |
| `rover_wheel_odometry` | 0.2.0 | Одометрия mecanum-базы |
| `rosboard` | 1.3.1 | ROSBoard |
| `rover_display` | 0.1.0 | Полноэкранный статус-дисплей |
| `rover_web` | 0.1.0 | Локальный веб-интерфейс, шлюз и исполнитель маршрутов |

## 5. Аппаратные подсистемы и периферия

| Модуль | Пакет/нода | Подключение | ROS-интерфейс |
|---|---|---|---|
| Моторная плата | `rover_base_driver` / `base_driver_node` | USB serial, стабильный путь; `/cmd_vel`; таймаут 0.5 с | `/wheel/encoders`, `/wheel/commands`, `/odom` через одометрию |
| IMU Yahboom | `rover_imu` / `yahboom_imu_node` | serial 921600, `/tmp/rover_devices/imu` | `/imu/data`, `/imu/mag`, `/imu/euler`, `/imu/valid_frame_count` |
| SLLidar | `sllidar_ros2` / `sllidar_node` | serial 460800, `/tmp/rover_devices/lidar` | `/scan` |
| USB-камера | `rover_camera` / `usb_camera_node` | `/dev/video0`, 1280×720, 30 FPS, MJPEG | `/image_raw`, `/image_raw/compressed`, `get_frame` |
| Детектор | `rover_vision` / `camera_detector_node` | модель из `models`, вход `/image_raw` | `/image_processed`, `/image_processed/compressed`, `/detections` |
| Octoliner | `rover_octoliner` / `octoliner_node` | I²C bus 1, адрес 0x2a (42) | `/octoliner/reading`, сервисы калибровки |
| Лента | `rover_led_strip` / `led_strip_node` | 16 диодов, SPI bus 1 device 0, WS2812 | `/led_strip/state`, `/led_strip/set_effect`, `/led_strip/set_leds` |
| Waveshare Audio | `rover_waveshare_audio` / `waveshare_audio_node` | serial `/dev/waveshare_audio`, 2 Мбит/с, WAV-чанки в Whisper | `/voice/text`, `/waveshare_audio/status` |

> Скорость IMU в PDF указана как 921600, в текущем `components/imu.yaml` — **115200**.

`rover_device_manager` нужен, чтобы USB-устройства не менялись местами после перезагрузки: он ищет реальные serial/by-path устройства и создаёт стабильные ссылки в `/tmp/rover_devices` (`motor_controller`, `imu`, `lidar`).

Лента: SPI-драйвер WS2812-подобной адресной ленты, в конфиге 16 диодов. При старте нода выполняет самотест. В веб-интерфейсе есть превью, покадровое управление каждым диодом и сохранение пользовательских кадров/пресетов.

Octoliner: 8 датчиков линии. Нода публикует значения сенсоров, рассчитанную позицию линии, признак обнаружения и служебное состояние; чувствительность и калибровка вынесены в настройки веб-интерфейса.

## 6. Топики, сервисы и интерфейсы

| Топик | Тип | Назначение |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | Команда скорости для базы |
| `/wheel/encoders` | `rover_interfaces/WheelEncoders` | Данные энкодеров |
| `/odom` | `nav_msgs/Odometry` | Одометрия для визуализации, Nav2 и веб-карты |
| `/imu/data` | `sensor_msgs/Imu` | Данные IMU |
| `/scan` | `sensor_msgs/LaserScan` | Лидар для SLAM/Nav2/визуализации |
| `/image_raw` | `sensor_msgs/Image` | Исходное изображение камеры |
| `/image_processed` | `sensor_msgs/Image` | Кадр после обработки, с рамками |
| `/detections` | `std_msgs/String` | JSON: class, confidence, bbox |
| `/led_strip/state` | `rover_interfaces/LedStripState` | Состояние ленты и текущий эффект |
| `/octoliner/reading` | `rover_interfaces/OctolinerReading` | 8 датчиков линии и производное состояние |
| `/voice/text` | `std_msgs/String` | Распознанный Whisper текст |
| `/agent/text` | `std_msgs/String` | Сообщения агента для экранного приложения |

Сервисы: `GetFrame` (один кадр без подписки на поток), `SetLEDEffect`, `SetLEDs`, `SetLedStripState`, `SetSensitivity`, а также `std_srvs/Trigger` для калибровки Octoliner на белом/чёрном поле.

## 7. Веб-интерфейс и экран

`web_gateway_node` слушает `0.0.0.0:8765`, работает с графом ROS напрямую через `rclpy`, отдаёт статические страницы, hackathon-файлы, карты, терминал и интеграции.

| Страница | Функциональность |
|---|---|
| Главная | Сводка, быстрые кнопки ROSboard/терминала, общее состояние |
| ROS State | Топики, сервисы, ноды; просмотр сообщений, публикация, вызов сервисов |
| Движение | WASD, маршруты, визуализация одометрии и карты |
| Периферия | Камера, лидар, свет, Octoliner, распознавание голоса, сервоприводы |
| Терминал | Встроенный ttyd и кнопка перезапуска |
| Диагностика | Системная загрузка, счётчики ROS, позиция/скорость, диагностика устройств |
| Настройки | Камера, лидар, LED, Octoliner, видимость сервоприводов и прочее |
| Хакатон | Просмотр md/html/pdf из `hackathon_files` |

Экран `rover_display`: сверху компактная панель с `sverk_rover_<serial>` и IP (по нажатию — настройки Wi-Fi), слева техническое состояние, снизу кнопка полноэкранной консоли. Правая часть выбирается параметром: заглушка либо hackathon-вид с батареей и текстом агента из `/agent/text`.

| Параметр | Значение |
|---|---|
| `wifi_interface` | `wlan0` |
| `netplan_path` | `/etc/netplan/50-cloud-init.yaml` |
| `agent_text_topic` | `/agent/text` |
| `battery_topic` | `/battery/state` |
| `console_shell` | `/bin/bash` |

## 8. Камера, распознавание объектов и карты

| Параметр камеры | Значение |
|---|---|
| Устройство | `/dev/video0` |
| Разрешение | 1280×720 @ 30 FPS |
| Топики | `/image_raw`, `/image_raw/compressed` |
| Сервис кадра | `get_frame` |
| Формат | MJPEG=True, JPEG quality=85 |

`camera_detector_node`: фиксированная модель из папки `models` пакета, вход `/image_raw`, выход `/image_processed` и `/image_processed/compressed`, отдельный `/detections` с JSON. Параметры: `enabled`, `input_topic`, `output_topic`, `detections_topic`, `confidence_threshold`, `nms_threshold`.

Карты — стандартный формат Nav2: YAML с `resolution`/`origin` и PGM/PNG с occupancy grid. `resolution=0.05` означает 5 см на клетку; веб-визуализация накладывает одометрию с тем же масштабом.

## 9. Навигация, SLAM и локализация

| Компонент | Настройка |
|---|---|
| AMCL | `robot_model_type: nav2_amcl::OmniMotionModel` |
| Планировщик | `NavFnPlanner` |
| Контроллер | `DWBLocalPlanner` |
| Костмапы | глобальный и локальный; слои obstacle/voxel/inflation |
| Сенсор | `/scan` (`LaserScan`) |
| Разрешение карты | обычно 0.05 м/клетку |

`mapping.launch.py` поднимает SLAM Toolbox для построения карты по `/scan` и `/odom`. `rover_localization` хранит EKF-конфиги: wheel-only и вариант с IMU; одометрия колёс публикует `/odom` из энкодеров.

## 10. Голосовой модуль Waveshare

| Часть | Что делает |
|---|---|
| Прошивка ESP32-S3 | Аудиоисточник: I²S-микрофон → serial-пакеты/WAV-поток |
| `rover_waveshare_audio` | Принимает звук, запускает Whisper, публикует текст |
| Конфиг | `serial_port`, `baudrate`, `whisper_model`, `language`, `output_text_topic` |
| Выход | `/voice/text` и статусный топик |

Модель Whisper: `tiny`/`base`/`small`/`medium`/`large`. На Raspberry Pi разумно начинать с `base` или `small`; `large` потребует существенно больше CPU/RAM и времени.

## 11. Конфиги и важные файлы

> Пути в этом разделе PDF устарели целиком. Актуальные — в [`02-zapusk-profili-i-konfigi.md`](02-zapusk-profili-i-konfigi.md).

| Файл (по PDF) | Что важно |
|---|---|
| `src/rover_bringup/config/rover.yaml` | Геометрия робота, base_driver, IMU, одометрия, общие параметры |
| `src/rover_bringup/config/peripherals.yaml` | Лидар, камера, vision, LED, Octoliner, аудио |
| `src/rover_bringup/config/ui.yaml` | Связка UI launch, экран и веб-компоненты |
| `src/ui/rover_web/config/web.yaml` | Порты веба/терминала/rosboard, `maps_root`, `hackathon_files_root`, `servo_enabled`, топики |
| `src/ui/rover_display/config/display.yaml` | Экран, Wi-Fi, netplan, топики агента/батареи, консоль |
| `src/rover_navigation/config/nav2_params.yaml` | Параметры Nav2 |
| `src/rover_navigation/config/slam_toolbox_params.yaml` | Параметры SLAM Toolbox |
| `src/rover_localization/config/*.yaml` | EKF wheel-only и с IMU |

Папка `hackathon_files` используется веб-страницей «Хакатон»: туда кладут Markdown, HTML и PDF — регламенты, задания, инструкции, чек-листы и сам этот документ.

## 12. Проверка, диагностика и типовые проблемы

```bash
ros2 node list
ros2 topic list
ros2 service list
ros2 topic echo /cmd_vel
ros2 topic echo /wheel/encoders
ros2 topic echo /odom

ros2 topic hz /image_raw
ros2 topic echo /detections
ros2 service call /usb_camera_node/get_frame rover_interfaces/srv/GetFrame "{}"

ros2 topic echo /led_strip/state
ros2 service list | grep led
ros2 topic echo /octoliner/reading
ros2 service call /octoliner/optimize_on_black std_srvs/srv/Trigger "{}"
ros2 topic echo /voice/text
ros2 topic echo /waveshare_audio/status
```

| Симптом | Причина/решение |
|---|---|
| `Configured motor_controller path is unavailable` | Изменился USB-путь. Проверить кабели или заново выполнить `setup_devices` |
| `cv2` падает из-за NumPy 2.x | Запускать web/camera/vision с `PYTHONNOUSERSITE=1`; для сборки — `PYTHONNOUSERSITE=1 colcon build` |
| Веб не открывается | Проверить `http://<ip>:8765`, firewall, привязку к `0.0.0.0`, сеть |
| Терминал «reconnecting» | Проверить ttyd, `rover_terminal_shell.sh`, рабочую директорию и права пользователя `pi` |
| Лента не светит | Проверить SPI bus/device, MOSI, питание ленты, общую землю, `led_count=16` |
| Octoliner не стартует из-за board revision | Использовать текущий драйвер без старого определения ревизии Pi; проверить шину и адрес I²C |
| Whisper не загружается | Проверить `openai-whisper`/`torch`, совместимость `setuptools`/`coverage`, `/dev/waveshare_audio` |
| Карта в вебе не совпадает с роботом | Визуализация использует `/odom` как координаты карты; стартовать из origin либо учитывать `map→odom` |

Минимальный чек-лист перед хакатоном:

- Собрать workspace и выполнить `source install/setup.zsh`.
- Проверить стабильные пути устройств через `rover_device_manager`.
- Запустить `ui.launch.py` и открыть веб с ноутбука.
- Проверять `/cmd_vel` только на безопасной скорости; первый тест — с колёсами в воздухе.
- Проверить `/image_raw`, `/detections`, `/scan`, `/odom`, `/led_strip/state`, `/octoliner/reading`, `/voice/text`.
- Положить регламенты и этот PDF в `hackathon_files`, карты — в `maps/`.
