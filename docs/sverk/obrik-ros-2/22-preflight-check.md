# Проверка перед полётом

> Раздел: Обрик ROS 2 · slug: `preflight-check`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/preflight-check

---

# Проверка перед полётом


Перед каждым взлётом запускайте автоматическую проверку — программа `selfcheck.py` проверяет все ключевые системы Обрика за одну команду. Это занимает меньше минуты и помогает предотвратить аварию.


Если хотя бы один пункт выдаёт ошибку — взлёт запрещён.


---


## Подготовка

-

Разместите карту ArUco-меток в центре полётной зоны.

-

Включите аппаратуру управления.

-

Переведите левый стик вниз, правый — в центральное положение.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_stick-down.png&sig=8193a7b4c058774f29981c26222122637cdef905ac43a4ffb1574d737841f1ba)


- Установите Обрик на точку взлёта.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fvisual3.png&sig=b60ece389e43b5cc5b6dc7bf1b16db1281eeb5ca48fb1054a1f54f1922089dcf)


- Подключите [АКБ](/learn/obrik-ros-2/battery-li-po) к Обрику.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fvisual4.png&sig=06f81cb43bf599bdf339b60d73c27f2fdaf1abe21e6f806847c4519bb6f90fec)


-

Дождитесь полного включения Обрика.


>

**Примечание** Обрик полностью включён, когда его Wi-Fi сеть появилась в списке доступных сетей.

-

Подключитесь к [Обрику по Wi-Fi](/learn/obrik-ros-2/qgc-wifi).

-

Откройте веб-интерфейс и запустите терминал.


---


## Запуск проверки


```
ros2 run self_check selfcheck.py

```


---


## Что проверяется

|  Проверка |  Что контролируется |
|  Связь с PX4 (FMU) |  Наличие данных от полётного контроллера: статус, режим, failsafe-флаги |
|  Аккумулятор |  Уровень заряда, напряжение на банку, ток, температура |
|  IMU и ориентация |  Обновление гироскопа и акселерометра, предупреждение при сильном наклоне |
|  Локальная позиция PX4 |  Текущие координаты и скорости от оценщика PX4 |
|  Камера |  Поступление кадров с камеры |
|  ArUco-маркеры |  Обнаружение маркеров в поле зрения камеры |
|  ArUco-позиция |  Поступление позиции от системы навигации по маркерам |
|  Скорость (VPE) |  Сравнение визуальной одометрии от ArUco с данными PX4 |
|  Здоровье SBC |  Свободное место на диске и температурный троттлинг бортового компьютера |
|  CPU |  Загрузка процессора |


Обращайте особое внимание на строки `WARNING`. Особенно важна проверка **Velocity estimation (VPE)**: если оценка скоростей работает некорректно, автономные полёты лучше не запускать.


Критические пункты — должны быть зелёными перед взлётом:

- **ArUco** — маркеры распознаются
- **Local position** — позиция вычислена
- **FMU** — связь с полётным контроллером есть
- **Velocity estimation** — скорость определена

>

**Примечание** При ошибках обращайтесь в [техподдержку](https://t.me/sverk_support).


---


## Примеры вывода


### Успешная проверка


Все строки — `[INFO]`. Ни одного `[WARN]` или `[ERROR]` — взлетать можно.


```
[INFO] [selfcheck]: Performing selfcheck (ROS 2, PX4 DDS)...
[INFO] [selfcheck]: [FMU (PX4 DDS)] VehicleStatus: updated
[INFO] [selfcheck]: [FMU (PX4 DDS)] battery voltage: 11.94 V (3.98 V/cell, 3 cells)
[INFO] [selfcheck]: [FMU (PX4 DDS)] battery remaining: 78%
[INFO] [selfcheck]: [FMU (PX4 DDS)] battery warning: 0
[INFO] [selfcheck]: [FMU (PX4 DDS)] failsafe flags: none active
[INFO] [selfcheck]: [VehicleControlMode / flight mode] mode: POSCTL (2)
[INFO] [selfcheck]: [PX4 Local Position] pos=(-0.03, 0.02, 0.00) m, vel=(0.00, 0.00, 0.00) m/s, valid(xy=True, z=True, v_xy=True, v_z=True)
[INFO] [selfcheck]: [IMU (PX4 DDS)] SensorCombined: updated
[INFO] [selfcheck]: [Attitude (PX4 DDS)] attitude r/p/y: 0.21 / -0.43 / 12.44 deg
[INFO] [selfcheck]: [Local position (ArUco)] PoseWithCovarianceStamped: updated
[INFO] [selfcheck]: [Velocity estimation (from ArUco pose)] max horizontal velocity: 0.003 m/s (threshold=0.100)
[INFO] [selfcheck]: [Velocity estimation (from ArUco pose)] max vertical velocity: 0.001 m/s (threshold=0.100)
[INFO] [selfcheck]: [Camera] Image: updated
[INFO] [selfcheck]: [ArUco markers] Markers: updated
[INFO] [selfcheck]: [VPE (vision input vs PX4 estimate)] VPE vs PX4 odom: horiz=0.012 m, vert=0.003 m (threshold=0.50)
[INFO] [selfcheck]: [VPE (vision input vs PX4 estimate)] estimator flags: no failure/fault/invalid flags active
[INFO] [selfcheck]: [SBC health] disk free: 12.34 GB (total: 28.87 GB)
[INFO] [selfcheck]: [SBC health] throttle flags: none set
[INFO] [selfcheck]: [CPU usage] 12.4

```


---


### Проверка с ошибками


```
[INFO] [selfcheck]: [FMU (PX4 DDS)] battery voltage: 10.41 V (3.47 V/cell, 3 cells)
[WARN] [selfcheck]: [FMU (PX4 DDS)] WARNING: low cell voltage: 3.47 V/cell (min=3.50); recharge battery

[INFO] [selfcheck]: [Attitude (PX4 DDS)] attitude r/p/y: 3.41 / -5.12 / 22.30 deg
[WARN] [selfcheck]: [Attitude (PX4 DDS)] WARNING: roll is 3.41 deg; place copter horizontally or redo level horizon calib
[WARN] [selfcheck]: [Attitude (PX4 DDS)] WARNING: pitch is 5.12 deg; place copter horizontally or redo level horizon calib

[WARN] [selfcheck]: [Local position (ArUco)] WARNING: PoseWithCovarianceStamped: NOT updated (/aruco_map/pose_cov)
[WARN] [selfcheck]: [Velocity estimation] WARNING: velocity estimate: NOT available (insufficient pose samples)

[WARN] [selfcheck]: [ArUco markers] WARNING: Markers: NOT updated (/markers)

[WARN] [selfcheck]: [VPE (vision input vs PX4 estimate)] WARNING: VPE input odometry: NOT updated (/fmu/in/vehicle_visual_odometry)

```

|  Сообщение |  Что означает |  Что делать |
|  `low cell voltage: 3.47 V/cell` |  Аккумулятор разряжен |  Зарядить перед полётом |
|  `roll/pitch N deg; place copter horizontally` |  Дрон стоит на наклонной поверхности или не откалиброван уровень горизонта |  Выровнять, повторить Level Horizon |
|  `PoseWithCovarianceStamped: NOT updated` |  ArUco не передаёт позицию — маркеры не видны или система не запущена |  Проверить карту меток и запуск |
|  `Markers: NOT updated` |  Камера не видит маркеры |  Проверить освещение, карту, фокус камеры |
|  `VPE input odometry: NOT updated` |  PX4 не получает визуальную одометрию от ArUco |  Критично — автономный полёт запрещён |


---


## Параметры


Стандартные топики Обрика прописаны по умолчанию — менять их не нужно. Флаги переопределения нужны только при нестандартной конфигурации или для отключения отдельных проверок:


```
# Отключить проверку VPE и здоровья бортового компьютера
ros2 run self_check selfcheck.py --no-vpe --no-sbc-health

# Указать количество ячеек АКБ для проверки напряжения на банку
ros2 run self_check selfcheck.py --battery-cells 3

```
