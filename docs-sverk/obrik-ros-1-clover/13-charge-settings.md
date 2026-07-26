# Настройка питания

> Раздел: Обрик ROS 1 (Clover) · slug: `charge-settings`
> Источник: https://edu.sverk.tech/learn/clover-2/charge-settings

---

# Настройка питания


## Индикатор напряжения


Для того чтобы не испортить аккумулятор, рекомендуется использовать индикатор напряжения (пищалку).


Подключите пищалку к балансировочному разъёму аккумулятора. Нажимая кнопку в основании, можно изменять минимальное напряжение на ячейках. Оптимальное значение — **3.5–3.6 V**.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2FDSCF6509.png&sig=12b2056e3db5a8a7b3cf450a0af0a9cf7cbb8cf3d1b1f3db4fd56e1d049a8be1)



>

**Caution** Перед настройкой питания убедитесь, что пропеллеры не установлены на моторах.


## Настройка параметров АКБ в QGC


Во вкладке **Power** настраиваются параметры АКБ.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F38.png&sig=05ac7dd65b3261d668dd41c5cf88b1d59e84a5fd5b0a720ec1689ac0a5ff025a)



>

**Caution** Обращайте внимание на маркировку АКБ — сверьтесь с [параметрами](/learn/clover-2/akb#2-%D0%BD%D0%B0%D0%BF%D1%80%D1%8F%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5-%D1%8F%D1%87%D0%B5%D0%B5%D0%BA-%D1%82%D0%B0%D0%B1%D0%BB%D0%B8%D1%86%D0%B0-%D0%B7%D0%BD%D0%B0%D1%87%D0%B5%D0%BD%D0%B8%D0%B9).

-

Установите параметр **Number of cells** в соответствии с количеством ячеек в АКБ (3S для Обрика)

-

Установите параметр **Empty Voltage** (минимальное напряжение ячейки) — значение **3.30 V** (для LiPo АКБ)

-

Установите параметр **Full Voltage** (максимальное напряжение ячейки) — значение **4.20 V** (для LiPo АКБ)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F39.png&sig=2da796c11babc33baee86f903631006bdb73210628b2bf6ac86fb610a8663e4a)



## Калибровка делителя напряжения

-

Подключите индикатор напряжения к балансировочному разъёму АКБ

-

Нажмите кнопку **Calculate** напротив надписи **Voltage Divider**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F40.png&sig=2cd68eb55a27697912d36a41fcde6a31c793b43503477f7ce3615ec025ae266f)


-

Введите в открывшемся поле суммарное значение с индикатора напряжения

-

Нажмите **Close**, чтобы сохранить рассчитанное значение


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F41.png&sig=c213b9523d8d1ae468991c118a785bd3192534fcff48dbe1b5dd878b07949f29)



>

**Note** Если индикатор напряжения недоступен, установите усреднённое значение делителя напряжения для комплекта Обрика: **Voltage divider = 11**.


## Проверка


После настройки и калибровки полётного контроллера перейдите на вкладку **Summary**. Все пункты должны быть отмечены зелёным маркером.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F42.png&sig=0b768370ea4dc2a38010131d7627a65902401dacaa20925b05d4ecb1fb471574)
