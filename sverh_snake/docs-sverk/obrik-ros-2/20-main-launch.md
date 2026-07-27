# Запуск системы

> Раздел: Обрик ROS 2 · slug: `main-launch`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/main-launch

---

# Запуск системы


У Обрика есть **один главный launch-файл**, который запускает сразу все основные системы дрона. Он стартует **автоматически** при включении дрона — вам не нужно вручную запускать камеру, ArUco и `offboard_control`, ленту или веб-интерфейс по отдельности. Включили дрон — всё уже работает.


Файл launch-файла:


```
sverk_ws/src/sverk_drone/main_package/launch_system/launch/full_system_real.launch.py

```


---


## Как происходит автозапуск


Когда вы включаете плату, цепочка такая:


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fautostart-flow.svg&sig=a1a779b542109d3af7691ff4aceb6decbadd3c45f1ed31e9db17384374055da5)



Поэтому, как только дрон включился и появилась его Wi-Fi сеть, все сервисы (`/navigate`, `/land`, лента, видеопоток, ArUco-навигация) уже доступны.


---


## Что запускает главный launch-файл


**Ядро — работает всегда:**

|  Система |  Что делает |
|  `MicroXRCEAgent` |  мост между бортовым компьютером и PX4 (по UART) |
|  `mavlink-routerd` |  мост к QGroundControl по Wi-Fi |
|  Камера |  публикует кадры в `/camera_1/image_raw` |
|  ArUco (детект, карта, локализация) |  определяет позицию дрона по меткам на полу |
|  VIO (`px4_local_pose_publisher`) |  передаёт позицию от ArUco в PX4 |
|  `offboard_control` |  принимает команды полёта (`/navigate`, `/land`, телеметрия) |
|  `led_control` |  управление светодиодной лентой |
|  Веб |  видеопоток, rosboard, HTTP API, сервисы калибровки |


Именно поэтому в статьях по программированию **не нужно** запускать `ros2 run offboard_control` или `ros2 launch led_control` — эти ноды уже подняты автозапуском.


**Опциональная периферия — НЕ в автозапуске:**


Серво, лазерные дальномеры VL53L1X, Arduino и лидар главный launch-файл по умолчанию **не** запускает. Их вы запускаете сами (отдельным `ros2 launch`, как описано в их разделах) — или добавляете в главный launch-файл, если хотите, чтобы они тоже поднимались автоматически.


---


## Как настроить, что запускается


В начале файла `full_system_real.launch.py` — простые флаги-выключатели. Поставьте `True`/`False`, чтобы включить или выключить подсистему:


```
ENABLE_ARUCO = True
ENABLE_CAMERA = True
ENABLE_VIO = True            # отправлять позицию от ArUco в PX4
ENABLE_MAVLINKROUTER = True  # мост к QGroundControl
ENABLE_WEB = True
ENABLE_LED = True
ENABLE_AI = False
ENABLE_LIDAR = False

MK_NAME = "RPI"              # тип платы: RPI | RADXA | RDX | ORANGE | ORANGE_3W

```

- **`ENABLE_*`** — включить/выключить подсистему.
- **`MK_NAME`** — какая у вас плата. От этого зависит, к какому порту подключается PX4-мост (`/dev/ttyAMA0`, `/dev/ttyS2` и т.д.) и какой драйвер камеры используется. **Поставьте значение для своей платы.**
- Ниже в файле — параметры камеры (`CAMERA_SENSOR`, `CAMERA_WIDTH`, `CAMERA_HEIGHT`, `CAMERA_FPS`).

---


## Как применить изменения в коде


Главный launch-файл и весь код Обрика собираются через `colcon`. Чтобы изменения (в коде или во флагах launch-файла) вступили в силу:


**Шаг 1. Пересобрать — внутри контейнера** (по SSH вы и так в контейнере, порт 22):


```
cd ~/sverk_ws
colcon build --packages-select launch_system   # если менял сам launch-файл
# или colcon build — пересобрать всё, если менял код пакетов
source install/setup.bash

```


**Шаг 2. Перезапустить контейнер — на хосте** (порт 2222), чтобы автозапуск поднял системы заново:


```
ssh -p 2222 <пользователь>@<IP_дрона>
sudo systemctl restart sverk-ros2-docker

```


Команда `restart` одинакова для всех плат: в systemd сервис всегда установлен под именем `sverk-ros2-docker`. По платам различаются только пользователь хоста и **исходный файл** сервиса в репозитории — при установке его копируют в systemd под общим именем:


```
sudo cp ~/sverk-ros2/scripts/sverk-ros2-docker-rpi.service /etc/systemd/system/sverk-ros2-docker.service

```

|  Плата |  `MK_NAME` |  Файл сервиса в репозитории |  Пользователь хоста |
|  Raspberry Pi CM5 |  `RPI` |  `sverk-ros2-docker-rpi.service` |  `pi` |
|  Radxa CM5 |  `RADXA` |  `sverk-ros2-docker-radxa.service` |  `rock` |
|  Orange Pi 5 Pro |  `ORANGE` |  `sverk-ros2-docker-orange.service` |  `orangepi` |
|  Orange Pi Zero 3W |  `ORANGE_3W` |  `sverk-ros2-docker-orangepi-zero3w.service` |  `orangepi` |
|  RDK X3 |  `RDX` |  (своя настройка платы) |  `sunrise` |


>

**Подсказка** Можно просто перезагрузить плату (`sudo reboot` на хосте) — после загрузки автозапуск всё поднимет сам. `systemctl restart` быстрее, потому что не ждёт полной перезагрузки.


---


## Когда запускать ноды вручную


Ручной `ros2 run` / `ros2 launch` нужен в двух случаях:

- **Опциональная периферия** (серво, дальномеры, Arduino, лидар) — её в автозапуске нет, поэтому запускаете сам.
- **Отладка** — когда хотите перезапустить один узел с другими параметрами. Тогда сначала желательно остановить его копию из автозапуска (перезапуск контейнера вернёт всё как было).

Проверить, что уже запущено:


```
ros2 node list      # список запущенных нод
ros2 topic list     # список топиков

```
