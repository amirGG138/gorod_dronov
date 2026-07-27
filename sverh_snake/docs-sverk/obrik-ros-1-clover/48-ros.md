# ROS

> Раздел: Обрик ROS 1 (Clover) · slug: `ros`
> Источник: https://edu.sverk.tech/learn/clover-2/ros

---

# ROS


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fros.svg&sig=779617d6694b7e8aca06cccdc61e84f52379107a8357533ee34e01f2aa0eebc9)



Основная документация: [https://wiki.ros.org](https://wiki.ros.org).


**ROS** – это широко используемый фреймворк для создания сложных, распределенных робототехнических систем. На ROS основана [платформа автономного полёта дрона](/learn/clover-2/offboard-flight).


## Установка


ROS уже установлен на [образ для дрона](/learn/clover-2/install-image).


Для установки инструментов ROS на компьютере вы можете обратиться к [официальной документации](https://wiki.ros.org/noetic/Installation/Ubuntu) по установке. Для быстрого старта рекомендуется воспользоваться [образом виртуальной машины с ROS и симулятором дрона](/learn/clover-2/simulation-vm).


## Концепции


### Ноды


Основная статья: [https://wiki.ros.org/Nodes](https://wiki.ros.org/Nodes).


ROS-нода[^1] – это специальная программа (обычно написанная на Python или C++), которая взаимодействует с другими нодами посредством ROS-топиков и ROS-сервисов. Разделение сложных робототехнических систем на изолированные ноды дает определенные преимущества: понижается связанность кода, повышается переиспользуемость и надежность.


Очень многие робототехнические библиотеки и драйвера выполнены именно в виде ROS-нод.


Для того, чтобы превратить обычную программу в ROS-ноду, необходимо подключить к ней библиотеку `rospy` (Python) или `roscpp` (C++) и добавить инициализирующий код.


Пример ROS-ноды на языке Python:


```
import rospy

rospy.init_node('my_ros_node')  # имя ROS-ноды

rospy.spin()  # входим в бесконечный цикл...

```


>

**Info** Любая [программа для автономного полёта дрона](/learn/clover-2/offboard-flight) является ROS-нодой.


### Топики


Основная статья: [https://wiki.ros.org/Topics](https://wiki.ros.org/Topics).


Топик – это именованная шина данных, по которой ноды обмениваются сообщениями. Любая нода может *опубликовать* сообщение в произвольный топик, а также *подписаться* на произвольный топик.


Для каждого созданного топика должен быть задан тип сообщений, которые по нему передаются. ROS включает в себя большое количество стандартных типов сообщений, покрывающих различные аспекты робототехники, но при необходимости возможно создание собственных типов сообщений. Примеры стандартных типов сообщений:

|  Тип сообщения |  Описание |
|  [`std_msgs/Int64`](https://docs.ros.org/api/std_msgs/html/msg/Int64.html) |  Целое число. |
|  [`std_msgs/Float64`](https://docs.ros.org/api/std_msgs/html/msg/Float64.html) |  Число с плавающей точкой (дробное) двойной точности. |
|  [`std_msgs/String`](https://docs.ros.org/api/std_msgs/html/msg/String.html) |  Строка. |
|  [`geometry_msgs/PoseStamped`](https://docs.ros.org/api/geometry_msgs/html/msg/PoseStamped.html) |  Позиция и ориентация объекта с заданной [системой координат](/learn/clover-2/frames) и временной меткой (широко используется для передачи текущей позиции робота и его частей). |
|  [`geometry_msgs/TwistStamped`](https://docs.ros.org/api/geometry_msgs/html/msg/TwistStamped.html) |  Линейная и угловая скорость объекта с заданной системой координат и временной меткой. |
|  [`sensor_msgs/Image`](https://docs.ros.org/api/sensor_msgs/html/msg/Image.html) |  Изображение (см. [статью о работе с камерой](/learn/clover-2/camera)) |


>

**Info** Смотрите остальные стандартные типы сообщений в пакетах [`common_msgs`](http://wiki.ros.org/common_msgs), [`std_msgs`](https://wiki.ros.org/std_msgs), [`geometry_msgs`](https://wiki.ros.org/geometry_msgs), [`sensor_msgs`](https://wiki.ros.org/sensor_msgs) и других.


Пример публикации сообщения типа [`std_msgs/String`](https://docs.ros.org/api/std_msgs/html/msg/String.html) (строка) в топик `/foo` на языке Python:


```
import rospy
from std_msgs.msg import String

rospy.init_node('my_ros_node')

foo_pub = rospy.Publisher('/foo', String, queue_size=1)  # создаем Publisher

foo_pub.publish(data='Hello, world!')  # публикуем сообщение

```


Пример подписки на топик `/foo`:


```
import rospy
from std_msgs.msg import String

rospy.init_node('my_ros_node')

def foo_callback(msg):
    print(msg.data)

# Подписываемся. При получении сообщения в топик /foo будет вызвана функция foo_callback.
rospy.Subscriber('/foo', String, foo_callback)

rospy.spin()  # входим в бесконечный цикл, чтобы программа не завершила работу

```


Вы можете прочитать данные из топика однократно, используя функцию `wait_for_message`:


```
msg = rospy.wait_for_message('/foo', String, timeout=3)  # ждать сообщения в топике /foo в таймаутом 3 с

```


Также существует возможность работы с топиками с помощью утилиты `rostopic`. Например, с помощью следующей команды можно просматривать сообщения, публикуемые в топик `/mavros/state`:


```
rostopic echo /mavros/state

```


Команда `rostopic info` позволяет узнать тип сообщений в топике, команда `rostopic hz` — частоту публикуемых в топике сообщений.


Также данные в топиках можно визуализировать и в [графических инструментах ROS](/learn/clover-2/rviz).


### Сервисы


Основная статья: [https://wiki.ros.org/Services](https://wiki.ros.org/Services).


Сервис – это некоторый аналог функции, которая может быть вызвана из одной ноды, а обработана в другой. У сервиса есть имя, аналогичное имени топика, и 2 типа сообщений: тип запроса и тип ответа.


Таким образом, сервисы реализуют паттерн [*удаленного вызова процедур*](https://ru.wikipedia.org/wiki/%D0%A3%D0%B4%D0%B0%D0%BB%D1%91%D0%BD%D0%BD%D1%8B%D0%B9_%D0%B2%D1%8B%D0%B7%D0%BE%D0%B2_%D0%BF%D1%80%D0%BE%D1%86%D0%B5%D0%B4%D1%83%D1%80).


Пример вызова ROS-сервиса из языка Python:


```
import rospy
from sverk.srv import GetTelemetry

rospy.init_node('my_ros_node')

# Создаем обертку над сервисом get_telemetry пакета sverk с типом GetTelemetry:
get_telemetry = rospy.ServiceProxy('get_telemetry', srv.GetTelemetry)

# Вызываем сервис и получаем телеметрию квадрокоптера:
telemetry = get_telemetry()

```


С сервисами можно также работать при помощи утилиты `rosservice`. Так можно вызвать сервис `/get_telemetry` из командной строки:


```
rosservice call /get_telemetry "{frame_id: ''}"

```


Больше примеров использования сервисов для автономных полётов квадрокоптера можно посмотреть в [документации ноды commands_offboard_flight](/learn/clover-2/commands-offboard-flight).


### Имена


Основная статья: [https://wiki.ros.org/Names](https://wiki.ros.org/Names).


Любой топик, сервис или параметр идентифицируется с помощью уникального имени. ROS-имя представляет собой иерархическую структуру с символом `/` в качестве разделителя (сходно с именами в файловой системе).


Примеры ROS-имен:

- `/` (глобальное пространство имен)
- `/foo`
- `/stanford/robot/name`
- `/wg/node1`

Эти имена является глобальными (аналогично полному пути в файлу в файловой системе). На практике рекомендуется использование *приватных* или *относительных* имен.


#### Приватное имя


Каждая нода может использовать собственное приватное пространство имен (соответствующее имени ноды) для своих ресурсов. Например, нода `aruco_detect` может публиковать такие топики:

- `/aruco_detect/markers`
- `/aruco_detect/visualization`
- `/aruco_detect/debug`

Когда нода ссылается на свой приватный ресурс, вместо пространства имен (`/aruco_detect/`) используется символ `~`, например:

- `~markers`
- `~visualization`
- `~debug`

Таким образом, создание топика `foo` в приватном пространство имен из Python будет выглядеть так:


```
private_foo_pub = rospy.Publisher('~foo', String, queue_size=1)

```


#### Относительное имя


Несколько нод также могут объединяться в общее пространство имен (например, при одновременной работе нескольких роботов). Для того, чтобы ссылаться на топики с учетом общего пространства имен, в названии ресурса опускается начальный символ `/`.


Пример создание топика `foo` с учетом общего пространства имен:


```
relative_foo_pub = rospy.Publisher('foo', String, queue_size=1)

```


>

**Hint** В общем случае всегда рекомендуется использовать приватные или относительные имена ресурсов и никогда не использовать глобальные.


## Работа на нескольких машинах


Основная статья: [https://wiki.ros.org/ROS/Tutorials/MultipleMachines](https://wiki.ros.org/ROS/Tutorials/MultipleMachines).


Преимуществом использования ROS является возможность распределения нод на несколько машин в сети. Например, ноду, осуществляющую распознавание образом на изображении можно запустить на более мощном компьютере; ноду, управляющую коптером можно запустить непосредственно на Raspberry Pi, подключенном к полётному контроллеру и т. д.


## Дополнительные материалы

- Учебник по ROS от Voltbro - [http://docs.voltbro.ru/starting-ros/](http://docs.voltbro.ru/starting-ros/).
- Другие книги по ROS - [https://wiki.ros.org/Books](https://wiki.ros.org/Books).

[^1]: Также встречается перевод “узел”.
