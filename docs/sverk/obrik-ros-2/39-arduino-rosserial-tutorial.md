# Примеры работы с Arduino

> Раздел: Обрик ROS 2 · slug: `arduino-rosserial-tutorial`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/arduino-rosserial-tutorial

---

# Примеры работы с Arduino


>

**Примечание** На дроне два UART. Для подключения используйте `UART_B` — `UART_A` занят полётным контроллером PX4.


Практические примеры работы с Arduino через rosserial_ros2. Каждый раздел — отдельный законченный сценарий.


>

**Примечание** Сначала прочитайте: [Знакомство с rosserial_ros2](/learn/obrik-ros-2/arduino-rosserial)


---


## Подготовка


### Установить библиотеку на Arduino IDE

- Скопируйте папку `ros_lib` из `<rosserial_ros2>/libraries/ros_lib`
- Упакуйте её в zip-архив
- В Arduino IDE: `Sketch → Include Library → Add .ZIP Library...`
- Перезапустите Arduino IDE
- Примеры появятся в меню: `File → Examples → Examples from Custom Libraries → rosserial_ros2`

### Собрать bridge на Обрике


```
mkdir -p ~/ros_ws/src
cp -r <rosserial_ros2>/rosserial_ros2_bridge ~/ros_ws/src/

cd ~/ros_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select rosserial_ros2_bridge
source install/setup.bash

```


### Запустить bridge


>

**Примечание** Arduino подключают к свободному порту **UART_B** (или по USB). Имя UART_B зависит от платы: RPi CM5 — `/dev/ttyAMA10`, Orange Pi Zero 3W — `/dev/ttyS6`, Orange Pi 5 Pro — `/dev/ttyS1`. UART_A занят полётным контроллером — туда подключать нельзя. Полная таблица интерфейсов по платам → [Бортовые компьютеры](/learn/obrik-ros-2/boards-overview).


```
# USB
ros2 run rosserial_ros2_bridge bridge_node --port /dev/ttyUSB0 --baud 57600

# UART (используйте UART_B — UART_A занят PX4)
ros2 run rosserial_ros2_bridge bridge_node --port /dev/ttyAMA3 --baud 57600

# TCP (если Arduino на другом компьютере)
ros2 run rosserial_ros2_bridge bridge_node --port socket://192.168.1.100:7777

```


---


## Сценарий 1: Публикация строки из Arduino


**Что делает программа:** Arduino каждую секунду отправляет строку, она появляется в ROS 2 топике.


Скетч из примеров: `File → Examples → rosserial_ros2 → rosserial_chatter`


Прошейте Arduino и запустите bridge. Проверить диагностически:


```
ros2 topic list | grep chatter
ros2 topic echo /chatter
# Ожидаемый вывод:
# data: hello from nano

```


Читать данные в Python:


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="rosserial_example")

def on_chatter(msg):
    print(f"Arduino: {msg.data}")

drone.topic.subscribe(String, '/chatter', on_chatter)
drone.topic.spin()

drone.close()

```


---


## Сценарий 2: Управление светодиодом из ROS 2


**Что делает программа:** отправляет команду из Python, Arduino включает/выключает встроенный светодиод.


Скетч: `File → Examples → rosserial_ros2 → rosserial_led_subscriber`


После прошивки и запуска bridge:


```
import sverk_interfaces
from std_msgs.msg import Bool

drone = sverk_interfaces.init(Nodename="rosserial_example")

pub = drone.topic.create_publisher(Bool, '/led')
cmd = Bool()

# Включить светодиод
cmd.data = True
pub.publish(cmd)

# Проверить состояние через подписку
msg = drone.topic.wait_for_message(Bool, '/led_state', timeout=3.0)
if msg:
    print(f"Состояние светодиода: {msg.data}")

# Выключить
cmd.data = False
pub.publish(cmd)

drone.close()

```


---


## Сценарий 3: Arduino как сервер сервиса


**Что делает программа:** из Python вызывает сервис на Arduino, Arduino управляет светодиодом и отвечает.


Скетч: `File → Examples → rosserial_ros2 → rosserial_set_bool_service_server`


Проверить, что сервис появился:


```
ros2 service list | grep set_led

```


Вызов сервиса из Python:


```
import sverk_interfaces
from std_srvs.srv import SetBool

drone = sverk_interfaces.init(Nodename="rosserial_example")

# включить светодиод на Arduino через сервис
resp = drone.service.call("/set_led", SetBool, data=True)
print("Ответ Arduino:", resp.success, resp.message)

drone.close()

```


>

**Примечание** Прямой вызов сервисов через CLI — см. [knowledge_base/arduino-raw.md](/learn/obrik-ros-2/arduino-raw).


---


## Сценарий 4: Arduino вызывает сервис ROS 2


**Что делает программа:** Arduino периодически вызывает сервис на Обрике. Полезно, когда Arduino следит за датчиком и сообщает о событиях.


Скетч: `File → Examples → rosserial_ros2 → rosserial_trigger_service_client`


На стороне Python сервер для приёма вызовов от Arduino:


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="rosserial_example")

# Подписываемся на топик, в который Arduino пишет результат триггера
trigger_count = 0

def on_trigger(msg):
    global trigger_count
    trigger_count += 1
    print(f"Arduino вызвала триггер #{trigger_count}: {msg.data}")

drone.topic.subscribe(String, '/nano_trigger_result', on_trigger)
drone.topic.spin()

drone.close()

```


>

**Примечание** Если Arduino использует сервис (`std_srvs/Trigger`) — нужен сервер на стороне ROS 2. Пример через rclpy — в [knowledge_base/arduino-raw.md](/learn/obrik-ros-2/arduino-raw).


---


## Сценарий 5: Параметры, логи и время


**Что делает программа:** Arduino читает параметры от bridge, отправляет логи, синхронизирует время с ROS 2.


Скетч: `File → Examples → rosserial_ros2 → rosserial_time_log_param_test`


Запуск bridge с параметрами (Arduino их прочитает):


```
ros2 run rosserial_ros2_bridge bridge_node \
  --port /dev/ttyUSB0 \
  --baud 57600 \
  --ros-args \
  -p period_ms:=250 \
  -p gain:=1.5 \
  -p label:=nano_diag \
  -p enabled:=true

```


Читать диагностику в Python:


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="rosserial_example")

def on_diag(msg):
    print(f"Диагностика: {msg.data}")

drone.topic.subscribe(String, '/diag_status', on_diag)
drone.topic.spin()

drone.close()

```


Логи в топике rosout:


```
ros2 topic echo /rosout
ros2 topic echo /rosserial_diagnostics

```


В скетче Arduino получает текущее время ROS 2:


```
#include <ros2.h>
ros::Node node;

void loop() {
    node.spin_some();
    if (!node.is_connected()) return;

    // Получаем синхронизированное время (как в ROS 2)
    ros::Time stamp = node.now();
    // stamp.sec — секунды, stamp.nsec — наносекунды
}

```


---


## Сценарий 6: Управление сервоприводом


**Что делает программа:** отправляет угол из Python, Arduino поворачивает сервопривод.


Скетч: `File → Examples → rosserial_ros2 → rosserial_servo_actuator`


Сервопривод подключается к пину D9:

|  Сервопривод |  Arduino |
|  сигнал (жёлтый) |  D9 |
|  питание (красный) |  внешний 5В |
|  земля (коричневый) |  GND Arduino = GND внешнего питания |


После прошивки и запуска bridge:


```
import sverk_interfaces
from std_msgs.msg import String, UInt16

drone = sverk_interfaces.init(Nodename="rosserial_example")

pub = drone.topic.create_publisher(UInt16, '/servo_angle')

# Повернуть на 90°
angle = UInt16()
angle.data = 90
pub.publish(angle)

# Проверить статус
msg = drone.topic.wait_for_message(String, '/servo_status', timeout=3.0)
if msg:
    print(f"Статус сервопривода: {msg.data}")

drone.close()

```


Диагностика через CLI:


```
ros2 topic list | grep servo
ros2 topic echo /servo_status --once

```


---


## Сценарий 7: Пользовательское сообщение


**Что делает программа:** создаёт своё сообщение ROS 2 и использует его в Arduino.


Пример находится в `<rosserial_ros2>/custom_message_tutorial`.


Добавить в workspace:


```
cp -r <rosserial_ros2>/rosserial_ros2_bridge ~/ros_ws/src/
cp -r <rosserial_ros2>/custom_message_tutorial/rosserial_test_msgs ~/ros_ws/src/

cd ~/ros_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select rosserial_ros2_bridge rosserial_test_msgs
source install/setup.bash

```


Посмотреть структуру пользовательского сообщения:


```
ros2 interface show rosserial_test_msgs/msg/McuStatus

```


Сгенерировать заголовки для Arduino IDE:


```
ros2 run rosserial_ros2_bridge generate_ros_lib \
  --packages rosserial_test_msgs \
  --output <rosserial_ros2>/libraries/ros_lib \
  --schema-output <rosserial_ros2>/rosserial_ros2_bridge/rosserial_ros2_bridge/generated_interfaces.json \
  --overwrite-generated

```


Прошить скетч `rosserial_custom_mcu_status` и запустить bridge. Читать топик:


```
import sverk_interfaces
from rosserial_test_msgs.msg import McuStatus

drone = sverk_interfaces.init(Nodename="rosserial_example")

def on_mcu_status(msg):
    print(f"MCU статус: {msg}")

drone.topic.subscribe(McuStatus, '/mcu_status', on_mcu_status)
drone.topic.spin()

drone.close()

```


Диагностика:


```
ros2 topic echo /mcu_status

```


---


## Сценарий 8: Подбор размеров буферов


Если скетч большой или используете сложные сообщения — проверьте, что буферы достаточны:


```
# Сколько байт займёт строка из 32 символов?
ros2 run rosserial_ros2_bridge buffer_size std_msgs/String data:=32

# Сколько займёт Twist (команды скорости)?
ros2 run rosserial_ros2_bridge buffer_size geometry_msgs/Twist

# Лазерный скан на 30 точек с подробностями
ros2 run rosserial_ros2_bridge buffer_size sensor_msgs/LaserScan \
  header.frame_id:=8 ranges:=30 intensities:=0 --buffer 280 --details

```


Если рекомендуемый размер больше буфера в скетче — увеличьте его:


```
// Увеличиваем выходной буфер до 512 байт
ros::NodeHandle_<SerialHardware, 2, 2, 128, 512> nh;

```


---


## Частые проблемы


### COM-порт занят


Закрой Serial Monitor в Arduino IDE, остановь другие процессы, которые держат порт.


### Bridge подключился, но топики не появились

- Убедитесь, что Arduino прошита нужным скетчем
- Проверьте, что скорость (baud rate) совпадает
- Убедитесь в правильном пути к порту (`/dev/ttyUSB0`, `/dev/ttyACM0` и т.д.)

### TCP relay подключается, но данных нет


Проверьте IP-адрес машины с relay (обычно адрес из локальной сети, например `192.168.1.x`).


### На Arduino Nano мало памяти


Уменьшите буферы, строки и массивы. Следите за предупреждениями компилятора о RAM.


---


## См. также


Низкоуровневые примеры с `ros2 service call`, `ros2 topic pub` и прямым rclpy: → [knowledge_base/arduino-raw.md](/learn/obrik-ros-2/arduino-raw)
