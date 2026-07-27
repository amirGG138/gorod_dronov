# Основы ROS 2

> Раздел: Обрик ROS 2 · slug: `ros2-basics`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/ros2-basics

---

# Основы ROS 2


ROS 2 (Robot Operating System 2) — это не операционная система в привычном смысле, а набор инструментов и соглашений для написания программ, которые управляют роботами. На Обрике именно ROS 2 связывает вашу Python-программу с полётным контроллером PX4.


**Официальная документация**: [docs.ros.org/en/humble](https://docs.ros.org/en/humble/)


---


## Ноды — программы, которые разговаривают друг с другом


**Нода** — это отдельная запущенная программа в ROS 2. Каждая нода решает свою задачу: нода камеры снимает картинку, нода навигации считает маршрут, нода `offboard_control` отправляет команды в PX4. Ноды работают независимо, но обмениваются данными.


Документация по нодам: [ROS 2 Nodes](https://docs.ros.org/en/humble/Concepts/Basic/About-Nodes.html)


Все программы для Обрика — это ROS 2 ноды.


### Схема: как ноды общаются на Обрике


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fros2-pipeline.svg&sig=fbed57718b6c543f7d0d3f42b1906727af86a91c642344dae416601efe8d77ff)



### Пример: минимальная нода на Python


**Что делает программа:** создаёт ноду, которая запускается и ждёт команд.


```
import rclpy               # главная библиотека ROS 2 для Python
from rclpy.node import Node  # класс Node — основа любой ноды

rclpy.init()               # запускаем ROS 2 (всегда первым делом)
node = Node('my_node')     # создаём ноду с именем 'my_node'
rclpy.spin(node)           # нода работает, пока не нажмёте Ctrl+C
rclpy.shutdown()           # корректно выключаем ROS 2

```


После запуска нода появляется в системе. Проверьте командой `ros2 node list` — вы увидите `/my_node` в списке.


>

**Примечание** Эти команды выполняются **внутри контейнера** `sverk_ros2`.


### Ноды в работающей системе Обрика

|  Нода |  Пакет |  Что делает |
|  `camera_node` |  `camera_ros` |  Драйвер камеры — публикует `/camera_1/image_raw` и `/camera_1/camera_info` |
|  `aruco_map_node` |  `aruco_map` |  Читает файл карты маркеров, публикует `/map_markers` |
|  `aruco_detect_node` |  `aruco_det_loc` |  Находит ArUco-маркеры на кадре, публикует `/markers` |
|  `aruco_loc_node` |  `aruco_det_loc` |  Вычисляет позицию дрона по маркерам, публикует `/aruco_map/pose_cov` |
|  `px4_local_pose_publisher` |  `px4_local_pose_publisher` |  Передаёт позицию от ArUco в PX4 EKF2 через uXRCE-DDS |
|  `offboard_control` |  `offboard_control` |  Принимает команды (`/navigate`, `/land` и др.) и управляет PX4 |
|  `web_video` |  `web_video_server` |  HTTP-стриминг ROS-топиков с изображением |
|  `rosboard` |  `rosboard` |  Веб-визуализация данных из любых ROS-топиков |
|  `ros_services_bridge` |  `ros_services_bridge` |  HTTP API для вызова ROS-сервисов из веб-интерфейса |
|  `led_control_node` |  `led_control` |  Управление светодиодной лентой |


Помимо нод, система запускает два процесса: `MicroXRCEAgent` (мост PX4 ↔ ROS 2 через UART) и `mavlink-routerd` (ретрансляция MAVLink на UDP 14550 для QGC).


---


## Топики


**Топик** — именованный канал передачи данных: одни ноды публикуют в него сообщения, другие подписываются и читают. Камера публикует кадры в топик `/camera_1/image_raw`, программа подписывается и получает их. Топик работает в одну сторону и постоянно — никто не ждёт ответа. Этим он отличается от сервиса.


Документация: [ROS 2 Topics](https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics.html)


Популярные типы сообщений:

|  Тип |  Описание |
|  `std_msgs/msg/Int64` |  Целое число |
|  `std_msgs/msg/String` |  Текстовая строка |
|  `geometry_msgs/msg/PoseStamped` |  Позиция + ориентация + система координат |
|  `geometry_msgs/msg/TwistStamped` |  Скорость + система координат |
|  `sensor_msgs/msg/Image` |  Кадр с камеры |


### Публикация в топик (Python)


**Что делает программа:** нода отправляет текстовое сообщение в топик `/foo`.


```
from std_msgs.msg import String  # тип сообщения — строка

# создаём publisher: хотим публиковать String в топик '/foo'
# число 10 — размер очереди (сколько сообщений хранить, если получатель не успевает)
pub = node.create_publisher(String, '/foo', 10)

msg = String()            # создаём пустое сообщение
msg.data = 'Привет, ROS!' # заполняем поле data
pub.publish(msg)          # отправляем в топик

```


### Подписка на топик (Python)


**Что делает программа:** нода принимает каждое новое сообщение из `/foo`.


```
def callback(msg):
    # эта функция вызывается каждый раз, когда приходит новое сообщение
    print('Получено:', msg.data)

# подписываемся: слушаем String из '/foo', вызываем callback при каждом сообщении
sub = node.create_subscription(String, '/foo', callback, 10)

```


### Работа с топиками из терминала


```
# смотреть что публикует топик /fmu/out/vehicle_status (статус PX4)
ros2 topic echo /fmu/out/vehicle_status

# с какой частотой приходят сообщения (в Гц)
ros2 topic hz /fmu/out/vehicle_status

# краткая информация о топике
ros2 topic info /fmu/out/vehicle_status

# список всех активных топиков
ros2 topic list

# список всех запущенных нод
ros2 node list

# информация о ноде (топики, сервисы, параметры)
ros2 node info /offboard_control

```


>

**Примечание** Эти команды выполняются **внутри контейнера** `sverk_ros2`.


---


## Сервисы — звонок с ответом


**Сервис** — обмен «запрос-ответ»: нода отправляет запрос («взлети») и ждёт ответа («выполнено» или «ошибка, моторы не запущены»). В отличие от топика, сервис двусторонний и разовый. Через сервисы работает управление Обриком: `/navigate`, `/land`, `/get_telemetry`.


Документация: [ROS 2 Services](https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Services.html)


### Вызов сервиса из Python


```
import sverk_interfaces
drone = sverk_interfaces.init(Nodename="ros2_example")
# получить телеметрию в системе координат 'map'
telem = drone.control.get_telemetry(frame_id="map")
print(f"Позиция: x={telem.x:.2f}, y={telem.y:.2f}, z={telem.z:.2f}")
drone.close()

```


Подробнее про все сервисы Обрика: [Команды управления полётом](/learn/obrik-ros-2/offboard-commands)


### Вызов сервиса из терминала


```
# взлёт на 1.5 м (относительно корпуса)
ros2 service call /navigate offboard_interfaces/srv/Navigate "{x: 0.0, y: 0.0, z: 1.5, yaw: 0.0, speed: 1.0, frame_id: 'body', auto_arm: true}"

# посадка
ros2 service call /land std_srvs/srv/Trigger "{}"

# получить телеметрию
ros2 service call /get_telemetry offboard_interfaces/srv/GetTelemetry "{frame_id: 'map'}"

# список всех активных сервисов
ros2 service list

# узнать тип сервиса
ros2 service type /navigate

# посмотреть структуру типа
ros2 interface show offboard_interfaces/srv/Navigate

```


---


## Библиотека sverk_interfaces


`sverk_interfaces` — Python-обёртка над ROS 2 сервисами Обрика. Скрывает шаблонный ROS 2 код: создание ноды, клиентов сервисов, ожидание ответа.


```
import sverk_interfaces
drone = sverk_interfaces.init(Nodename="my_program")
# ... код программы ...
drone.close()

```

|  Метод |  Описание |
|  `drone.control.navigate(x, y, z, yaw, speed, frame_id, auto_arm)` |  Плавный полёт к точке |
|  `drone.control.land()` |  Посадка |
|  `drone.control.get_telemetry(frame_id)` |  Телеметрия: позиция, режим, аккумулятор |
|  `drone.control.set_altitude(z, frame_id)` |  Сменить высоту без остановки полёта |
|  `drone.control.set_yaw(yaw, frame_id)` |  Сменить курс без остановки |
|  `drone.control.set_yaw_rate(yaw_rate)` |  Вращение с угловой скоростью (рад/с) |
|  `drone.control.set_position(x, y, z, yaw, frame_id, auto_arm)` |  Удержание/полёт к точке |
|  `drone.control.set_velocity(vx, vy, vz, yaw, frame_id, auto_arm)` |  Управление по скорости |
|  `drone.control.set_attitude(roll, pitch, yaw, thrust, frame_id, auto_arm)` |  Управление углами (STABILIZED) |
|  `drone.control.set_rates(roll_rate, pitch_rate, yaw_rate, thrust, auto_arm)` |  Управление угловыми скоростями (ACRO) |
|  `drone.control.flip(axis, vz, climb_duration, rate, target_angle, thrust, auto_arm)` |  Кувырок |


Подробные описания параметров, примеры и вызовы из терминала → [Нода offboard_control](/learn/obrik-ros-2/offboard-node).


---


## Установка ROS 2


ROS 2 уже установлен на [образе для бортового компьютера Обрика](/learn/obrik-ros-2/os-image-flash). Если вы работаете на своём компьютере с Ubuntu 22.04:


```
sudo apt install ros-humble-desktop
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc

```


Хотите попробовать прямо сейчас без дрона? Читайте про [симулятор](/learn/obrik-ros-2/simulation).


---


## Имена топиков и сервисов


Документация: [ROS 2 Names](https://docs.ros.org/en/humble/Concepts/Basic/About-Namespaces.html)

|  Форма |  Пример |  Когда использовать |
|  Глобальное |  `/foo` |  Всегда работает, независимо от места запуска |
|  Относительное |  `foo` |  Относительно namespace текущей ноды |
|  Приватное |  `~/foo` |  Принадлежит только этой ноде |


Обычно в программах для Обрика используются глобальные имена: `/navigate`, `/land`, `/get_telemetry`.


---


## Несколько дронов в одной сети


Документация: [ROS 2 Multi-machine](https://docs.ros.org/en/humble/Tutorials/Advanced/Multi-machine.html)


Если запустить два дрона в одной Wi-Fi сети без настройки, они начнут «мешать» друг другу — сервисы и топики перемешаются. Чтобы этого не происходило, каждому дрону назначают свой домен (число от 0 до 232):


```
export ROS_DOMAIN_ID=1  # команды для дрона 1
export ROS_DOMAIN_ID=2  # команды для дрона 2

```


Эта переменная указывается один раз перед запуском программы. Дроны с разными `ROS_DOMAIN_ID` не видят друг друга.


---


## Схема: полный путь команды на Обрике


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Foffboard-pipeline.svg&sig=d1dacc1ea26f832f8ca14b163d95c791fc9987fbc830fd3afed2baca6bc10dc3)
