# MAVROS

> Раздел: Обрик ROS 1 (Clover) · slug: `mavros`
> Источник: https://edu.sverk.tech/learn/clover-2/mavros

---

# MAVROS


Основная документация: [http://wiki.ros.org/mavros](http://wiki.ros.org/mavros)


MAVROS (MAVLink + ROS) — это пакет для ROS, предоставляющий возможность управлять беспилотниками по протоколу [MAVLink](/learn/clover-2/mavlink). MAVROS поддерживает полётные стеки PX4 и APM. Связь организовывается по UART, USB, TCP или UDP.


MAVROS подписывается на определенные ROS-топики в ожидании команд, публикует в другие топики телеметрию, и предоставляет сервисы.


Нода MAVROS автоматически запускается в launch-файле дрона. Для [настройки типа подключения](connection.md) см. аргумент `fcu_conn`.


>

**Hint** Упрощенное взаимодействие с коптером возможно с использованием пакета [`simple_offboard`](/learn/clover-2/commands-offboard-flight).


>

**Note** В пакете `sverk` некоторые плагины MAVROS отключены (в целях сохранения ресурсов). Подробнее см. параметр `plugin_blacklist` в файле `/home/pi/catkin_ws/src/sverk/sverk/launch/mavros.launch`.


## Основные сервисы


`/mavros/set_mode` — установить [полётный режим](/learn/clover-2/offboard-flight) контроллера. Обычно устанавливается режим OFFBOARD (для управления с Raspberry Pi).


`/mavros/cmd/arming` — включить или выключить моторы беспилотника (изменить armed-статус).


## Основные публикуемые топики


`/mavros/state` — статус подключения к полётному контроллеру. Режим полётного контроллера.


`/mavros/local_position/pose` — локальная позиция коптера в системе координат ENU и его ориентация.


`/mavros/local_position/velocity` — текущая скорость в локальных координатах. Угловые скорости.


`/mavros/global_position/global` — текущая глобальная позиция (широта, долгота, высота).


`/mavros/global_position/local` — глобальная позиция в системе координат [UTM](https://ru.wikipedia.org/wiki/%D0%A1%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0_%D0%BA%D0%BE%D0%BE%D1%80%D0%B4%D0%B8%D0%BD%D0%B0%D1%82_UTM).


`/mavros/global_position/rel_alt` — относительная высота (относительно высоты включения моторов).


Просмотр сообщений, публикуемых в топики возможен с помощью утилиты `rostopic`, например `rostopic echo /mavros/state`. Подробнее см. [работа с ROS](/learn/clover-2/ros).


## Основные топики для публикации


`/mavros/setpoint_position/local` — установить целевую позицию и рысканье (yaw) беспилотника (в системе координат ENU).


`/mavros/setpoint_position/global` – установить целевую позицию в глобальных координатах (ширина, долгота и высота) и рысканье беспилотника.


`/mavros/setpoint_velocity/cmd_vel` — установить целевую линейную скорость беспилотника.


`/mavros/setpoint_attitude/attitude` и `/mavros/setpoint_attitude/att_throttle` — установить целевую ориентацию (Attitude) и уровень газа.


`/mavros/setpoint_attitude/cmd_vel` и `/mavros/setpoint_attitude/att_throttle` — установить целевые угловые скорости и уровень газа.


### Топики для посылки raw-пакетов


`/mavros/setpoint_raw/local` — отправка пакета [SET_POSITION_TARGET_LOCAL_NED](https://mavlink.io/en/messages/common.html#SET_POSITION_TARGET_LOCAL_NED). Позволяет установить целевую позицию /целевую скорость и целевое рысканье/угловую скорость по рысканью. Выбор устанавливаемых величин осуществляется с помощью поля `type_mask`.


`/mavros/setpoint_raw/attitude` — отправка пакета [SET_ATTITUDE_TARGET](https://mavlink.io/en/messages/common.html#SET_ATTITUDE_TARGET). Позволяет установить целевую ориентацию / угловые скорости и уровень газа. Выбор устанавливаемых величин осуществляется с помощью поля `type_mask`


`/mavros/setpoint_raw/global` — отправка пакета [SET_POSITION_TARGET_GLOBAL_INT](https://mavlink.io/en/messages/common.html#SET_POSITION_TARGET_GLOBAL_INT). Позволяет установить целевую позицию в глобальных координатах (ширина, долгота, высота), а также скорости полёта.
