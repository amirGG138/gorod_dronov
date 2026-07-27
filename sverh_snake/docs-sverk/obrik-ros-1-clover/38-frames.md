# Системы координат (фреймы)

> Раздел: Обрик ROS 1 (Clover) · slug: `frames`
> Источник: https://edu.sverk.tech/learn/clover-2/frames

---

# Системы координат (фреймы)


![Системы координат коптера (TF2)](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fframes.png&sig=13cf35c82f2608bf39ee5caa1fbb55dfa9e35a7d911858bdd9971f11b1b81c6d)



Основные фреймы в пакете `sverk`:

- `map` — координаты относительно точки инициализации полётного контроллера: белая сетка на иллюстрации;
- `base_link` — координаты относительно квадрокоптера: схематичное изображение квадрокоптера на иллюстрации;
- `body` — координаты относительно квадрокоптера без учета наклонов по тангажу и крену: красная, синяя и зеленая линии на иллюстрации;
- <a name=“navigate_target”></a>`navigate_target` – координаты точки, в которую сейчас летит дрон (с использованием [navigate](/learn/clover-2/commands-offboard-flight#navigate));
- `terrain` – координаты относительно пола в текущей позиции коптера (см. сервис [set_altitude](commands_offboard_flight#set_altitude))
- `setpoint` – текущий setpoint по позиции;
- `main_camera_optical` – система координат, [связанная с основной камерой](/learn/clover-2/camera-setup#%D0%BD%D0%B0%D1%81%D1%82%D1%80%D0%BE%D0%B9%D0%BA%D0%B0-%D1%80%D0%B0%D1%81%D0%BF%D0%BE%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D1%8F-%D0%BA%D0%B0%D0%BC%D0%B5%D1%80%D1%8B).

При использовании [системы позиционирования по ArUco-маркерам](/learn/clover-2/aruco) появляются дополнительные фреймы:

- `aruco_map` – координаты относительно [карты ArUco-маркеров](/learn/clover-2/aruco-map);
- `aruco_N` – координаты относительно [маркера](/learn/clover-2/aruco) с ID=N.

>

**Hint** В соответствии с [соглашением](http://www.ros.org/reps/rep-0103.html), для фреймов, связанных с коптером, ось X направлена вперед, Y – налево и Z – вверх.


Более наглядно 3D визуализацию систем координат можно наблюдать, используя [rviz](/learn/clover-2/rviz).


## tf2


Основная документация: [http://wiki.ros.org/tf2](http://wiki.ros.org/tf2)


Для работы с системами координат в Обрике используется ROS-пакет tf2. tf2 – это набор библиотек для языков программирования C++, Python и других, которые помогают работать с системами координат. ROS-ноды публикуют в топик `/tf` сообщения формата `TransformStamped`, которые содержат в себе трансформации между заданными системами координат в определенные моменты времени.


С помощью [`simple_offboard`](/learn/clover-2/commands-offboard-flight) можно запросить расположение коптера в любой системе координат, используя аргумент `frame_id` сервиса `get_telemetry`.


Из Python можно использовать библиотеку tf2 для преобразования геометрических объектов (например, PoseStamped, PointStamped) из одной системы координат в другую.
