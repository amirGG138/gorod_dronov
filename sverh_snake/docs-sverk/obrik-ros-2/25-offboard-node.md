# Нода offboard_control

> Раздел: Обрик ROS 2 · slug: `offboard-node`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/offboard-node

---

# Нода offboard_control


Нода `offboard_control` — это сердце управляющей программы Обрика. Она принимает команды через ROS 2 сервисы (`/navigate`, `/land`, `/get_telemetry` и другие), пересчитывает координаты и отправляет управляющие сигналы напрямую в PX4 через протокол uXRCE-DDS.


Вам не нужно трогать эту ноду напрямую — библиотека `sverk_interfaces` делает это за вас. Но понимать, как она устроена, полезно.


---


## Схема: от кода до моторов


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Foffboard-pipeline.svg&sig=d1dacc1ea26f832f8ca14b163d95c791fc9987fbc830fd3afed2baca6bc10dc3)



---


## Требования

- ROS 2 Humble (или совместимый)
- Пакеты: `px4_msgs`, `px4_ros_com`, `offboard_interfaces`, `tf2_ros`, `tf2_geometry_msgs`, `geometry_msgs`, `std_srvs`
- PX4 с поддержкой uXRCE-DDS и запущенный `MicroXRCEAgent`

---


## Сборка


```
cd ~/sverk_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select offboard_control
source install/setup.bash

```


---


## Запуск


>

**Примечание** Нода `offboard_control` **уже работает** — её запускает [главный launch-файл](/learn/obrik-ros-2/main-launch) при включении дрона. Для обычной работы запускать её не нужно: сразу управляйте дроном через `sverk_interfaces`. Ручной запуск ниже нужен только для отладки (например, с другими параметрами) — тогда сначала остановите копию из автозапуска.


### Запуск ноды напрямую


>

**Примечание** Команды запускаются **внутри контейнера** `sverk_ros2` — по SSH вы попадаете туда сразу: `ssh sverk@<IP_дрона>` (порт 22, пароль: sverk).


Обычный режим (реальный дрон):


```
ros2 run offboard_control offboard_control

```


Режим симулятора (PX4 SITL добавляет суффикс к топикам):


```
ros2 run offboard_control offboard_control --ros-args -p simulator:=true

```


### Запуск через launch-файл (рекомендуется)


```
ros2 launch offboard_control offboard_control.launch.py

```


С изменением параметров:


```
# другое имя мировой системы координат
ros2 launch offboard_control offboard_control.launch.py map_frame_id:=odom

# медленная скорость по умолчанию и длинный таймаут
ros2 launch offboard_control offboard_control.launch.py default_speed:=0.3 offboard_timeout:=15.0

# запуск с разрешением посадки только в режиме OFFBOARD
ros2 launch offboard_control offboard_control.launch.py land_only_in_offboard:=true

```


---


## Параметры ноды

|  Параметр |  Тип |  По умолчанию |  Что делает |
|  `body_frame_id` |  string |  `base_link` |  Имя фрейма корпуса в TF |
|  `map_frame_id` |  string |  `map` |  Имя мировой системы координат |
|  `aruco_map_frame_id` |  string |  `aruco_map` |  Имя системы координат маркеров |
|  `transform_timeout` |  double |  0.5 |  Сколько секунд ждать пересчёт координат |
|  `offboard_timeout` |  double |  10.0 |  Сколько секунд ждать перехода в OFFBOARD |
|  `arming_timeout` |  double |  5.0 |  Сколько секунд ждать запуска моторов |
|  `default_speed` |  double |  0.5 |  Скорость по умолчанию для navigate (м/с) |
|  `land_only_in_offboard` |  bool |  true |  Разрешать посадку только в режиме OFFBOARD |
|  `check_kill_switch` |  bool |  true |  Учитывать kill switch с аппаратуры управления |
|  `local_position_timeout` |  double |  2.0 |  Таймаут данных о локальной позиции (с) |
|  `global_position_timeout` |  double |  10.0 |  Таймаут данных GPS (с) |
|  `battery_timeout` |  double |  2.0 |  Таймаут данных аккумулятора (с) |
|  `manual_control_timeout` |  double |  0.0 |  Таймаут ручного управления; 0 = отключено |
|  `simulator` |  bool |  false |  Режим симулятора |


---


## Все сервисы


Нода предоставляет сервисы в глобальном пространстве имён: `/navigate`, `/land`, `/get_telemetry` и т.д.


>

**Примечание** Ниже описаны типы сервисов и вызов из терминала через `ros2 service call` — для отладки. Для управления дроном из Python используйте библиотеку `sverk_interfaces` — все команды с примерами собраны в статье [Программирование автономных полётов](/learn/obrik-ros-2/offboard-commands).


---


### /navigate — полёт к точке


Тип: `offboard_interfaces/srv/Navigate`


Плавный полёт к целевой позиции. Курс устанавливается сразу при получении команды. Подходит для взлёта, перелёта по прямой, простых маршрутов.

|  Поле |  Тип |  Описание |
|  `x`, `y`, `z` |  float32 |  Целевая позиция в метрах |
|  `yaw` |  float32 |  Целевой курс в радианах |
|  `speed` |  float32 |  Скорость в м/с |
|  `frame_id` |  string |  Система координат: `map`, `body`, `terrain`, `aruco_map` |
|  `auto_arm` |  bool |  Перейти в OFFBOARD и запустить моторы перед полётом |


Ответ: `success` (bool), `message` (string).


```
# взлёт на 1.5 м (body)
ros2 service call /navigate offboard_interfaces/srv/Navigate "{x: 0.0, y: 0.0, z: 1.5, yaw: 0.0, speed: 1.0, frame_id: 'body', auto_arm: true}"

# полёт к точке (map)
ros2 service call /navigate offboard_interfaces/srv/Navigate "{x: 1.0, y: 0.0, z: 1.0, yaw: 0.0, speed: 0.5, frame_id: 'map', auto_arm: false}"

```


---


### /land — посадка


Тип: `std_srvs/srv/Trigger`


Переводит PX4 в режим AUTO.LAND. Если параметр `land_only_in_offboard:=true`, команда принимается только когда дрон уже в режиме OFFBOARD.


```
ros2 service call /land std_srvs/srv/Trigger "{}"

```


---


### /get_telemetry — телеметрия


Тип: `offboard_interfaces/srv/GetTelemetry`


Возвращает полное состояние дрона.

|  Поле ответа |  Описание |
|  `connected` |  Подключён ли PX4 |
|  `armed` |  Включены ли моторы |
|  `mode` |  Текущий режим (OFFBOARD, POSITION…) |
|  `x`, `y`, `z` |  Позиция в метрах (ENU) |
|  `yaw` |  Курс в радианах (NED, 0 = север) |
|  `vx`, `vy`, `vz` |  Скорость в м/с |
|  `lat`, `lon`, `alt` |  GPS-координаты |
|  `voltage` |  Напряжение аккумулятора в вольтах |


```
ros2 service call /get_telemetry offboard_interfaces/srv/GetTelemetry "{frame_id: 'map'}"

```


---


### /set_altitude — сменить высоту


Тип: `offboard_interfaces/srv/SetAltitude`


Меняет только высоту в текущей миссии, не прерывая полёт.


```
ros2 service call /set_altitude offboard_interfaces/srv/SetAltitude "{z: 2.0, frame_id: 'terrain'}"

```


---


### /set_yaw — повернуться на угол


Тип: `offboard_interfaces/srv/SetYaw`


Меняет курс, не прерывая текущую миссию. `yaw: nan` сбрасывает ручное управление курсом.


```
# поворот на -90° (90° по часовой) относительно корпуса
ros2 service call /set_yaw offboard_interfaces/srv/SetYaw "{yaw: -1.5708, frame_id: 'body'}"

# сбросить управление курсом
ros2 service call /set_yaw offboard_interfaces/srv/SetYaw "{yaw: nan, frame_id: 'body'}"

```


---


### /set_yaw_rate — вращение с постоянной скоростью


Тип: `offboard_interfaces/srv/SetYawRate`


Задаёт угловую скорость по вертикальной оси. Положительное значение — против часовой стрелки (вид сверху).


```
# вращение 0.5 рад/с против часовой
ros2 service call /set_yaw_rate offboard_interfaces/srv/SetYawRate "{yaw_rate: 0.5}"

```


---


### /set_position — задать точку для удержания


Тип: `offboard_interfaces/srv/SetPosition`


Удобно при частом обновлении цели (кружение, следование по траектории). Нода сразу начинает лететь к указанной точке.


```
# зависание на месте
ros2 service call /set_position offboard_interfaces/srv/SetPosition "{x: 0.0, y: 0.0, z: 0.0, yaw: 0.0, frame_id: 'body', auto_arm: false}"

# подняться на 3 м выше текущей позиции
ros2 service call /set_position offboard_interfaces/srv/SetPosition "{x: 0.0, y: 0.0, z: 3.0, yaw: 0.0, frame_id: 'body', auto_arm: false}"

```


---


### /set_velocity — управление скоростью


Тип: `offboard_interfaces/srv/SetVelocity`


Дрон летит с заданными скоростями по осям.


```
# полёт вперёд по корпусу 1 м/с
ros2 service call /set_velocity offboard_interfaces/srv/SetVelocity "{vx: 1.0, vy: 0.0, vz: 0.0, yaw: 0.0, frame_id: 'body', auto_arm: false}"

```


---


### /set_attitude — управление углами (продвинутое)


Тип: `offboard_interfaces/srv/SetAttitude`


Аналог режима STABILIZED: задаёте крен, тангаж, курс и газ напрямую.

|  Поле |  Тип |  Описание |
|  `roll`, `pitch`, `yaw` |  float32 |  Углы в радианах |
|  `thrust` |  float32 |  Газ от 0 до 1 |
|  `frame_id` |  string |  Система координат для yaw |
|  `auto_arm` |  bool |  Перейти в OFFBOARD и запустить моторы |


```
ros2 service call /set_attitude offboard_interfaces/srv/SetAttitude "{roll: 0.0, pitch: 0.05, yaw: 0.0, thrust: 0.5, frame_id: 'map', auto_arm: false}"

```


---


### /set_rates — управление угловыми скоростями (самое низкоуровневое)


Тип: `offboard_interfaces/srv/SetRates`


Аналог режима ACRO. Задаёте скорости вращения по каждой оси и газ.

|  Поле |  Тип |  Описание |
|  `roll_rate`, `pitch_rate`, `yaw_rate` |  float32 |  Угловые скорости в рад/с |
|  `thrust` |  float32 |  Газ от 0 до 1 |
|  `auto_arm` |  bool |  OFFBOARD и запуск моторов при необходимости |


Положительные направления: `yaw_rate` против часовой (вид сверху), `pitch_rate` нос вверх, `roll_rate` влево.


```
ros2 service call /set_rates offboard_interfaces/srv/SetRates "{roll_rate: 0.0, pitch_rate: 0.0, yaw_rate: 0.5, thrust: 0.5, auto_arm: false}"

```


---


### /flip — автоматический кувырок


Тип: `offboard_interfaces/srv/Flip`


Кувырок в три фазы: подъём, вращение, возврат в исходную точку.


>

**Внимание** Минимальная высота перед кувырком — 2 метра.


Как это работает внутри:

|  Фаза |  Что делает PX4 |
|  CLIMB |  Летит вверх со скоростью `vz` в течение `climb_duration` с |
|  ROTATE |  Вращается с угловой скоростью `rate` по оси `axis` до угла `target_angle` |
|  POSITION_HOLD |  Возвращается к исходной позиции и зависает |


```
ros2 service call /flip offboard_interfaces/srv/Flip "{axis: 'roll', vz: 2.0, climb_duration: 0.5, rate: 16.0, target_angle: 6.00, thrust: 0.1, auto_arm: false}"

```


Параметры:

|  Поле |  Описание |
|  `axis` |  `"roll"`, `"pitch"` или `"yaw"` |
|  `vz` |  Скорость подъёма (м/с) |
|  `climb_duration` |  Время подъёма (с) |
|  `rate` |  Скорость вращения (рад/с), знак задаёт направление |
|  `target_angle` |  Целевой угол (рад); 6.28 = полный оборот, 6.0 = чуть меньше |
|  `thrust` |  Газ во время вращения (0.1 обычно хватает) |
|  `auto_arm` |  Перейти в OFFBOARD и запустить моторы перед кувырком |


---


## Типичный сценарий: симулятор SITL


```
# 1. Запустить PX4 SITL + Gazebo (в отдельном терминале)
# 2. Запустить MicroXRCEAgent (в отдельном терминале)
# 3. Запустить offboard_control
ros2 launch offboard_control offboard_control.launch.py

```


```
# 4. Взлёт и полёт — запускаем программу на Python
import sverk_interfaces, time
drone = sverk_interfaces.init(Nodename="sitl_test")
drone.control.navigate(x=0.0, y=0.0, z=1.0, yaw=0.0, speed=0.5,
                        frame_id="body", auto_arm=True)
time.sleep(5.0)
drone.control.land()
drone.close()

```


>

**Примечание** Отладочные команды терминала (echo топиков, список сервисов) — [база знаний: ros2-raw.md](/learn/obrik-ros-2/ros2-raw)


---


## Тестовые программы


В каталоге `examples/` есть две программы для проверки всего функционала:

- `test_fly_cube.py` — взлёт и полёт по траектории «куб» (относительные смещения в body).
- `test_all_services.py` — последовательная проверка всех сервисов: взлёт, set_altitude, set_yaw, set_yaw_rate, set_position, set_velocity, set_attitude, set_rates, посадка.

```
cd ~/sverk_ws && source install/setup.bash
python3 src/sverk_drone/offboard/offboard_control/examples/test_fly_cube.py
python3 src/sverk_drone/offboard/offboard_control/examples/test_all_services.py

```
