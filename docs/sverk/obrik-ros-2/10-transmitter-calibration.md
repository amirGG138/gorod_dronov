# Калибровка аппаратуры управления и настройка полётных режимов

> Раздел: Обрик ROS 2 · slug: `transmitter-calibration`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/transmitter-calibration

---

# Калибровка аппаратуры управления и настройка полётных режимов


Калибровка аппаратуры управления RadioMaster Pocket в QGC настраивает соответствие стиков командам дрона. Этот раздел также описывает назначение полётных режимов на переключатели.


---


>

**Внимание** Отключите аккумулятор от Обрика (питание только через USB) и снимите пропеллеры с моторов.


---


## Каналы управления


<p>
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fradiomaster_front2.png&sig=87d7bbb0c63a7b907253e8d8e1aa929387f658e71fcc333ff390dd4e62702486)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fradiomaster_back2.png&sig=17071d517a7d9897c848d47d6e53f6f7577309f70bd1d11506d0cf36151f9732)
 </p>


Аппаратура управления RadioMaster Pocket отправляет на дрон данные по **10 каналам** — по каждому каналу идёт своё значение. Каждый канал соответствует одному органу управления:

|  Канал |  Орган управления |
|  1 |  Roll (крен) |
|  2 |  Pitch (тангаж) |
|  3 |  Throttle (газ) |
|  4 |  Yaw (рысканье) |
|  5 |  SA (запуск моторов) |
|  6 |  SB (режимы полёта) |
|  7 |  SC |
|  8 |  SD (Kill Switch) |
|  9 |  SE |
|  10 |  S1 (крутилка) |

- **Roll** (крен) — наклон влево/вправо → правый стик, горизонтально
- **Pitch** (тангаж) — наклон вперёд/назад → правый стик, вертикально
- **Throttle** (газ) — скорость моторов → левый стик, вертикально
- **Yaw** (рыскание) — поворот вокруг вертикальной оси → левый стик, горизонтально
- **SA–SD** — переключатели для режимов, запуска моторов и аварийного отключения

---


## Калибровка аппаратуры управления


Откройте вкладку **Radio** в Vehicle Configuration.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F28.png&sig=559a0a9197916810c45bc5013009bd759134954960d30b5c16a1b7e286583a38)



>

**Подсказка** Перемещая стики и переключатели, вы можете в реальном времени видеть, как движутся полоски каналов на экране. Это полезно для проверки связи.


**Примечание** Если аппаратура управления показывает связь с Обриком, но QGC не видит движений стиков — в меню SYS аппаратуры управления, раздел ExpressLRS, измените **Model Match** с **off** на **on**, затем обратно на **off**.


### Назначение калибровки аппаратуры управления


Каждый стик немного отличается: один может ходить чуть дальше в одну сторону, у другого центр смещён. Калибровка сообщает PX4 точные минимальные, центральные и максимальные значения каждого стика и переключателя. Без этого дрон может «думать», что вы держите стик не в центре, когда он на самом деле по центру, — и будет дрейфовать в воздухе без команды.


### Калибровка

- Выставите **Mode 2** (стандартный режим: газ слева, крен/тангаж справа)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F29.png&sig=aa48cd8ee0de600898c08e0caa3fd65331aa0eed36ab97cf1857da71bf5fd430)


- Нажмите кнопку **Calibrate**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F30.png&sig=2e8ad9f229f2702535a4130a0a5ba21d0239508912111aacf5700936e2337d83)


-

Установите все триммеры в ноль — переведите **оба стика в центральное положение**


>

**Подсказка** Правый стик возвращается в центр автоматически. Для левого стика (Throttle) совместите риски на стике с рисками на корпусе аппаратуры управления — это и есть центр.

-

Нажмите **Ok**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F31.png&sig=22b95c42affa414a78ed42d83a120a735b4fd0b386ffc73bf8430e15c77933b4)


- Переведите **левый стик (Throttle) в нижнее положение**, как показано в правом окне, и нажмите **Next**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F32.png&sig=b137aaab0324765eafb2390093513971e28203cf6861064c143eeb9288984b5f)


-

Двигайте стиками вслед за анимацией на экране


>

**Подсказка** Чем точнее вы следуете анимации — тем лучше калибровка. Доводите стики до упора в каждом направлении.

-

Когда появится надпись **“Move all transmitter switches and/or dials back and forth to their extreme positions”** — переключите все тумблеры **SA, SB, SC, SD, SE, S1** в их крайние положения (туда и обратно)

-

Нажмите **Next**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F33.png&sig=1134cf8137bacfcf203a4992cb3766f3290d68086dd5f6b7423a7463144b0b2a)


- Когда появится **“All settings have been captured. Click Next to write the new parameters to your board”** — нажмите **Next**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F34.png&sig=6a857e6fdedc8844e67149555142ce905130bc193bfb251fc4659740cb3a7982)



Калибровка завершена.


---


## Настройка полётных режимов


**Что такое полётные режимы?** PX4 умеет летать по-разному в зависимости от режима:

|  Режим |  Что делает |
|  **Stabilized** (Стабилизированный) |  Дрон автоматически держит горизонтальное положение. Вы управляете наклоном, высоту держите сам газом |
|  **Altitude** (По высоте) |  Дрон держит горизонт и автоматически удерживает высоту. Вы управляете только горизонтальным движением |
|  **Position** (По позиции) |  Дрон держит горизонт, высоту и позицию. При отпускании стиков зависает на месте |


Откройте вкладку **Flight Modes** в Vehicle Configuration.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F35.png&sig=316db4f78f7c66feca7b637ee0e839e9f6218076d72bfd1e146afdbc3ed42b45)



### Настройка режимов на переключатель SB


Тумблер **SB** имеет 3 положения - 3 режима полёта.


В разделе **Flight Mode Settings**:

- **Mode Channel** → установите **Channel 6** (это тумблер SB)
- **Flight Mode 1** → **Stabilized** (SB сверху — первое положение)
- **Flight Mode 4** → **Position** (SB посередине — второе положение)
- **Flight Mode 6** → **Altitude** (SB снизу — третье положение)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F36.png&sig=29019d330dbd56e94b5c23d9b54f88f4d3f77f88fd0ac27e5fdde3971d28a769)



>

**Подсказка** Жёлтым подсвечивается тот режим, который сейчас активен согласно положению тумблера SB. Переключите SB на аппаратуре управления и посмотрите, как меняется подсветка.


### Настройка переключателей запуска моторов и аварийного отключения


**Запуск моторов (arming)** — подача питания на моторы. Пока моторы не запущены, они не закрутятся даже при газе. **Kill switch (аварийное отключение)** — мгновенное отключение моторов. Используется только в экстренных ситуациях.


В разделе **Switch Settings**:

- **Arm switch channel** → **Channel 5** (переключатель **SA**)
- **Emergency Kill switch channel** → **Channel 8** (переключатель **SD**)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F37.png&sig=0c22cfa8dd43cfefe6963b72345a1639212008b0291f535ef7586f16fe518f86)



>

**Внимание** Kill switch — экстренная кнопка. Нажимайте только если дрон вышел из-под контроля. При нажатии моторы мгновенно останавливаются — дрон упадёт.
