# Работа с лазерным дальномером

> Раздел: Обрик ROS 1 (Clover) · slug: `laser`
> Источник: https://edu.sverk.tech/learn/clover-2/laser

---

# Работа с лазерным дальномером


## Дальномер VL53L1X


Рекомендуемая для Обрика модель дальномера – STM VL53L1X. Это дальномер может измерять расстояния от 0 до 4 м, при этом обеспечивая высокую точность измерений.


На [образе для Raspberry Pi](/learn/clover-2/install-image) предустановлен соответствующий ROS-драйвер.


### Подключение к Raspberry Pi


>

**Hint** Перед включением дальномера необходимо снять с него защитную пленку.


Подключите дальномер по интерфейсу I²C к пинам 3V, GND, SCL и SDA:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Flaser.png&sig=a14904ebae1a6a0fe6a2c73ff44f4e1d32c3f046a14620e4ac7d5e956bd32cac)



Если обозначенный пин GND занят, можно использовать другой свободный, используя [распиновку](https://pinout.xyz).


>

**Hint** По интерфейсу I²C возможно подключать несколько периферийных устройств одновременно. Используйте для этого параллельное подключение.


### Включение


[Подключитесь по SSH](/learn/clover-2/ssh) и отредактируйте файл `~/catkin_ws/src/sverk/sverk/launch/sverk.launch` так, чтобы драйвер VL53L1X был включен:


```
<arg name="rangefinder_vl53l1x" default="true"/>

```


По умолчания драйвер дальномера передает данные в Pixhawk (через топик `/rangefinder/range`). Для просмотра данных из топика используйте команду:


```
rostopic echo /rangefinder/range

```


### Настройки PX4


>

**Hint** Для корректной работы лазерного дальномера с полётным контроллером рекомендуется использование специальной прошивки PX4 для Обрика.


Для использования данных с дальномера в [PX4 должен быть сконфигурирован](parameters.md).


При использовании EKF2 (`SYS_MC_EST_GROUP` = `ekf2`):

- `EKF2_HGT_MODE` = `2` (Range sensor) – при полёте над горизонтальным полом;
- `EKF2_RNG_AID` = `1` (Range aid enabled) – в остальных случаях.

При использовании LPE (`SYS_MC_EST_GROUP` = `local_position_estimator, attitude_estimator_q`):

- В параметре `LPE_FUSION` включен флажок “pub agl as lpos down” – при полёте над горизонтальным полом.

### Получение данных из Python


Для получения данных из топика создайте подписчика:


```
import rospy
from sensor_msgs.msg import Range

rospy.init_node('flight')

def range_callback(msg):
    # Обработка новых данных с дальномера
    print('Rangefinder distance:', msg.range)

rospy.Subscriber('rangefinder/range', Range, range_callback)

rospy.spin() # дальнейший код программы

```


Также существует возможность однократного получения данных с дальномера:


```
from sensor_msgs.msg import Range

# ...

dist = rospy.wait_for_message('rangefinder/range', Range).range

```


### Визуализация данных


Для построения графика по данным с дальномера может быть использован rqt_multiplot.


Для визуализации данных может быть использован rviz. Для этого необходимо добавить топик типа `sensor_msgs/Range` в визуализацию:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Frviz-range.png&sig=ad5ea09577ed4059e8f6b98c05c93cb4a4ba5b4f7974766b1026aaaddd2a4ab2)



См. [подробнее об rviz и rqt](/learn/clover-2/rviz).
