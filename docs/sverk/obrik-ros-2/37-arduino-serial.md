# Работа с Arduino через serial_bridge

> Раздел: Обрик ROS 2 · slug: `arduino-serial`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/arduino-serial

---

# Работа с Arduino через serial_bridge


>

**Примечание** На дроне два UART. Для подключения используйте `UART_B` — `UART_A` занят полётным контроллером PX4.


## Описание


**Arduino** — компактная плата-микроконтроллер. Она управляет моторами и светодиодами, читает датчики, но сама по себе не работает с ROS 2.


**serial_bridge** — пакет, который соединяет Arduino с Обриком через USB (или UART). Arduino и бортовой компьютер обмениваются командами в текстовом виде, а пакет превращает их в ROS 2 топики и сервисы.


Это простой и надёжный способ подключить любое Arduino-устройство к дрону.


---


## Применение на дроне


Через Arduino к дрону можно подключить:

- Датчики (температура, давление, влажность)
- Реле и электромагниты
- Сервоприводы (альтернативный способ)
- Кнопки и концевики
- Собственные исполнительные устройства

---


## Где находится пакет


```
~/sverk_ws/src/sverk_drone/peripheral/serial_bridge

```


---


## Схема работы


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fserial-bridge-flow.svg&sig=2c2b8c4e7507a278c36ef596e23257115e6d97c1bd33e77151c649f3a9b3af33)



---


## Проверка подключения Arduino


Подключите Arduino по USB и убедитесь, что система её видит:


```
ls /dev/ttyACM*    # Arduino обычно появляется здесь
ls /dev/ttyUSB*    # или здесь, если через USB-UART адаптер

```


>

**Примечание** Arduino подключают к свободному порту **UART_B** (или по USB). Имя UART_B зависит от платы: RPi CM5 — `/dev/ttyAMA10`, Orange Pi Zero 3W — `/dev/ttyS6`, Orange Pi 5 Pro — `/dev/ttyS1`. UART_A занят полётным контроллером — туда подключать нельзя. Полная таблица интерфейсов по платам → [Бортовые компьютеры](/learn/obrik-ros-2/boards-overview).


Запомните путь — например `/dev/ttyACM0` — он понадобится при запуске ноды.


---


## Пример: управление сервоприводом через Arduino


В пакете уже есть готовый пример — сервопривод подключён к пину D2 на Arduino.


### Файлы примера

|  Файл |  Назначение |
|  `serial_bridge/arduino_servo_node.py` |  ROS 2 нода |
|  `launch/arduino_servo.launch.py` |  launch-файл |
|  `config/arduino_servo.yaml` |  настройки |
|  `examples/serial_servo_bridge_d2/serial_servo_bridge_d2.ino` |  программа Arduino |


### Шаг 1: Залить программу на Arduino


**Что делает программа:** прошивает Arduino программой, которая принимает команды по USB.


Откройте файл `serial_servo_bridge_d2.ino` в Arduino IDE и загрузите его на плату.


Скетч ждёт байты:

- `0..180` — повернуть на этот угол
- `0xFD` (253) — в центр
- `0xFE` (254) — включить сервопривод
- `0xFF` (255) — выключить сервопривод

### Шаг 2: Запустить ноду на Обрике


```
# Запуск через launch-файл
ros2 launch serial_bridge arduino_servo.launch.py

# Или напрямую с указанием порта
ros2 run serial_bridge arduino_servo_node --ros-args -p port:=/dev/ttyACM0

```


### Шаг 3: Управление из Python


**Что делает программа:** публикует угол в топик, Arduino поворачивает сервопривод.


```
import sverk_interfaces
from std_msgs.msg import Float32

drone = sverk_interfaces.init(Nodename="serial_bridge_example")

# Создаём публикатор в топик управления сервоприводом
pub = drone.topic.create_publisher(Float32, '/arduino_servo_node/target_angle_deg')

# Поворот на 45°
msg = Float32()
msg.data = 45.0
pub.publish(msg)

# Поворот на 90°
msg.data = 90.0
pub.publish(msg)

drone.close()

```


---


## Arduino программа (C++) — шаблон


**Что делает программа:** Arduino читает команды из Serial и управляет устройством.


```
// Простой пример: Arduino читает текстовые команды и отвечает
// Команды: "ON\n" — включить, "OFF\n" — выключить, "STATUS\n" — спросить состояние

const int LED_PIN = 13;   // встроенный светодиод
bool ledState = false;

void setup() {
    Serial.begin(115200);          // скорость должна совпадать с настройками ноды
    pinMode(LED_PIN, OUTPUT);
    Serial.println("READY");       // сообщаем, что готовы к работе
}

void loop() {
    if (Serial.available() > 0) {
        String cmd = Serial.readStringUntil('\n');  // читаем строку до переноса
        cmd.trim();                                 // убираем пробелы

        if (cmd == "ON") {
            ledState = true;
            digitalWrite(LED_PIN, HIGH);
            Serial.println("OK LED_ON");            // ответ ноде
        }
        else if (cmd == "OFF") {
            ledState = false;
            digitalWrite(LED_PIN, LOW);
            Serial.println("OK LED_OFF");
        }
        else if (cmd == "STATUS") {
            // Отправляем текущее состояние
            Serial.println(ledState ? "STATE 1" : "STATE 0");
        }
    }
}

```


---


## Чтение данных от Arduino


Если Arduino публикует данные (например, показания датчика) в ROS 2 топик через serial_bridge, подписаться на них можно так:


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="arduino_sub_example")

def on_arduino_data(msg):
    print(f"Данные от Arduino: {msg.data}")

drone.topic.subscribe(String, '/arduino_data', on_arduino_data)
drone.topic.spin()

drone.close()

```


Для однократного чтения (например, проверить состояние):


```
import sverk_interfaces
from std_msgs.msg import String

drone = sverk_interfaces.init(Nodename="arduino_read_example")

msg = drone.topic.wait_for_message(String, '/arduino_data', timeout=5.0)
if msg:
    print(f"Состояние Arduino: {msg.data}")
else:
    print("Нет данных от Arduino")

drone.close()

```


---


## Как проверить

- Загрузите программу на Arduino
- Подключите Arduino к Обрику по USB
- Проверьте, что порт появился: `ls /dev/ttyACM*`
- Запустите ноду: `ros2 launch serial_bridge arduino_servo.launch.py`
- Выполните программу управления на Python — сервопривод должен повернуться

---


## Другой способ: rosserial_ros2


Если нужно, чтобы Arduino сам публиковал топики ROS 2 и был полноценным узлом — используйте rosserial:


[Обзор rosserial_ros2](/learn/obrik-ros-2/arduino-rosserial) [Практические примеры](/learn/obrik-ros-2/arduino-rosserial-tutorial)


---


## См. также


Низкоуровневые примеры с `ros2 service call`, `ros2 topic pub` и прямой работой с serial-портом: [knowledge_base/arduino-raw.md](/learn/obrik-ros-2/arduino-raw)
