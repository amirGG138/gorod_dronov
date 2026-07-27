# Периферия и железо

## Сводная таблица

| Модуль | Нода | Подключение | ROS-интерфейс |
|---|---|---|---|
| Моторная плата | `base_driver_node` | USB serial, 115200, путь `/tmp/rover_devices/motor_controller` | `/cmd_vel` → `/wheel/encoders`, `/wheel/commands`, `/battery_voltage` |
| IMU Yahboom | `yahboom_imu_node` | serial 115200, `/tmp/rover_devices/imu` | `/imu/data`, `/imu/mag`, `/imu/euler`, `/imu/valid_frame_count` |
| Лидар SLLIDAR C1 | `sllidar_node` | serial 460800, `/tmp/rover_devices/lidar` | `/scan` |
| Фильтр корпуса | `lidar_footprint_filter` | — | `/scan` → `/scan_filtered` |
| USB-камера | `usb_camera_node` | `/dev/video0` | `/image_raw`, `/image_raw/compressed`, сервис `get_frame` |
| Детектор | `camera_detector_node` | — | `/image_processed`, `/detections` |
| Лента WS2812 | `led_strip_node` | SPI bus 1, device 0, 16 диодов | `/led_strip/state`, `/led_strip/set_state` |
| Octoliner | `octoliner_node` | I²C bus 1, адрес 42 (0x2a) | `/octoliner/reading` + сервисы |
| Waveshare ESP32-S3 Audio | `waveshare_audio_node` | serial `/dev/waveshare_audio`, 2 Мбит/с | `/voice/text`, `/voice/transcript`, `/waveshare_audio/status`, сервис `/voice/say` |

## Диспетчер устройств

`rover_device_manager` не даёт USB-устройствам меняться местами после перезагрузки: он ищет реальные serial/by-path устройства и создаёт стабильные симлинки в `/tmp/rover_devices/`.

```bash
ros2 run rover_device_manager setup_devices     # разовая настройка, пишет ~/.config/rover/devices.json
ros2 run rover_device_manager discover_devices  # диагностический поиск
```

Режимы (`discovery_mode`, он же `ROVER_DISCOVERY_MODE`):

| Режим | Поведение |
|---|---|
| `configured` | использовать сохранённые пути, ничего не искать — быстрый штатный старт |
| `verify` | проверить, что сохранённые устройства на месте |
| `full` | полный поиск заново |

Обязательными считаются `motor_controller`, `imu`, `lidar` (`components/device_manager.yaml`). Профиль `agent` запускается вообще без discovery.

## Шасси и одометрия

Mecanum-кинематика в `rover_base_driver/kinematics.py`, протокол платы — `quad_md_protocol.py` (текстовые кадры, напряжение приходит строкой `$Battery:` и запрашивается раз в 5 с).

Ограничения из `components/base.yaml`: `max_wheel_speed_mps 0.35`, управление на 50 Гц, таймаут команды 0.5 с, таймаут обратной связи 0.35 с, полный набор лимитов ускорения/торможения/рывка по каждой оси.

Калибровка энкодеров (`rover_v1.yaml`): 11 линий, редукция 45:1, квадратура ×4. Порядок и знаки моторов (`motor_command_order: [3,1,2,0]`, знаки `-1`) компенсируют фактическую разводку — при перестановке моторов правится здесь, а не в коде.

Одометрия (`rover_wheel_odometry`) отбрасывает выборки с разрывом > 0.5 с и скоростью колеса > 1.5 м/с.

## Лидар и фильтр корпуса

`components/lidar.yaml`: модель `sllidar_c1`, `serial_baudrate 460800` (перебор при старте: 460800, 115200, 256000, 1000000), `scan_mode: Standard`, `scan_frequency: 10.0`, `range_min: 0.17`, `frame_id: lidar_link`, `inverted: false`, `angle_compensate: true`.

Лидар развёрнут на 180° относительно `base_link` (`lidar_rpy: [0, 0, π]`) — фильтр `rover_lidar_filter` учитывает это через TF, а не угловыми масками, поэтому при перестановке лидара достаточно поправить URDF. `padding_m: 0.025`, `tf_timeout_sec: 0.05`.

## Камера и зрение

`components/camera.yaml`: `/dev/video0`, 1280×720 @ 30 FPS, MJPEG, JPEG q=85, переподключение раз в 2 с.

`components/vision.yaml`: **по умолчанию `enabled: false`**. Модель `ssd_mobilenet_v1_coco_2017_11_17` из `package://rover_vision/models` (в комплекте также `yolov5n.onnx`), пороги `confidence 0.30` / `nms 0.45`, ограничение `max_processing_fps: 10.0`. Детекции публикуются JSON-строкой в `/detections`.

## Светодиодная лента

`components/led_strip.yaml`: транспорт `auto` (реализация — WS2812 поверх `spidev`), SPI bus 1 device 0, 16 диодов, стартовая яркость 0.35, цвет `#16B8F3`, самотест при старте (последовательный прогон диодов, 0.06 с шаг), анимация 30 Гц, публикация состояния 5 Гц. `enabled: false` — лента при старте погашена.

Проводка: данные на `GPIO18`. **Не вешайте данные на `GPIO2`** — это SDA шины I²C, конфликтует с Octoliner. Для Pi 5 нужен стек `Adafruit-Blinka` + `Adafruit-Blinka-Raspberry-Pi5-Neopixel`.

## Octoliner

8 датчиков линии, I²C bus 1, адрес 42, опрос 50 Гц, чувствительность 0.8, автокалибровка при старте выключена. Сервисы: `/octoliner/set_sensitivity`, `/octoliner/optimize_on_black` (`std_srvs/Trigger`). Публикует и «сырые» 8 каналов, и производные: битовый паттерн, число тёмных датчиков, признак видимости линии, позицию линии и её сглаженное значение.

## Звук: Waveshare ESP32-S3 Audio Board

Плата работает аудиоисточником: I²S-микрофон → кадры `PCM1` по USB Serial/JTAG (16 кГц, моно, s16le, кадры по 320 сэмплов). ROS-нода собирает высказывания и распознаёт их Whisper.

`components/audio.yaml`: `whisper_model: base`, `language: ru`, `min_rms: 350`, `start_frames: 3`, `stop_frames: 35`, `pre_roll_frames: 8`, максимум 12 с на высказывание.

Обратный канал — синтез речи: сервис `/voice/say` (`rover_interfaces/SpeakText`), движок **Piper**, голос `ru_RU-irina-medium`, файлы в `~/sverk_rover/tts_voices`, аудио уходит на плату кадрами `SPK1`. Установка голоса — `tools/install_piper_ru_voice.sh`.

Прошивки в `firmware/`: `speech-stream-stt` (рабочая, для ROS STT/TTS) и `speech-command-test` (локальный тест wake-word на ESP-SR). Прошивать:

```bash
cd install/rover_waveshare_audio/share/rover_waveshare_audio/firmware/speech-stream-stt
PORT=/dev/ttyACM0 ./flash.sh     # на Raspberry Pi
```

Хостовые зависимости: `python3 -m pip install -U openai-whisper` плюс подходящая сборка PyTorch. На Pi модели крупнее `small` брать не стоит.

Правило udev для устойчивого имени платы — `udev/99-rover-waveshare-audio.rules`.

## Веб-интерфейс

`web_gateway_node` слушает `0.0.0.0:8765`, общается с графом ROS напрямую через `rclpy`. Страницы: главная, ROS State (топики/сервисы/ноды, просмотр и публикация сообщений, вызов сервисов), движение (WASD, маршруты, одометрия и карта), периферия, терминал (iframe ttyd), диагностика, настройки, «Хакатон» (просмотр md/html/pdf из `hackathon_files`).

Скорости по умолчанию: линейная 0.18, боковая 0.16, угловая 0.70 рад/с; потолки 0.35 / 0.35 / 1.50. Таймаут команды из веба 0.25 с, удержание стопа 0.75 с. Каталоги: планы — `~/.local/share/sverh-rover-web/plans`, карта — `maps/current`, файлы хакатона — `~/sverk_rover/hackathon_files`.

## Экран Raspberry Pi

`rover_status_display_node` — полноэкранное приложение: сверху `sverk_rover_<serial>` и IP (по тапу — настройки Wi-Fi через `/usr/local/sbin/rover-wifi-config.py` и `/etc/netplan/50-cloud-init.yaml`), слева техническое состояние, снизу кнопка полноэкранной консоли. Правая панель переключается параметром `right_panel_mode`: заглушка или «хакатонный» вид с батареей и текстом агента из `/agent/text`.

Тема: фон `#07141C`, панели `#0C202B`, акцент `#16B8F3` — тот же акцентный цвет, что и дефолтный цвет ленты.
