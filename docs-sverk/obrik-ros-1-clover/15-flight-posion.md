# Полёт в режиме Position

> Раздел: Обрик ROS 1 (Clover) · slug: `flight-posion`
> Источник: https://edu.sverk.tech/learn/clover-2/flight-posion

---

# Полёт в режиме Position


>

**Caution** Обязательный шаг перед первым запуском автономного полёта.

-

[Включить аппаратуру управления](/learn/clover-2/hardware-control)

-

Перевести левый стик вниз, а правый в центральное положение


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_stick-down.png&sig=363c87693c1d2ca9ee0ffa9ae355165e517c78e58c8e6f6d2885858058bdf33c)


-

На аппаратуре управления переведите переключатель **SB** в положение **Position** (как было настроено в разделе в [Настройка аппаратуры управления](/learn/clover-2/controller-settings))


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_up.png&sig=d26d02d512cf2eccc9d4f337d0f68fdfdad59bdf2f31c56b1f9ae17f5b0b907e)


-

Установите Обрик на точку взлета


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdron_on_start2.png&sig=2d20077a1d8d8aaa734d4e069cf3fc5ee8a8d64667cbf876cd4640db69d2ce73)


-

Подключите [АКБ](/learn/clover-2/akb) к Обрику


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdron_on_start_back2.png&sig=fe9f3a02b52b13024056626ac2ea4b6e97ebf3d328d23e1465b889fdaa55e60f)


-

Дождитесь полного включения Обрика


>

**Hint** Обрик полностью включен, если появилась Wi-Fi сеть


## Запуск Обрика и взлет


Кнопка **SA** - **Arm/Disarm** (включение/отключение моторов).


Переключатель **SB** - Выбор режима полёта.


Кнопка SD - Kill Switch (экстренное отключение моторов).


>

**Caution** Убедитесь, что кнопка **SD (Kill switch)** в положении выкл. (отжата)


Нажмите и отпустите кнопку **SA (Arm)**, моторы начнут вращаться на минимальных оборотах


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_SA-down.png&sig=193ea7184834d297defe169606c97eee4b9d9de24391102e4265b0c21017bd1a)



>

**Caution** Кнопка должна заблокироваться в нажатом положении


Плавно поднимите **левый стик** (Throttle) вверх. Обрик взлетит и автоматически зависнет на высоте ~1 метра


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fradiomaster_front_stick-down-up.png&sig=13c720cae77508cdfad27a7389780e55790008c09cc92242416453c1d0505f9a)



Попробуйте немного подвигать **правым стиком** (Pitch/Roll). Обрик будет двигаться в пространстве, а при отпускании стика — снова зависать на месте


>

**Caution** Не улетайте далеко от поля меток, иначе Обрик потеряется


## Посадка и выключение

- Для посадки плавно опустите **левый стик** (Throttle) вниз до полной посадки Обрика
- Нажмите и отпустите кнопку **SA (Disarm)**

>

**Caution** Кнопка должна выйти из заблокированного положения

- В целях безопасности нажмите и отпустите кнопку **SD (Kill Switch)**

>

**Caution** Кнопка должна заблокироваться в нажатом положении

- Отключите АКБ от Обрика
- Выключите аппаратуру управления
