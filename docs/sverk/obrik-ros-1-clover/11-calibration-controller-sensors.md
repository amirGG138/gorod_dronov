# Калибровка датчиков

> Раздел: Обрик ROS 1 (Clover) · slug: `calibration-controller-sensors`
> Источник: https://edu.sverk.tech/learn/clover-2/calibration-controller-sensors

---

# Калибровка датчиков


Во вкладке **Sensors** находятся пункты калибровки датчиков Обрика.


>

**Hint** От точности калибровки датчиков зависит качество полёта.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F17.png&sig=ffea0b26045e22f0e12dfac2b42ca0c054a3fc3918d1f989ed3e4eee82ddeba8)



## Шаг 1: Калибровка гироскопа

-

Выберите меню **Gyroscope**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F18.png&sig=b356a3f7397f2a6e2f40c5c95fd3af65bcd373e8f72c05d42a0e816f20330802)


-

Установите Обрик на ровную поверхность

-

Нажмите **Ok**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F19.png&sig=04740003582c95c47b66dfad03fce318fd614100658e21b3762e1058326d0236)


-

Дождитесь окончания калибровки


Если калибровка прошла успешно — рамка будет зелёной, а снизу появится надпись *“Completed”*. Если при калибровке была ошибка — повторите её заново.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F20.png&sig=b3c83db6356319a226e76e69c33c2718ddd0b39d47c23f3ccf9519c1fd70bdb1)



## Шаг 2: Калибровка акселерометра


>

**Note** При калибровке акселерометра необходимо устанавливать Обрик в каждую из указанных ориентаций и удерживать до световой индикации.

-

Выберите меню **Accelerometer**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F21.png&sig=43257c83f67fe013a56efdf78b16c66cd80bcaef1f3b44be2cf191d68e2134f1)


-

Установите параметры **Autopilot Orientation**: **Pitch** 180°, **Yaw** 90° и нажмите **Ok**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F22.png&sig=7e66a4c7301abffb474031a3ff60993c4b8b85c0ceb8e11db0d5e95947f8ffa5)


-

Установите Обрик на шасси — дождитесь появления жёлтой рамки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F23.png&sig=83f7133546f9e6553d9132e598cc5e268e11c73ea1b39c824fdcaa6328a51318)


-

Держите Обрик неподвижно до появления зелёной рамки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F24.png&sig=73936cc8d17b6cc43e0220809f747d047de6642489c8a5772a380c9a0f9170e3)


-

Повторите для всех положений поочерёдно


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2Fcompleted.png&sig=ce0765af011265ecf2ddb11165d553d0b869484f1e95261029cb02d9d6f53f4e)



Если калибровка прошла успешно — все 6 рамок будут зелёными с надписью *“Completed”*. Если при калибровке была допущена ошибка — калибровка сбросится, повторите её заново.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F25.png&sig=0c09c1fa6f877da996dff0039b626d147489b65ab413f86287536305f353ce92)



## Шаг 3: Калибровка уровня горизонта


>

**Note** От точности калибровки уровня горизонта зависит качество полёта.

-

Выберите меню **Horizon**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F26.png&sig=f1ccd93979720ba34393e52385c3abdbbb076362965509be7c1349944c9309fe)


-

Установите Обрик на ровную поверхность

-

Нажмите **Ok**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F27.png&sig=8c5481d347cd84ebb10204d058e853b4f900fdfe4ae0715306e78ea880be4b5f)


-

Дождитесь окончания калибровки
