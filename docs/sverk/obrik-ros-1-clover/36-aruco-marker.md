# Распознавание ArUco-маркеров

> Раздел: Обрик ROS 1 (Clover) · slug: `aruco-marker`
> Источник: https://edu.sverk.tech/learn/clover-2/aruco-marker

---

# Распознавание ArUco-маркеров


>

**Info** Для распознавания маркеров модуль камеры должен быть корректно подключен и [сконфигурирован](/learn/clover-2/camera-setup).


Модуль `aruco_detect` распознает ArUco-маркеры и публикует их позиции в ROS-топики и в [TF](/learn/clover-2/frames).


Эта функция полезна для применения совместно с какой-либо системой позиционирования для дрона, такой как [GPS](gps.md), [Optical Flow](/learn/clover-2/optical-flow), PX4Flow, визуальная одометрия, ультразвуковое ([Marvelmind](https://marvelmind.com)) или UWB-позиционирование ([Pozyx](https://www.pozyx.io)).


Также возможно применение совместно с [навигацией по карте маркеров](/learn/clover-2/aruco-map).


## Настройка


Аргумент `aruco` в файле `~/catkin_ws/src/sverk/sverk/launch/sverk.launch` должен быть в значении `true`:


```
<arg name="aruco" default="true"/>

```


Для включения распознавания маркеров аргумент `aruco_detect` в файле `~/catkin_ws/src/sverk/sverk/launch/aruco.launch` должен быть в значении `true`:


```
<arg name="aruco_detect" default="true"/>

```


Для правильной работы в этом же файле также должны быть выставлены аргументы:


```
<arg name="placement" default="floor"/>
<arg name="length" default="0.33"/>

```


Значение аргумента `placement` следует выставлять следующим образом:

- если *все* маркеры наклеены на полу (земле), выставить значение `floor`;
- если *все* маркеры наклеены на потолке, выставить значение `ceiling`;
- в противном случае удалить строку с параметром.

Если некоторые маркеры имеют размер, отличный значения `length`, их размер может быть переопределен с помощью параметра `length_override` ноды `aruco_detect`:


```
<param name="length_override/3" value="0.1"/>
<param name="length_override/17" value="0.25"/>

```


## Система координат


С маркером связана следующая система координат:

- ось **<font color=red>x</font>** указывает на правую сторону маркера;
- ось **<font color=green>y</font>** указывает кверху маркера;
- ось **<font color=blue>z</font>** указывает от плоскости маркера.

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Faruco-axis.png&sig=719215af31f19489b7118015563b1d9e6d648a8540207b2b52d143f8b7d67314)



## Работа с распознанными маркерами


Наглядно распознанные маркеры можно видеть в топике `aruco_detect/debug`. Просмотреть его можно с помощью [`rqt_image_view`](/learn/clover-2/rviz) или через [web_video_server](/learn/clover-2/web-video-server) по ссылке [http://192.168.11.1:8080/snapshot?topic=/aruco_pose/debug:](http://192.168.11.1:8080/snapshot?topic=/aruco_pose/debug:)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Faruco-detect-debug.png&sig=9c31b9a1fa8240408ce64d5ec2a06341fccd2f272c12f6ddf7a184a0013c9d0f)



Распознанные маркеры и их позиции публикуются в топик `aruco_detect/markers`. Чтение топика из Bash:


```
rostopic echo /aruco_detect/markers

```


## Навигация по маркерам


С использованием модуля [`simple_offboard`](/learn/clover-2/commands-offboard-flight) можно осуществлять навигацию по маркерам используя соответствующие TF-фреймы.


Полет в точку над маркером 5 на высоту 1 метр:


```
navigate(frame_id='aruco_5', x=0, y=0, z=1)

```


Полет в точку на метр левее маркера 7 на высоте 2 метра:


```
navigate(frame_id='aruco_7', x=-1, y=0, z=2)

```


Если необходимый маркер не появится в поле зрения в течение полусекунды, дрон продолжит выполнять предыдущую команду.


Подобные значения `frame_id` можно использовать и в других сервисах, например `get_telemetry`. Получение расположения дрона относительно маркера 3:


```
telem = get_telemetry(frame_id='aruco_3')

```


Если необходимый маркер не появится в поле зрения в течение полусекунды, в полях `telem.x`, `telem.y`, `telem.z`, `telem.yaw` будет значение `NaN`.


## Работа с результатом распознавания из Python


Чтение топика `aruco_detect/markers` из Python:


```
import rospy
from aruco_pose.msg import MarkerArray
rospy.init_node('my_node')

# ...

def markers_callback(msg):
    print('Detected markers:'):
    for marker in msg.markers:
        print('Marker: %s' % marker)

# Подписываемся. При получении сообщения в топик aruco_detect/markers будет вызвана функция markers_callback.
rospy.Subscriber('aruco_detect/markers', MarkerArray, markers_callback)

# ...

rospy.spin()

```


Сообщения будут содержать ID маркера, его угловые точки на изображении и его позицию (относительно камеры).


---


См. далее: [навигация по картам маркеров](/learn/clover-2/aruco-map).
