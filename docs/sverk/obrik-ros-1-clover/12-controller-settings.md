# Калибровка аппаратуры управления

> Раздел: Обрик ROS 1 (Clover) · slug: `controller-settings`
> Источник: https://edu.sverk.tech/learn/clover-2/controller-settings

---

# Калибровка аппаратуры управления


>

**Caution** Перед подключением и калибровкой аппаратуры управления убедитесь, что:

- К Обрику не подключено внешнее питание от АКБ;
- Пропеллеры не установлены на моторах.

Во вкладке **Radio** показывается то, как Обрик воспринимает положения элементов аппаратуры управления и их соотношение с каналами (с 1 по 16).


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F28.png&sig=f63aecbc7bd3dcaaa4ae45cc42da78aaeed1b1cac7f67871e8e0b508f612dacc)



RadioMaster Pocket (аппаратура управления Обрика) имеет 10 каналов со следующим соотношением:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2Fradiomaster_channels.png&sig=06f89504280b3beb3c553753075787d39457f2d01db2ed3601b7040c97438bfa)



>

**Note** Перемещая стики и изменяя положения переключателей, можно в реальном времени видеть их соотношение с каналами.


Если на аппаратуре управления есть индикация связи с Обриком, но QGC не воспринимает движения стиков — в меню **SYS** → **ExpressLRS** измените параметр **Model Match** с положения **off** в положение **on**, затем обратно в **off**.


## Калибровка

-

Выставьте **Mode 2**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F29.png&sig=b4c8264d31fd4d6f2864c0c41ff2c5eaa3ceb062f91624260cb8c3329083af40)


-

Нажмите кнопку **Calibrate**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F30.png&sig=b5bdf4b3ba0866fdd495424b533454642f5bc94b8c63c60e6bfec76db3ea542e)


-

Установите триммеры **Throttle, Yaw, Pitch, Roll** в 0 — переместите оба стика в центральное положение


>

**Hint** Правый стик центруется автоматически по обеим осям. Чтобы установить левый стик (Throttle) в центральное положение — совместите риски на стике с рисками на корпусе.

-

Нажмите **Ok**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F31.png&sig=97e27cf57aede3243fac1e201bab92c9528fe0666db2a621a60eaffc2d5afd8c)


-

Переведите левый стик (Throttle) в нижнее положение, как показано в окне справа, и нажмите **Next**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F32.png&sig=04af013dcd7a15d4dc311ac2978235d2670e3c13921ee3da1826a49a3743392f)


-

Повторяйте движения стиками вслед за анимацией, читайте подсказки


>

**Hint** Чем точнее вы следуете анимации, тем лучше будет произведена калибровка.

-

При появлении надписи *“Move all transmitter switches and/or dials back and forth to their extreme positions”* — переключите **SA, SB, SC, SD, SE, S1** в их крайние положения

-

Нажмите **Next**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F33.png&sig=74ff8e3e1abe7bc18a27a99d3d73cc527791c799da3f0483b4d627888ed0b45a)


-

При появлении надписи *“All settings have been captured. Click Next to write the new parameters to your board”* — нажмите **Next**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F34.png&sig=d07d33d41a9d0354f9236c95133df9d1c5a055a6e7ff174c873c2f497afba33a)



## Настройка полётных режимов


Во вкладке **Flight Modes** настраивается соотношение позиций переключателя **SB** с режимами полёта, а также **Arm** (включение двигателей) и **Kill switch** (экстренное отключение двигателей).


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F35.png&sig=66a115ec2642a22a135813f89ccbe993abafe894168067dedb8b310115fb7060)



Настройка полётных режимов (поле **Flight Mode Settings**):

-

**Mode Channel** — установите **Channel 6** (переключатель SB)

-

**Flight Mode 1** — установите **Stabilized** (полёт с автоматическим удержанием горизонтального положения)

-

**Flight Mode 4** — установите **Position** (полёт с автоматическим удержанием позиции)

-

**Flight Mode 6** — установите **Altitude** (полёт с автоматическим удержанием высоты)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F36.png&sig=4638932bc9982d1ac8c3b775772b9671105abc9e9db3014256c1f18df326d7a9)



>

**Caution** Жёлтым подсвечивается режим (**Flight Mode**), который соответствует текущей позиции переключателя **SB** на аппаратуре управления.


Настройка переключателей (поле **Switch Settings**):

-

**Arm switch channel** — установите **Channel 5** (переключатель **SA**)

-

**Emergency Kill switch channel** — установите **Channel 8** (переключатель **SD**)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_flight_controller%2F37.png&sig=3594cd8d4ac25d04e418ed2ab7ded328bf80154c15d1f159f75b6b9517bc371d)
