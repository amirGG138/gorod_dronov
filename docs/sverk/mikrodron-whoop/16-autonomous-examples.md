# Примеры Python-программ

> Раздел: Микродрон (Whoop) · slug: `autonomous-examples`
> Источник: https://edu.sverk.tech/learn/whoop/autonomous-examples

---

# Примеры Python-программ


## Взлёт, полёт вперёд и посадка


Минимальный пример: взлетает, летит вперёд 3 секунды, садится.


```
import time
from simple_offboard_py import SimpleOffboard, Frame

drone = SimpleOffboard()

drone.takeoff(0.7)
print("Взлетели")

drone.set_velocity(1.2, 0.0, 0.0, Frame.LOCAL_NED, None, 0.1)

time.sleep(3)

drone.land()
print("Сели")

```


## Полёт по точкам


Дрон последовательно облетает заданные точки и садится.


```
from simple_offboard_py import SimpleOffboard, Frame

drone = SimpleOffboard()

drone.takeoff(1.0)
print("Взлетели")

# Точки (x, y, z) в системе LOCAL_NED
# Z отрицательный: высота 1 м над землёй = z = -1.0
waypoints = [
    (1.0, 0.0, -1.0),
    (1.0, 1.0, -1.0),
    (0.0, 1.0, -1.0),
]

for x, y, z in waypoints:
    reached = drone.navigate(x, y, z, frame=Frame.LOCAL_NED, yaw=0.0,
                             tolerance=0.15, time_limit=15.0)
    if not reached:
        print(f"Не достиг точки ({x}, {y}, {z}), продолжаю")

drone.land()
print("Сели")

```


## Полёт относительно курса дрона (BODY_NED)


`Frame.BODY_NED` — движение задаётся относительно текущего направления носа дрона. Удобно, когда не важно в какую сторону повёрнут дрон: «вперёд» всегда вперёд по носу.


```
from simple_offboard_py import SimpleOffboard, Frame

drone = SimpleOffboard()

drone.takeoff(0.7)
print("Взлетели")

# Вперёд по носу на 1 м
drone.navigate(1.0, 0.0, -0.7, frame=Frame.BODY_NED, yaw=0.0,
               tolerance=0.1, time_limit=10.0)

# Вправо на 0.5 м
drone.navigate(0.0, 0.5, -0.7, frame=Frame.BODY_NED, yaw=0.0,
               tolerance=0.1, time_limit=10.0)

drone.land()
print("Сели")

```


## Поиск объекта и зависание над ним


Дрон медленно летит вперёд. Как только камера распознаёт нужный объект с достаточной уверенностью — останавливается и зависает на месте.


```
from simple_offboard_py import SimpleOffboard, Frame

TARGET_LABEL = "balloon"  # название объекта из модели

drone = SimpleOffboard()

drone.takeoff(0.7)
print("Взлетели")

drone.set_velocity(0.3, 0.0, 0.0, Frame.BODY_NED, yaw=0.0)

found = False
while not found:
    for det in drone.get_detections():
        if det.label == TARGET_LABEL and det.score > 0.7:
            print(f"Найден: {det.label}, уверенность={det.score:.2f}")
            found = True
            break

# Зависнуть на текущей позиции
x, y, z, _, _, yaw = drone.get_position()
drone.set_position(x, y, z, Frame.LOCAL_NED, yaw=yaw)

drone.land()
print("Сели")

```


Что содержит каждый обнаруженный объект:


```
for det in drone.get_detections():
    print(det.label)    # название: "balloon", "person" и т.д.
    print(det.score)    # уверенность: 0.0 — 1.0
    print(det.x1, det.y1)  # левый верхний угол рамки (пиксели)
    print(det.x2, det.y2)  # правый нижний угол рамки (пиксели)

```
