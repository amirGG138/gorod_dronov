# Модуль связи Рой ESP-NOW

> Раздел: Обрик ROS 1 (Clover) · slug: `swarm`
> Источник: https://edu.sverk.tech/learn/clover-2/swarm

---

# Модуль связи Рой ESP-NOW


## Комплексная система коммуникации для роя дронов на базе протокола ESP-NOW


### Обзор системы


Модуль обеспечивает взаимодействие дронов в рое через ESP-NOW протокол. Это готовый “язык общения” для группы квадрокоптеров, чтобы они могли летать вместе, как стая птиц, и не сталкиваться.


**Рой дронов** — это группа из нескольких дронов, которые летают вместе, общаются между собой и выполняют одну задачу согласованно, как одно целое. Каждый дрон оборудован модулем ESP32, который отвечает за беспроводную передачу пакетов между дронами, в то время как Raspberry Pi управляет полетом и логикой миссии.


### Основные возможности системы

- Широковещательная передача телеметрии (данные о состоянии дрона: его координаты, высота, скорость, заряд батареи и т.д) в реальном времени
- Отправка пользовательских сообщений между дронами ( например, “собраться в круг”)
- Алгоритмы предотвращения столкновений
- Скоординированное роевое взаимодействие
- Автоматическое обнаружение дронов в сети

### Архитектура системы


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F1.png&sig=481e7e8ab992dbb18926af3d33e2c306fd17710921aa527a1d84cd627716430c)



#### Схема передачи данных

- Главный компьютер (Raspberry Pi 1) решает, что нужно передать другим дронам. Он отправляет команду ESP32 #1 через проводное соединение UART (очень простой и быстрый кабель для передачи данных).
- ESP32 #1 берет эту команду и транслирует ее по протоколу ESP-NOW всем другим модулям ESP32 поблизости.
- Другие ESP32, получив сообщение, передают его по проводу UART уже своим главным компьютерам (Raspberry Pi #N). Так команда доходит до другого дрона.

#### Структура проекта


<pre> clover-swarm-espnow/ ├── esp/ # прошивка ESP32 │ ├── src/ # исходный код │ │ ├── main.cpp # основная точка входа в прошивку │ │ ├── ESPNowManager.cpp # управление коммуникацией ESP-NOW │ │ ├── ConfigManager.cpp # управление конфигурацией │ │ ├── PacketDeserializer.cpp # утилиты парсинга пакетов │ │ ├── Statistics.cpp # статистика сети │ │ └── telemetry_generator.cpp # Генерация данных телеметрии │ ├── data/ # файлы конфигурации │ │ ├── config.json # основная конфигурация │ │ └── espnow_config.json # специальные настройки ESP-NOW │ ├── platformio.ini # конфигурация сборки PlatformIO │ └── test/ # тесты прошивки ├── skyros/ # библиотека Python для Raspberry Pi │ ├── src/skyros/ # основной исходник библиотеки │ │ ├── [drone.py](http://drone.py) # основной интерфейс дрона │ │ ├── collision_avoidance/ # алгоритмы предотвращения столкновений │ │ └── drone_data.py # структуры данных │ ├── examples/ # примеры использования │ │ ├── [example.py](http://example.py) # базовый пример использования │ │ ├── complex_example.py # продвинутая координация роя │ │ └── example_stress_usage.py # стресс-тесты │ └── test/ # тесты Python библиотеки │ ├── [stationary.py](http://stationary.py) # стационарные испытания дронов │ ├── [stress.py](http://stress.py) # стресс-тест сети │ └── network_performance_test.py # тесты производительности └── esp_controller/ # Прошивка контроллера ESP32 для OTA </pre>


### Инструкции по настройке


#### Прошивка ESP32


Примечание: Данная инструкция предназначена для разработки и обновления прошивки. На предварительно настроенных дронах прошивка ESP32 уже должна быть установлена.


>

**Caution** Убедитесь, что дроны выключены перед началом работ

-

Подключение оборудования Подключите Raspberry Pi UART4 к ESP32C3 super mini UART1:

  - TX (RPi GPIO8) → RXD (ESP GPIO3/D3)
  - RX (RPi GPIO9) → TXD (ESP GPIO4/D4)
  - CTS (RPi GPIO10) → RTS (ESP GPIO5/D5)
  - RTS (RPi GPIO11) → CTS (ESP32 GPIO6/D6)
  - VCC (RPi 5V) → VCC (ESP32 5V)
  - GND (RPi GND) → GND (ESP32 GND)<br>
-

Сборка и загрузка прошивки

  - Загрузка предварительно собранного бинарного файла

Инструмент для прошивки esptool:


```
pip install esptool

```

  - ESP32 к компьютеру по USB
  - Определите порт:
    - Linux: /dev/ttyACM0, /dev/ttyUSB0
    - Windows: COM3, COM4
    - macOS: /dev/tty.usbserial-*

#### Прошивка ESP32C3 Super Mini

-

Сотрите флэш-память:


```
esptool.py --chip esp32c3 --port /dev/ttyACM* erase_flash

```

-

Загрузите прошивку (включая загрузчик и таблицу разделов)


```
esptool.py --chip esp32c3 --port /dev/ttyACM0 --baud 921600 \
--before default_reset --after hard_reset write_flash \
0x0 firmware_esp32c3_super_mini_prod_merged.bin

```

-

Первый запуск (важно!)


При первой прошивке ESP32-C3 может потребоваться до 30 секунд для инициализации файловой системы SPIFFS. Это нормальное поведение — не отключайте питание и не прерывайте процесс.


#### Настройка Raspberry Pi

-

Включение UART на Raspberry Pi


Отредактируйте файл: `/boot/config.txt`:

  - В терминале выполните

```
sudo nano /boot/config.txt

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F2.png&sig=3ee4b5a2ae681e727a7352b29c0f4ff6ce4ab78744bab1917bd70fe8bedc8faa)


  - Найдите (или добавьте в конец) следующие строки:

```
[all]
dtoverlay=pi3-disable-bt
dtoverlay=uart0,ctsrts
dtoverlay=uart4,ctsrts
enable_uart=1

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F3.png&sig=fd234d9f00dd445f1b17061002bda1d37afbc39c37f616fdf6482677e5c78d2a)


  - Отключите Bluetooth используя следующие команды:

```
sudo systemctl disable hciuart
sudo systemctl disable bluetooth

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F4.png&sig=a8693bc268a0cf9e608a1fc77a2e84c1edd353e4ec3185baabedf87e94179032)


  - Перезагрузите Raspberry Pi командой:

```
sudo reboot

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F5.png&sig=c33829c620a9f9602a6adc4b55d6af220b05b316774a069a59eeeca6de5d3783)


-

Установка Python-библиотеки


```
cd skyros/
pip install -e

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F6.png&sig=9fa3ca0a80e9ed85904b4844426d967ba6c4e14799c50f0a578704c2057cbc15)


-

Развертывание на нескольких дронах


Для одновременного развертывания кода на несколько дронов используйте Ansible Deployment Guide.


### Примеры использования


Директория `skyros/examples/` содержит примеры для различных сценариев:

-

Базовое использование (`example.py`)

  - Инициализация дрона;
  - Основные команды управления полетом;
  - Обнаружение дронов в сети;
  - Мониторинг статуса;
  - Базовая навигация с предотвращением столкновений

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fswarm%2F7.png&sig=c7e51e4e867645f8eb36009b710eee0c746ca2a5ac1d42b379516326883b657b)



```
cd skyros/
python …

```

-

Координация роя (`complex_example.py`)

  - Мастер-слейв координация дронов;
  - Обработка пользовательских сообщений для скоординированного ;
  - Индивидуальный таргетинг и контроль дронов<br>
-

Стресс-тестирование (`example_stress_usage.py`)


Проверка производительности сети под нагрузкой

  - Сценарии координации нескольких дронов;
  - Мониторинг телеметрии;
  - Отслеживание сетевого статуса;
  - Полезно только для отладки и проверки производительности сети.

**Ключевые функции:**

- Обнаружение дронов: автоматическое обнаружение других дронов с помощью телеметрии
- Предотвращение столкновений: встроенные алгоритмы для безопасного полёта роя
- Пользовательские сообщения: широковещательная и целевая передача
- Мониторинг сети: отслеживание состояния и производительности в режиме реального времени
- Скоординированный полёт: синхронный взлет, навигация и посадка

### Продвинутое тестирование


Стационарное тестирование (`skyros/test/stationary.py`)


Используйте для диагностики сетевых проблем:

-

**Подготовка**:

  - Разместите дроны на маркерах ArUco
  - Обеспечьте контролируемые условия<br>
-

**Мониторинг**: Тест предоставляет информацию в режиме реального времени о:

  - Состоянии сетевого подключения
  - Обнаруженных позициях дронов и расстояниях до них
  - Расчетах векторов предотвращения столкновений
  - Приеме телеметрических пакетов
  - Показатели успешности передачи сообщений
-

**Запуск**:


```
cd skyros/test/
python3 stationary.py

```

-

**Что показывает тест**:

  - Измерение расстояний между дронами
  - Координаты местоположения всех обнаруженных дронов
  - Сетевая задержка и статистика пакетов
  - Данные телеметрии в реальном времени<br>
-

**Дополнительные тесты**:

  - `network_performance_test.py` — проверка пропускной способности
  - `stress.py` — тестирование под высокой нагрузкой
  - `esp_simple_test.py` — проверка функциональности ESP32
