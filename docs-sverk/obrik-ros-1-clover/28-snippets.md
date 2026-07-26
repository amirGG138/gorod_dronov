# Примеры кода

> Раздел: Обрик ROS 1 (Clover) · slug: `snippets`
> Источник: https://edu.sverk.tech/learn/clover-2/snippets

---

# Примеры кода


## Python


>

**Note** При использовании кириллических символов в кодировке UTF-8 необходимо добавить в начало программы указание кодировки:


```
# -*- coding: utf-8 -*-

```


### navigate_wait


<a name=“block-nav”></a>


<a name=“block-takeoff”></a>


Функция для полёта в точку и ожидание окончания полёта:


```
import math

def navigate_wait(x=0, y=0, z=0, yaw=float('nan'), speed=0.5, frame_id='', auto_arm=False, tolerance=0.2):
    navigate(x=x, y=y, z=z, yaw=yaw, speed=speed, frame_id=frame_id, auto_arm=auto_arm)

    while not rospy.is_shutdown():
        telem = get_telemetry(frame_id='navigate_target')
        if math.sqrt(telem.x ** 2 + telem.y ** 2 + telem.z ** 2) < tolerance:
            break
        rospy.sleep(0.2)

```


Для того, чтобы определить расстояние до целевой точки, функция использует фрейм [`navigate_target`](/learn/clover-2/frames#navigate_target).


Использование функции для полёта в точку x=3, y=2, z=1 [относительно карты маркеров](/learn/clover-2/aruco-map):


```
navigate_wait(x=3, y=2, z=1, frame_id='aruco_map')

```


Эту функцию можно использовать и для взлета:


```
navigate_wait(z=1, frame_id='body', auto_arm=True)

```


### land_wait


<a name=“block-land”></a>


Посадка и ожидание окончания посадки:


```
def land_wait():
    land()
    while get_telemetry().armed:
        rospy.sleep(0.2)

```


Использование:


```
land_wait()

```


### wait_arrival


Ожидание окончания прилета в [navigate](/learn/clover-2/commands-offboard-flight#navigate)-точку:


```
import math

def wait_arrival(tolerance=0.2):
    while not rospy.is_shutdown():
        telem = get_telemetry(frame_id='navigate_target')
        if math.sqrt(telem.x ** 2 + telem.y ** 2 + telem.z ** 2) < tolerance:
            break
        rospy.sleep(0.2)

```


### get_distance


Функция определения расстояния между двумя точками (**важно**: точки должны быть в одной [системе координат](/learn/clover-2/frames)):


```
import math

def get_distance(x1, y1, z1, x2, y2, z2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)

```


### get_distance_global


Функция для приблизительного определения расстояния (в метрах) между двумя глобальными координатами (широта/долгота):


```
import math

def get_distance_global(lat1, lon1, lat2, lon2):
    return math.hypot(lat1 - lat2, lon1 - lon2) * 1.113195e5

```


### disarm


Дизарм коптера (выключение винтов, **коптер упадет**):


```
# Объявление прокси:
from mavros_msgs.srv import CommandBool
arming = rospy.ServiceProxy('mavros/cmd/arming', CommandBool)

# ...

arming(False)  # дизарм

```


### transform


Трансформировать позицию (`PoseStamped`) из одной системы координат ([фрейма](/learn/clover-2/frames)) в другую, используя [tf2](http://wiki.ros.org/tf2):


```
import tf2_ros
import tf2_geometry_msgs
from geometry_msgs.msg import PoseStamped

tf_buffer = tf2_ros.Buffer()
tf_listener = tf2_ros.TransformListener(tf_buffer)

# ...

# Создаем объект PoseStamped (либо получаем из топика):
pose = PoseStamped()
pose.header.frame_id = 'map'  # фрейм, в котором задана позиция
pose.header.stamp = rospy.get_rostime()  # момент времени, для которого задана позиция (текущее время)
pose.pose.position.x = 1
pose.pose.position.y = 2
pose.pose.position.z = 3
pose.pose.orientation.w = 1

frame_id = 'base_link'  # целевой фрейм
transform_timeout = rospy.Duration(0.2)  # таймаут ожидания трансформации

# Преобразовываем позицию из старого фрейма в новый:
new_pose = tf_buffer.transform(pose, frame_id, transform_timeout)

```


### upside-down


Определение, перевернут ли коптер:


```
PI_2 = math.pi / 2
telem = get_telemetry()

flipped = abs(telem.roll) > PI_2 or abs(telem.pitch) > PI_2

```


### angle-hor


Расчет общего угла коптера к горизонту:


```
PI_2 = math.pi / 2
telem = get_telemetry()

flipped = not -PI_2 <= telem.roll <= PI_2 or not -PI_2 <= telem.pitch <= PI_2
angle_to_horizon = math.atan(math.hypot(math.tan(telem.pitch), math.tan(telem.roll)))
if flipped:
    angle_to_horizon = math.pi - angle_to_horizon

```


### circle


Полет по круговой траектории:


```
RADIUS = 0.6  # m
SPEED = 0.3  # rad / s

start = get_telemetry()
start_stamp = rospy.get_rostime()

r = rospy.Rate(10)

while not rospy.is_shutdown():
    angle = (rospy.get_rostime() - start_stamp).to_sec() * SPEED
    x = start.x + math.sin(angle) * RADIUS
    y = start.y + math.cos(angle) * RADIUS
    set_position(x=x, y=y, z=start.z)

    r.sleep()

```


### rate


Повторять действие с частотой 10 Гц:


```
r = rospy.Rate(10)
while not rospy.is_shutdown():
    # Do anything
    r.sleep()

```


### mavros-sub


Пример подписки на топики из MAVROS:


```
from geometry_msgs.msg import PoseStamped, TwistStamped
from sensor_msgs.msg import BatteryState
from mavros_msgs.msg import RCIn

def pose_update(pose):
    # Обработка новых данных о позиции коптера
    pass

rospy.Subscriber('mavros/local_position/pose', PoseStamped, pose_update)
rospy.Subscriber('mavros/local_position/velocity', TwistStamped, velocity_update)
rospy.Subscriber('mavros/battery', BatteryState, battery_update)
rospy.Subscriber('mavros/rc/in', RCIn, rc_callback)

rospy.spin()

```


Информацию по топикам MAVROS см. по [ссылке](/learn/clover-2/mavros).


### mavlink


Пример отправки произвольного [MAVLink-сообщения](/learn/clover-2/mavlink) коптеру:


```
from mavros_msgs.msg import Mavlink
from mavros import mavlink
from pymavlink import mavutil

mavlink_pub = rospy.Publisher('mavlink/to', Mavlink, queue_size=1)

# Отправка сообщения HEARTBEAT:

msg = mavutil.mavlink.MAVLink_heartbeat_message(mavutil.mavlink.MAV_TYPE_GCS, 0, 0, 0, 0, 0)
msg.pack(mavutil.mavlink.MAVLink('', 2, 1))
ros_msg = mavlink.convert_to_rosmsg(msg)

mavlink_pub.publish(ros_msg)

```


### mavlink-receive


Подписка на все MAVLink-сообщения от полётного контроллера и их декодирование:


```
from mavros_msgs.msg import Mavlink
from mavros import mavlink
from pymavlink import mavutil

link = mavutil.mavlink.MAVLink('', 255, 1)

def mavlink_cb(msg):
    mav_msg = link.decode(mavlink.convert_to_bytes(msg))
    print('msgid =', msg.msgid, mav_msg) # print message id and parsed message

mavlink_sub = rospy.Subscriber('mavlink/from', Mavlink, mavlink_cb)

rospy.spin()

```


### rc-sub


Реакция на переключение режима на пульте радиоуправления (может быть использовано для запуска автономного полёта, см. [пример](https://gist.github.com/okalachev/b709f04522d2f9af97e835baedeb806b)):


```
from mavros_msgs.msg import RCIn

# Вызывается при получении новых данных с пульта
def rc_callback(data):
    # Произвольная реакция на переключение тумблера на пульте
    if data.channels[5] < 1100:
        # ...
        pass
    elif data.channels[5] > 1900:
        # ...
        pass
    else:
        # ...
        pass

# Создаем подписчик на топик с данными с пульта
rospy.Subscriber('mavros/rc/in', RCIn, rc_callback)

rospy.spin()

```


### set_mode


Сменить [режим полёта](/learn/clover-2/offboard-flight) на произвольный:


```
from mavros_msgs.srv import SetMode

set_mode = rospy.ServiceProxy('mavros/set_mode', SetMode)

# ...

set_mode(custom_mode='STABILIZED')

```


### flip


Флип:


```
import math

PI_2 = math.pi / 2

def flip():
    start = get_telemetry()  # memorize starting position

    set_rates(thrust=1)  # bump up
    rospy.sleep(0.2)

    set_rates(pitch_rate=30, thrust=0.2)  # pitch flip
    # set_rates(roll_rate=30, thrust=0.2)  # roll flip

    while True:
        telem = get_telemetry()
        flipped = abs(telem.roll) > PI_2 or abs(telem.pitch) > PI_2
        if flipped:
            break

    rospy.loginfo('finish flip')
    set_position(x=start.x, y=start.y, z=start.z, yaw=start.yaw)  # finish flip

print(navigate(z=2, speed=1, frame_id='body', auto_arm=True))  # take off
rospy.sleep(10)

rospy.loginfo('flip')
flip()

```


Необходимо использование специальной прошивки PX4 для Обрика. Перед выполнением флипа необходимо принять все меры безопасности.


### calibrate-gyro


Произвести калибровку гироскопа:


```
from pymavlink import mavutil
from mavros_msgs.srv import CommandLong
from mavros_msgs.msg import State

send_command = rospy.ServiceProxy('mavros/cmd/command', CommandLong)

def calibrate_gyro():
    rospy.loginfo('Calibrate gyro')
    if not send_command(command=mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION, param1=1).success:
        return False

    calibrating = False
    while not rospy.is_shutdown():
        state = rospy.wait_for_message('mavros/state', State)
        if state.system_status == mavutil.mavlink.MAV_STATE_CALIBRATING or state.system_status == mavutil.mavlink.MAV_STATE_UNINIT:
            calibrating = True
        elif calibrating and state.system_status == mavutil.mavlink.MAV_STATE_STANDBY:
            rospy.loginfo('Calibrating finished')
            return True

calibrate_gyro()

```


>

**Note** В процессе калибровки гироскопов дрон нельзя двигать.


### aruco-detect-enabled


Динамически включать и отключать [распознавание ArUco-маркеров](/learn/clover-2/aruco-marker) (например, для экономии ресурсов процессора):


```
import rospy
import dynamic_reconfigure.client

rospy.init_node('flight')
aruco_client = dynamic_reconfigure.client.Client('aruco_detect')

# Выключить распознавание маркеров
aruco_client.update_configuration({'enabled': False})

rospy.sleep(5)

# Включить распознавание маркеров
aruco_client.update_configuration({'enabled': True})

```


### optical-flow-enabled


Динамически включать и отключать [Optical Flow](/learn/clover-2/optical-flow):


```
import rospy
import dynamic_reconfigure.client

rospy.init_node('flight')
flow_client = dynamic_reconfigure.client.Client('optical_flow')

# Выключить Optical Flow
flow_client.update_configuration({'enabled': False})

rospy.sleep(5)

# Включить Optical Flow
flow_client.update_configuration({'enabled': True})

```


### aruco-map-dynamic


Динамически изменить используемый файл с [картой ArUco-маркеров](/learn/clover-2/aruco-map):


```
import rospy
import dynamic_reconfigure.client

rospy.init_node('flight')
map_client = dynamic_reconfigure.client.Client('aruco_map')

map_client.update_configuration({'map': '/home/pi/catkin_ws/src/sverk/aruco_pose/map/office.txt'})

```


### wait-global-position


Ожидать появления глобальной позиции (окончания инициализации [GPS-приемника](gps.md)):


```
import math

while not rospy.is_shutdown():
    if math.isfinite(get_telemetry().lat):
        break
    rospy.sleep(0.2)

```


### get-param


Считать параметр полётного контроллера:


```
from mavros_msgs.srv import ParamGet
from mavros_msgs.msg import ParamValue

param_get = rospy.ServiceProxy('mavros/param/get', ParamGet)

# Считать параметр типа INT
value = param_get(param_id='COM_FLTMODE1').value.integer

# Считать параметр типа FLOAT
value = param_get(param_id='MPC_Z_P').value.float

```


### set-param


Изменить параметр полётного контроллера:


```
from mavros_msgs.srv import ParamSet
from mavros_msgs.msg import ParamValue

param_set = rospy.ServiceProxy('mavros/param/set', ParamSet)

# Изменить параметр типа INT:
param_set(param_id='COM_FLTMODE1', value=ParamValue(integer=8))

# Изменить параметр типа FLOAT:
param_set(param_id='MPC_Z_P', value=ParamValue(real=1.5))

```


### is-simulation


Проверить, что код запущен в [симуляции Gazebo](simulation.md):


```
is_simulation = rospy.get_param('/use_sim_time', False)

```


### simulator-interaction


Переместить физический объект (линк) в Gazebo (а также поменять его скорости) можно при помощи сервиса `gazebo/set_link_state` (тип [`SetLinkState`](http://docs.ros.org/en/api/gazebo_msgs/html/srv/SetLinkState.html)). Например, если добавить в мир объект куб (линк `unit_box::link`), то так можно переместить его в точку (1, 2, 3):


```
import rospy
from geometry_msgs.msg import Point, Pose, Quaternion
from gazebo_msgs.srv import SetLinkState
from gazebo_msgs.msg import LinkState

rospy.init_node('flight')

set_link_state = rospy.ServiceProxy('gazebo/set_link_state', SetLinkState)

# Переместить линк в Gazebo
set_link_state(LinkState(link_name='unit_box::link', pose=Pose(position=Point(1, 2, 3), orientation=Quaternion(0, 0, 0, 1))))

```


>

**Info** Простую анимацию объектов в Gazebo можно реализовать [с помощью акторов](http://classic.gazebosim.org/tutorials?tut=actor&cat=build_robot).
