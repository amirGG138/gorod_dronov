# Калибровка аппаратуры управления

> Раздел: Микродрон (Whoop) · slug: `setup-rc`
> Источник: https://edu.sverk.tech/learn/whoop/setup-rc

---

# Калибровка аппаратуры управления


>

**Внимание** Перед калибровкой убедитесь, что:

- К микродрону не подключено питание от [АКБ](/learn/whoop/kb-battery);
- Пропеллеры не установлены на моторах.

Во вкладке **Radio** отображается то, как микродрон воспринимает положения элементов аппаратуры управления и их соответствие каналам (с 1 по 16).


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage1.png&sig=d0af7576d9aaf8c2203eba55192780cb82ffad5a68e8de5fdc2e4b69865c90df)



RadioMaster Pocket имеет 10 каналов:

|  Канал |  Элемент |  Канал |  Элемент |
|  1 |  Roll |  6 |  SB |
|  2 |  Pitch |  7 |  SC |
|  3 |  Throttle |  8 |  SD |
|  4 |  Yaw |  9 |  SE |
|  5 |  SA |  10 |  S1 |


>

**Примечание** Перемещая стики и переключатели можно в реальном времени увидеть их соответствие каналам.


Если аппаратура показывает связь с микродроном, но QGC не воспринимает движения стиков — в меню **SYS → ExpressLRS** измените параметр **Model Match** с **off** в **on** и обратно в **off**.


## Калибровка

- Установите **Mode 2**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage2.png&sig=0181dd08392bc742f7f38a55419364831e3ac6b92c872840fa9823ec420e730a)


- Нажмите кнопку **Calibrate**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage3.png&sig=e22f4aea1422a939af840d60ae9b6f574ddd62dde3056bb96f40acedce5dea97)


- Установите триммеры **Throttle, Yaw, Pitch, Roll в 0** — переместите оба стика в центральное положение.

>

**Подсказка** Правый стик центруется автоматически. Чтобы выставить левый стик по оси Throttle в центр — совместите риски на стике с рисками на корпусе.

- Нажмите **Ok**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage4.png&sig=520bde8bcbdce5eb9651beb10301643aa4f82cce65905b9d9c3bb3144a83f400)


- Переведите левый стик (Throttle) в нижнее положение и нажмите **Next**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage5.png&sig=c8bd8b890af34124f4d8a6dc133ab241fabbbc427a9c00a1683ec016bcc28da4)


- Повторяйте движения стиками вслед за анимацией.

>

**Подсказка** Чем точнее следовать анимации, тем точнее будет калибровка.

-

При появлении надписи *«Move all transmitter switches and/or dials back and forth to their extreme positions»* переключите **SA, SB, SC, SD, SE, SI** в крайние положения.

-

Нажмите **Next**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage6.png&sig=1a33154f1bc8a0f5ca20cc9495654e503580b47c96ccb9e17514cd39fe7b9d2b)


- При появлении надписи *«All settings have been captured. Click Next to write the new parameters to your board»* нажмите **Next**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage7.png&sig=86e142ecf16e13c6d909d89df1f0b18aec9e33668d12ffab1ad08323b7cc2f51)



## Настройка полётных режимов


Во вкладке **Flight Modes** настраивается соответствие позиций переключателя **SB** режимам полёта, а также Arm и Kill Switch.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage8.png&sig=b1e9ca71da565fc1e9adab79e43b8f8e8f83a07655375c085135118f73e46f81)



Настройка полётных режимов (поле **Flight Mode Settings**):

- **Mode Channel** → **Channel 6** (переключатель SB)
- **Flight Mode 1** → **Stabilized**
- **Flight Mode 4** → **[Position](/learn/whoop/manual-flight-position)**
- **Flight Mode 6** → **Altitude**

>

**Внимание** Жёлтым подсвечивается режим, соответствующий текущей позиции переключателя **SB**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage9.png&sig=33231724272682a9a12a1e7ebcde9b5252d8548bc2f84457e96a44e17e90d768)



Настройка переключателей (поле **Switch Settings**):

- **Arm switch channel** → **Channel 5** (переключатель **SA**)
- **Emergency Kill switch channel** → **Channel 8** (переключатель **SD**)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-rc%2Fimage10.png&sig=a72f33d6d012ce7e465edb23c20e356858a151f8815c9994fba2b539bad21f8c)
