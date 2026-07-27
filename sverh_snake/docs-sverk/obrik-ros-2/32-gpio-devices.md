# Подключение внешних устройств

> Раздел: Обрик ROS 2 · slug: `gpio-devices`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/gpio-devices

---

# Подключение внешних устройств


К бортовому компьютеру Обрика можно подключать самую разную периферию: кнопки, концевики, реле, электромагниты, индикаторы, Arduino-устройства, датчики по I2C и SPI.


На этой странице описаны все доступные интерфейсы. Для конкретных устройств есть отдельные подробные страницы:

- [Лазерные дальномеры VL53L1X](/learn/obrik-ros-2/sensor-vl53l1x)
- [Сервоприводы](/learn/obrik-ros-2/servo-control)

---


## Схема интерфейсов


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fgpio-interfaces.svg&sig=e9d9e2be97292645027bebf4a15ef7ba813e57744979a7fc5cba519ff0e53f70)



---


Управление цифровыми пинами (OUTPUT/INPUT) из Python — в статье [Работа с GPIO](/learn/obrik-ros-2/gpio).


---


## PWM — управление сервоприводами


**PWM** (Широтно-импульсная модуляция) — способ управлять мощностью через быстрое включение/выключение. Сервопривод понимает, в какое положение повернуться, по длительности импульса.


Подробнее: [Использование сервоприводов](/learn/obrik-ros-2/servo-control)


---


## I2C — подключение датчиков


**I2C** — шина для датчиков, когда надо подключить несколько устройств к двум проводам. По одной паре (SDA + SCL) можно повесить несколько датчиков с разными адресами.


Проверить, что устройство видно на шине (диагностика):


```
# Покажет адреса всех подключённых I2C-устройств
i2cdetect -y 1

```


>

**Примечание** Эти команды выполняются **внутри контейнера** `sverk_ros2`. Устройства видны благодаря монтированию `/dev` в docker compose.


**Что делает программа:** сканирует шину I2C и печатает адреса найденных устройств.


```
import board
import busio

# Инициализируем шину I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Захватываем шину перед работой
while not i2c.try_lock():
    pass

try:
    # Получаем список адресов всех подключённых устройств
    addresses = [hex(addr) for addr in i2c.scan()]
    print(f"Найдено устройств: {addresses}")
finally:
    i2c.unlock()  # освобождаем шину

```


Если подключаете лазерный дальномер VL53L1X — смотрите сюда: [Использование VL53L1X](/learn/obrik-ros-2/sensor-vl53l1x)


---


## SPI — быстрый обмен данными


SPI используется, например, для LED-ленты. Сначала убедитесь, что устройство видно (диагностика):


```
# Должны появиться файлы /dev/spidev0.0 или похожие
ls /dev/spidev*

```


>

**Примечание** Эти команды выполняются **внутри контейнера** `sverk_ros2`. Устройства видны благодаря монтированию `/dev` в docker compose.


>

**Примечание** GPIO-контроллер одинаков на всех платах — `/dev/gpiochip0`. Различия по другим интерфейсам (UART, SPI, камера) → [Бортовые компьютеры](/learn/obrik-ros-2/boards-overview).


После этого используйте библиотеку, подходящую для вашего модуля.


---


## UART и USB — связь с Arduino


В системе доступны UART-интерфейсы и USB-порты для подключения Arduino и других последовательных устройств.


>

**Примечание** Для подключения используйте `UART_B` — `UART_A` занят полётным контроллером PX4.


Проверить, что устройство подключено (диагностика):


```
ls /dev/ttyAMA*   # UART-порты бортового компьютера
ls /dev/ttyUSB*   # USB-serial адаптеры
ls /dev/ttyACM*   # Arduino по USB

```


>

**Примечание** Эти команды выполняются **внутри контейнера** `sverk_ros2`. Устройства видны благодаря монтированию `/dev` в docker compose.


### Получение данных от Arduino через serial_bridge


Arduino данные приходят в ROS 2 через пакет `serial_bridge`. Нода-мост читает последовательный порт и публикует сообщения в топик. В программе подписка на этот топик выполняется через `drone.topic.subscribe()` — не нужно работать с портом напрямую.


**Что делает программа:** подписывается на данные от Arduino (например, показания датчика расстояния) и обрабатывает их в коллбэке.


```
import time
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="gpio_example")

def on_arduino_data(msg):
    """Вызывается при каждом сообщении от Arduino."""
    # msg.data — строка с данными, которые отправил Arduino
    print(f"Данные от Arduino: {msg.data}")

# Подписываемся на топик serial_bridge
# Топик '/serial/rx' — данные, пришедшие с Arduino в Обрик
sub = drone.topic.subscribe(String, '/serial/rx', on_arduino_data)

try:
    # Крутим спин 5 секунд, получаем данные
    end = time.time() + 5.0
    while time.time() < end:
        drone.topic.spin_once()
        time.sleep(0.01)
finally:
    drone.topic.unsubscribe(sub)
    drone.close()

```


**Отправить команду на Arduino** (публикация в топик):


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="gpio_example")

# Создаём публикатор в топик '/serial/tx' — данные уйдут из Обрика на Arduino
pub = drone.topic.create_publisher(String, '/serial/tx')

msg = String()
msg.data = "ping\n"          # строка, которую получит Arduino
pub.publish(msg)

drone.close()

```


>

**Примечание** Пакет `arduino-serial` должен быть запущен отдельно: `ros2 launch arduino-serial bridge.launch.py`. Смотрите [arduino-rosserial-tutorial.md](/learn/obrik-ros-2/arduino-rosserial-tutorial).


>

**Подсказка** Подробнее о реализации GPIO — [gpio-raw.md](/learn/obrik-ros-2/gpio-raw).
