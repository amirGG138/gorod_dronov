# Программирование автономных полётов

> Раздел: Обрик ROS 2 · slug: `offboard-commands`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/offboard-commands

---

# Программирование автономных полётов


Здесь собраны все команды, которые вы можете отправить дрону из Python-программы. Одна библиотека `sverk_interfaces` берёт на себя всю сложную работу: запуск ROS 2 ноды, подключение к сервисам, пересчёт координат. Вам достаточно двух строк, чтобы поднять дрон в воздух.


---


## Быстрый старт


### Взлёт и посадка за 10 строк


**Что делает программа:** дрон взлетает на 1.5 метра и через 5 секунд садится.


```
import time                            # стандартная библиотека для паузы
import sverk_interfaces                # библиотека управления Обриком

# создаём объект drone — он запускает ROS 2 ноду внутри
drone = sverk_interfaces.init(Nodename="my_first_flight")

# navigate отправляет дрон в точку (x=0, y=0, z=1.5) — это 1.5 м вверх
# frame_id='body' означает «относительно корпуса», auto_arm=True — поднимется сам
resp = drone.control.navigate(
    x=0.0, y=0.0, z=1.5,
    yaw=0.0, speed=1.0,
    frame_id="body",
    auto_arm=True
)
print("Взлёт:", resp.success, resp.message)  # True или False + сообщение

time.sleep(5.0)                        # ждём 5 секунд в воздухе

land_resp = drone.control.land()      # команда посадки
print("Посадка:", land_resp.success)

drone.close()                          # освобождаем ресурсы

```


Команда `navigate` отправляется мгновенно и программа продолжает работу. Дрон летит в фоне, пока вы делаете что-то ещё. Если хотите дождаться прилёта — используйте `navigate_wait`.


---


## Все команды drone.control


### navigate — полёт в точку


Базовая команда. Отправляет дрон к нужным координатам и сразу возвращает управление программе.

|  Параметр |  Тип |  По умолчанию |  Описание |
|  `x`, `y`, `z` |  float |  обязательно |  Координаты цели в метрах |
|  `yaw` |  float |  0.0 |  Целевой курс в радианах |
|  `speed` |  float |  0.5 |  Скорость полёта в м/с |
|  `frame_id` |  str |  `'map'` |  Система координат: `'body'`, `'map'`, `'aruco_map'` |
|  `auto_arm` |  bool |  False |  Если True, сам включит моторы и поднимется |


```
# полёт на 1 метр вперёд относительно корпуса, сохраняя курс
drone.control.navigate(x=1.0, y=0.0, z=0.0, yaw=0.0, speed=0.5, frame_id="body")

```


>

**Примечание** `auto_arm=True` нужен только для **первой** команды взлёта: она переводит дрон в режим OFFBOARD и включает моторы. Если оставить `False`, а моторы ещё не запущены, дрон не взлетит и останется на месте. Когда дрон уже в воздухе, в следующих командах `auto_arm` можно не указывать.


---


### navigate_wait — полёт в точку с ожиданием прилёта


Как `navigate`, но программа ждёт, пока дрон не окажется в нужной точке с заданной точностью.

|  Параметр |  Тип |  По умолчанию |  Описание |
|  `tolerance` |  float |  0.2 |  Допустимое расстояние до цели (м) |
|  `timeout` |  float |  None |  Максимальное время ожидания (с); None = бесконечно |
|  `check_interval` |  float |  0.2 |  Как часто проверять положение (с) |


```
# взлёт и ожидание, пока дрон не окажется в 0.25 м от цели
drone.control.navigate_wait(
    x=0.0, y=0.0, z=1.5,
    frame_id="body",
    auto_arm=True,
    tolerance=0.25,
    timeout=30.0
)
print("Дрон прилетел!")

```


---


### land — посадка


Переводит дрон в режим автоматической посадки (PX4 AUTO.LAND).


```
drone.control.land()

```


---


### get_telemetry — узнать, где дрон и что с ним


Возвращает текущее состояние дрона: координаты, скорость, заряд аккумулятора, режим.


```
t = drone.control.get_telemetry(frame_id="map")

print("Подключён:", t.connected)       # True/False
print("Моторы запущены:", t.armed)     # True = моторы запущены
print("Режим:", t.mode)                # OFFBOARD, POSITION, LAND...
print("Позиция:", t.x, t.y, t.z)      # метры в системе map
print("Скорость:", t.vx, t.vy, t.vz)  # м/с
print("Аккумулятор:", t.voltage, "В")      # напряжение
print("GPS:", t.lat, t.lon, t.alt)     # широта, долгота, высота

```


>

**Примечание** `frame_id` задаёт систему координат, **в которой возвращаются и интерпретируются данные**. `body` — относительно корпуса (X — вперёд, Y — влево, Z — вверх), `map` — мировая система, `terrain` — высота над поверхностью, `aruco_map` — карта ArUco-маркеров. Например, `get_telemetry(frame_id="body")` вернёт позицию и скорость относительно самого дрона, а `frame_id="map"` — относительно мировой системы.


---


### set_altitude — сменить высоту, не меняя курс и положение по X, Y


Удобно, когда нужно просто подняться или спуститься во время полёта.


```
# подняться до 2 м над землёй (terrain = относительно поверхности)
drone.control.set_altitude(z=2.0, frame_id="terrain")

# опуститься до 1 м в мировой системе координат
drone.control.set_altitude(z=1.0, frame_id="map")

```


---


### set_yaw — повернуться на угол


Поворот вокруг вертикальной оси без смены позиции.


```
import math

# повернуться на 90 градусов по часовой (отрицательное = по часовой)
drone.control.set_yaw(yaw=-math.pi / 2, frame_id="body")

# сбросить ручное управление курсом
drone.control.clear_yaw_override()

```


---


### set_yaw_rate — вращаться с постоянной скоростью


Дрон вращается вокруг вертикальной оси до следующей команды.


```
# вращение 0.5 рад/с против часовой стрелки (вид сверху)
drone.control.set_yaw_rate(yaw_rate=0.5)

# остановить вращение — сбросить override
drone.control.clear_yaw_override()

```


---


### set_position — задать точку для удержания (низкоуровневое)


Используется для частого обновления цели, например при полёте по кругу. Нода `offboard_control` сразу начинает лететь к этой точке.


```
import math, time

# полёт по кругу: каждые 0.1 с обновляем цель
start = drone.control.get_telemetry(frame_id="map")
radius = 0.6
for i in range(200):
    angle = i * 0.1 * 0.3          # угол меняется 0.3 рад/с
    x = start.x + math.sin(angle) * radius
    y = start.y + math.cos(angle) * radius
    drone.control.set_position(x=x, y=y, z=start.z, yaw=start.yaw, frame_id="map")
    time.sleep(0.1)

```


---


### set_velocity — управление по скорости


Дрон летит с заданной скоростью по осям, пока не получит новую команду.


```
# лететь вперёд 1 м/с по оси корпуса
drone.control.set_velocity(vx=1.0, vy=0.0, vz=0.0, yaw=0.0, frame_id="body")

```


>

**Примечание** `vx, vy, vz` — скорость в м/с в выбранной `frame_id` (в `body`: `vx` — вперёд, `vy` — влево, `vz` — вверх), `yaw` — курс в радианах. Жёстких ограничений в сервисе нет: предельную скорость задают параметры PX4 (`MPC_XY_VEL_MAX` — по горизонтали, `MPC_Z_VEL_MAX_UP`/`MPC_Z_VEL_MAX_DN` — по вертикали). Для обучения берите небольшие значения — 0.5–1 м/с, как в примерах.


---


### set_attitude — управление по углам (продвинутое)


Аналог режима STABILIZED: вы задаёте углы наклона и газ.


```
import math
# небольшой наклон вперёд + газ 0.5
drone.control.set_attitude(roll=0.0, pitch=0.1, yaw=0.0, thrust=0.5, frame_id="map")

```


>

**Примечание** `roll, pitch, yaw` задаются в радианах, `thrust` — газ в диапазоне 0…1 (около 0.5 удерживает высоту). Начинайте с малых углов (0.05–0.1 рад): большой наклон быстро разгоняет дрон. Предельный наклон в воздухе ограничен параметром PX4 `MPC_TILTMAX_AIR`.


---


### set_rates — управление угловыми скоростями (самое низкоуровневое)


Аналог режима ACRO. Задаёте скорости вращения по каждой оси и газ.


```
# вращение по крену 1 рад/с, газ 0.4
drone.control.set_rates(roll_rate=1.0, pitch_rate=0.0, yaw_rate=0.0, thrust=0.4)

```


Направления: `yaw_rate > 0` — против часовой (вид сверху), `pitch_rate > 0` — нос вверх, `roll_rate > 0` — влево. Угловые скорости задаются в рад/с, `thrust` — газ 0…1.


>

**Внимание** Режим ACRO не стабилизирует углы сам — дрон удерживает заданную скорость вращения, пока не получит новую команду. Используйте только на безопасной высоте и с небольшими значениями.


---


### flip — автоматический кувырок


Дрон делает почти полный оборот по выбранной оси в три автоматических фазы:

- Набор высоты с заданной скоростью `vz` в течение `climb_duration` секунд.
- Вращение по оси с угловой скоростью `rate` до достижения `target_angle`.
- Возврат к начальной позиции.

>

**Внимание** Перед кувырком дрон должен находиться минимум на 2 метра над землёй.


```
# кувырок вперёд (pitch) — дрон должен висеть на высоте >= 2 м
drone.control.flip(
    axis="pitch",          # ось: 'roll', 'pitch' или 'yaw'
    vz=2.0,                # скорость подъёма перед флипом (м/с)
    climb_duration=0.5,    # время подъёма (с)
    rate=16.0,             # скорость вращения (рад/с)
    target_angle=6.0,      # 6.0 рад ≈ почти полный оборот (2*pi = 6.28)
    thrust=0.1,            # тяга во время вращения
    auto_arm=False         # дрон уже в воздухе
)

```


---


## Команды drone.fcu — безопасность и калибровка


### Выключение моторов


```
drone.fcu.disarm()         # штатное выключение (только на земле)
drone.fcu.force_disarm()   # принудительное (можно в воздухе, аварийно!)
drone.fcu.kill_switch()    # мгновенная остановка всех моторов

```


### Калибровки (всегда на земле, до полёта)


```
drone.fcu.calibrate_gyro()        # гироскоп (дрон должен стоять неподвижно)
drone.fcu.calibrate_accel()       # акселерометр (потребует 6 положений)
drone.fcu.calibrate_level()       # горизонт (поставьте дрон ровно)
drone.fcu.calibrate_mag()         # компас (нужно вращать дрон вокруг всех осей)
drone.fcu.calibrate_baro()        # барометр (высотомер)

```


---


## Команды drone.led — светодиодная лента


Доступна, если установлен пакет `led_interfaces` и запущена нода `led_control`.


```
if drone.led:
    # заливка всей ленты красным цветом
    drone.led.set_effect("fill", r=255, g=0, b=0)

    # мигание зелёным
    drone.led.set_effect("blink", r=0, g=255, b=0)

    # радуга по всей ленте
    drone.led.set_effect("rainbow")

    # управление отдельными светодиодами: (индекс, r, g, b)
    drone.led.set_leds([(0, 255, 0, 0), (1, 0, 255, 0), (2, 0, 0, 255)])

```


Доступные эффекты: `fill`, `blink`, `blink_fast`, `fade`, `wipe`, `flash`, `rainbow`, `rainbow_fill`.


---


## Настройка значений по умолчанию


Если все команды используют одинаковые параметры, задайте их один раз:


```
drone.control.configure_defaults(
    frame_id="body",    # все команды без явного frame_id — в body
    speed=0.5,          # скорость по умолчанию
    auto_arm=False,     # не запускать моторы автоматически
    tolerance=0.25,     # точность navigate_wait
    timeout=60.0        # максимальное ожидание
)

# теперь можно коротко
drone.control.navigate_wait(x=0.0, y=0.0, z=1.5)  # frame_id='body', speed=0.5

```


---


## Жизненный цикл программы


`sverk_interfaces.init(...)` сам запускает ROS 2, если он ещё не запущен. `drone.close()` корректно завершает работу. При любом выходе из программы (даже при ошибке) библиотека вызовет `close()` автоматически через `atexit`.


Рекомендуемая структура любой программы:


```
import sverk_interfaces

drone = sverk_interfaces.init(Nodename="my_program")
try:
    # весь код полёта здесь
    pass
finally:
    drone.close()  # выполнится даже при ошибке

```


---


## Готовые примеры в репозитории


```
cd ~/sverk_ws && source install/setup.bash

```


>

**Примечание** Команды запускаются **внутри контейнера** `sverk_ros2` — по SSH вы попадаете туда сразу: `ssh sverk@<IP_дрона>` (порт 22, пароль: sverk).


```
# взлёт на 1 м вперёд и посадка
python3 src/sverk_drone/sverk_interfaces/examples/simple_takeoff_land.py

# квадрат в плоскости map
python3 src/sverk_drone/sverk_interfaces/examples/square_mission.py

# объёмная фигура «куб» в системе body
python3 src/sverk_drone/sverk_interfaces/examples/cube_mission.py

# полёт по кругу через set_position
python3 src/sverk_drone/sverk_interfaces/examples/circle_trajectory.py

# монитор телеметрии в консоль
python3 src/sverk_drone/sverk_interfaces/examples/telemetry_monitor.py

# безопасное выключение и калибровки
python3 src/sverk_drone/sverk_interfaces/examples/safety_and_calibration.py

# эффекты светодиодной ленты
python3 src/sverk_drone/sverk_interfaces/examples/led_effects.py

# управление отдельными светодиодами
python3 src/sverk_drone/sverk_interfaces/examples/led_set_leds.py

```
