# Полёт в режиме Position

> Раздел: Обрик ROS 2 · slug: `first-flight`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/first-flight

---

# Полёт в режиме Position


Режим Position удерживает Обрик в точке. Положение дрона вычисляет фильтр Калмана (EKF2) — он объединяет данные всех источников: IMU, оптического потока, дальномера и ArUco-меток. Камера нижнего обзора и метки работают не в одиночку, а в симбиозе с остальными датчиками внутри общего фильтра. Этот раздел описывает первый реальный полёт — от включения аппаратуры управления до посадки.


>

**Внимание** Обязательно прочитайте [правила техники безопасности](/learn/obrik-ros-2/safety) перед первым полётом, если ещё не сделали этого.


---


## Режим Position


В режиме **Position** Обрик использует данные с камеры нижнего обзора и ArUco-маркеров, чтобы точно знать своё положение в пространстве. Это позволяет дрону висеть на месте без вашего участия — он сам компенсирует ветер и другие воздействия.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fposition-mode.svg&sig=7f4a02c8c54b0f9e0021a057d9c25c71313337973c8e72a7e95e9eb903bd3797)



Именно поэтому режим Position — лучший для первого полёта и обязательный шаг перед автономным программированием.


---


## Подготовка к полёту


Выполняйте шаги строго по порядку:


**Шаг 1.** [Включите аппаратуру управления](/learn/obrik-ros-2/transmitter-bind)


**Шаг 2.** Переведите **левый стик вниз**, правый — в центральное положение.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_stick-down.png&sig=8193a7b4c058774f29981c26222122637cdef905ac43a4ffb1574d737841f1ba)



>

**Подсказка** Левый стик вниз = газ на нуле. Это безопасное положение для подключения аккумулятора.


**Шаг 3.** Переведите переключатель **SB** в положение **Position** (как было настроено в разделе [Настройка аппаратуры управления](/learn/obrik-ros-2/transmitter-calibration)).


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_up.png&sig=9e32752cd23e921f6303c4ba444eebc0543fdcc6800b43f65e6c7fb0950223a7)



**Шаг 4.** Установите Обрик на точку взлёта — в центре поля ArUco-меток.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fvisual3.png&sig=b60ece389e43b5cc5b6dc7bf1b16db1281eeb5ca48fb1054a1f54f1922089dcf)



**Шаг 5.** Подключите [АКБ](/learn/obrik-ros-2/battery-li-po).


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fvisual4.png&sig=06f81cb43bf599bdf339b60d73c27f2fdaf1abe21e6f806847c4519bb6f90fec)



**Шаг 6.** Дождитесь полного включения Обрика.


>

**Подсказка** Обрик полностью включён, когда в списке Wi-Fi сетей появилась его точка доступа.


---


## Запуск и взлёт


Познакомьтесь с кнопками аппаратуры управления перед взлётом:

|  Кнопка |  Назначение |
|  **SA** |  Arm / Disarm — запуск / остановка моторов |
|  **SB** |  Выбор режима полёта (Position / Altitude / Stabilized) |
|  **SD** |  Kill Switch — **экстренное** отключение моторов |


>

**Внимание** Перед взлётом убедитесь, что кнопка **SD (Kill Switch)** отжата — она не должна быть заблокирована в нажатом положении.


---


**Arm (запуск моторов):**


Нажмите и отпустите кнопку **SA (Arm)** — моторы начнут вращаться на минимальных оборотах.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_SA-down.png&sig=deedbce86ed11c4c32b0c139effd8bbbbc9e9d60b43eb28fa55e00a9cdcf2314)



>

**Внимание** Кнопка SA должна заблокироваться в нажатом положении — это значит, что Arm активен.


---


**Взлёт:**


Плавно поднимите **левый стик (Throttle)** вверх. Обрик взлетит и автоматически зависнет на высоте около 1 метра — режим Position сам удержит его.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_stick-down-up.png&sig=4c48e44b14ba6a695387e33fc444137f33c60e3aad4c4205548810b8d3493947)



---


**Управление в воздухе:**


Попробуйте немного подвигать **правым стиком (Pitch/Roll)**. Обрик будет двигаться в пространстве, а при отпускании стика — снова зависать на месте.


>

**Внимание** Не улетайте далеко от поля ArUco-меток. Если камера перестанет видеть метки, Обрик потеряет ориентацию и может вести себя непредсказуемо.


---


## Посадка и выключение


Выполняйте строго по порядку:


**Шаг 1.** Плавно опустите **левый стик (Throttle) вниз** до полной посадки. Не торопитесь — дайте дрону мягко сесть.


**Шаг 2.** Нажмите и отпустите кнопку **SA (Disarm)**.


>

**Внимание** Кнопка SA должна выйти из заблокированного положения — моторы остановятся.


**Шаг 3.** В целях безопасности нажмите и отпустите кнопку **SD (Kill Switch)**.


>

**Внимание** Кнопка SD должна заблокироваться в нажатом положении.


**Шаг 4.** Отключите АКБ.


**Шаг 5.** Выключите аппаратуру управления.
