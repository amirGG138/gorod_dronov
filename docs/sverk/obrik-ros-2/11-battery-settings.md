# Настройка питания и мониторинга АКБ

> Раздел: Обрик ROS 2 · slug: `battery-settings`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/battery-settings

---

# Настройка питания и мониторинга АКБ


Полётный контроллер PX4 следит за уровнем заряда АКБ и предупреждает о разрядке. Этот раздел описывает настройку мониторинга аккумулятора в QGC. Устройство аккумулятора, маркировку и безопасные напряжения подробно разбирает отдельная статья [Аккумулятор (АКБ)](/learn/obrik-ros-2/battery-li-po).


---


## Какой аккумулятор у Обрика


Обрик по умолчанию использует **LiHV** (высоковольтный литий-полимерный) аккумулятор, но поддерживает и обычный **LiPo**. Оба собраны из последовательно соединённых **ячеек** (cells): маркировка **3S** означает «3 ячейки в серии».


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Flipo-cells.svg&sig=d94a1f6be8d416a7d4bb5b1f726d5fc9179c5fc3a2a545a8ee5fbff5df302df4)



Про химию, маркировку, зарядку и безопасные напряжения каждой химии — в статье [Аккумулятор (АКБ)](/learn/obrik-ros-2/battery-li-po). Здесь важно одно: за напряжением нужно следить, иначе аккумулятор можно повредить или посадить дрон.


### Зачем следить за напряжением в полёте


При нагрузке (работающих моторах) напряжение аккумулятора **резко падает**, а когда нагрузка снимается — немного восстанавливается. Это значит, что в воздухе аккумулятор «выглядит» более разряженным, чем он есть. PX4 учитывает это и заранее предупреждает о низком заряде.


Если не следить за зарядом:

- аккумулятор может сесть прямо в воздухе → дрон упадёт;
- глубокий разряд → потеря ёмкости и износ аккумулятора.

---


## Звуковой индикатор напряжения


**Звуковой индикатор** — небольшое устройство, которое подключается к **балансировочному разъёму** аккумулятора и подаёт звуковой сигнал, когда напряжение любой ячейки падает ниже заданного порога.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fbuzzer-connection.svg&sig=40d88efa8d9bd399b2bec33ca3ad1be330b8a301c51b0319f1a7d71e8e5cf91c)



Нажимая кнопку на основании индикатора, можно изменить пороговое напряжение. **Оптимальное значение: 3.5–3.6 В** на ячейку.


<p>
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2FDSCF6503.png&sig=91827f27dc40483b913d6ab6132b1e9ecf85de270262c7e287a14b8bd44b9456)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2FDSCF6509.png&sig=ac5c2a40d4967d5f704a1495377df934dd00851b2166120114d580e0e6fad28e)
</p>


---


## Настройка питания в QGC


>

**Внимание** Перед настройкой убедитесь, что пропеллеры **не установлены** на моторах.


Откройте вкладку **Power** в Vehicle Configuration.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F38.png&sig=8b8e788f7a3c6f612d393eb4af1a75d6445453b662c6c87568704d052da020fa)



>

**Примечание** Сверьте маркировку АКБ с [допустимыми напряжениями](/learn/obrik-ros-2/battery-li-po#%D0%BD%D0%B0%D0%BF%D1%80%D1%8F%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5-%D1%8F%D1%87%D0%B5%D0%B5%D0%BA-%D1%87%D1%82%D0%BE-%D0%BC%D0%BE%D0%B6%D0%BD%D0%BE-%D1%87%D1%82%D0%BE-%D0%BD%D0%B5%D0%BB%D1%8C%D0%B7%D1%8F) своего аккумулятора


### Основные параметры


Установите следующие значения (стандартные для 3S-аккумулятора Обрика):

- **Number of cells** → `3` (три ячейки, аккумулятор 3S)
- **Empty Voltage** → `3.30 В` (минимально допустимое напряжение ячейки)
- **Full Voltage** → `4.20 В` (напряжение ячейки для отметки «полный заряд»)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F39.png&sig=9d7fe1ec22f49e5a3eed371679778208da27c67acf1471953465b91ad02a5ed4)



>

**Примечание** PX4 получает от измерительной схемы суммарное напряжение аккумулятора (для 3S — до 12.6 В) и делит его на число ячеек, чтобы получить напряжение каждой. Эти значения используются для расчёта процента заряда и предупреждений в QGC.


**Примечание** Значения 3.30 и 4.20 В — пороги мониторинга, подходящие и для LiPo, и для LiHV; это не параметры зарядки. Заряжайте аккумулятор по его типу (для LiHV — до 4.35 В на ячейку, см. [Аккумулятор (АКБ)](/learn/obrik-ros-2/battery-li-po)).


---


## Калибровка делителя напряжения


**Делитель напряжения** — это электрическая схема, которая уменьшает напряжение аккумулятора (например, 12.6 В) до уровня, который может измерить микроконтроллер (обычно 0–3.3 В). Если коэффициент делителя настроен неправильно — PX4 будет показывать неверное напряжение.


### Вариант 1: Калибровка по индикатору напряжения (точный метод)

-

Подключите звуковой индикатор напряжения аккумулятора к балансировочному разъёму — он покажет суммарное напряжение

-

Нажмите кнопку **Calculate** напротив надписи **Voltage Divider**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F40.png&sig=4019849f88efb3b42961ec237228ec88de8ece255d0b9520582f41fcd0f1230a)


-

Введите в открывшееся поле суммарное напряжение со звукового индикатора (например, `11.4`)

-

Нажмите **Close** — QGC сохранит рассчитанный коэффициент


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F41.png&sig=6f7ee155e795b8c01f0fdc3d4e72bbccaadb56af42f82c9c5d1581ce0e961bdd)



### Вариант 2: Усреднённое значение (без индикатора)


Если индикатора нет, установите **Voltage divider = 11** — это среднее проверенное значение для Обрика.


---


## Итоговая проверка


После настройки и всех калибровок перейдите на вкладку **Summary**. Все пункты должны быть отмечены **зелёным маркером**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F42.png&sig=6c6c8aea0377cc5e1c6ff04ecca2d54d079460c1d953fad28b867944285e7f49)



Если какой-то пункт красный — вернитесь к соответствующей вкладке и повторите настройку.


Чеклист перед первым полётом:

- Sensors — все три калибровки выполнены (зелёные)
- Radio — аппаратура управления откалибрована
- Flight Modes — режимы назначены на SB, SA, SD
- Power — параметры аккумулятора настроены
- Summary — всё зелёное
