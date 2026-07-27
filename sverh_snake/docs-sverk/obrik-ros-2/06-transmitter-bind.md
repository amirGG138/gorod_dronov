# Настройка аппаратуры управления

> Раздел: Обрик ROS 2 · slug: `transmitter-bind`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/transmitter-bind

---

# Настройка аппаратуры управления


Аппаратура управления RadioMaster Pocket связывается с Обриком по радиоканалу.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fradiomaster_front2.png&sig=87d7bbb0c63a7b907253e8d8e1aa929387f658e71fcc333ff390dd4e62702486)



>

**Примечание** Чтобы загрузить профиль настроек и активировать русскую озвучку — читайте статью [Русская озвучка RadioMaster Pocket](/learn/obrik-ros-2/transmitter-voice)


---


## Как работает радиосвязь между аппаратурой управления и дроном


Аппаратура управления и дрон общаются по радиоканалу — похоже на то, как рация связывается с другой ракцией. Для этого используется протокол **ELRS (ExpressLRS)** — современный быстрый и надёжный протокол для управления дронами.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fradio-link.svg&sig=255a2930d95a17b44afb51f7afc3d21035a87acde17d99e29812f26c1ce89daf)



Чтобы аппаратура управления и приёмник «нашли» друг друга среди множества других дронов, используется **Binding Phrase** — общая секретная фраза. Связаться между собой могут только устройства с одинаковой фразой.


>

**Примечание** Binding Phrase — уникальная фраза, которая связывает именно ваш передатчик (TX, аппаратура управления) с именно вашим приёмником (RX, дрон). Они должны содержать одинаковую фразу, чтобы найти друг друга в эфире.


---


## Подготовка аппаратуры управления

-

Снимите чёрные резиновые накладки с задней стороны аппаратуры управления

-

Вставьте АКБ, соблюдая полярность (+ к +, − к −)

-

Переведите все стики и переключатели в исходное (безопасное) положение:

  - **Левый стик** — вниз (газ на нуле)
  - **Тумблеры SB, SC** — от себя (нижнее положение)
  - **Переключатели SA, SD** — в положение выкл.

>

**Внимание** При включении аппаратура управления проверяет положение органов управления. Если стик газа (Throttle) не внизу — аппаратура управления выдаст предупреждение: при случайном включении дрон может резко взлететь.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fconsole_position.png&sig=54fee4b448642837cd184f922170e76b88f9f509156aa7df9f3a5f8156d05cb9)


- Подключите зарядное устройство через порт USB Type‑C (можно использовать во время полётов)
- Включите аппаратуру управления — зажмите **кнопку питания** до появления на экране 4-х точек

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0883.png&sig=e789541d7e106480d1ac5caa8efd48ecfb52e5c5e1a6c3e522ea624513a6b866)



>

**Подсказка** Если при включении появляется предупреждение — перепроверьте положение стиков и тумблеров


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0887.png&sig=baeea2246748c0851552d320de1ed8cb0c74906e8aacec2262918c14445b5051)



---


## Настройка передатчика (TX) — аппаратуры управления


Здесь Binding Phrase устанавливается на аппаратуре управления (передатчике).

- Нажмите кнопку **SYS**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763-.png&sig=e67479d5a40faf1801fd9ddc22d278c67567b3d9aa58a17a9e646cf00a6d6941)


- Перейдите в меню **ExpressLRS**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0789.png&sig=f60971eaeae36ed17be1102c830b82f678b1ef4793206b7d7540d6d3601be7f1)



>

**Внимание** Чтобы выйти из меню ExpressLRS, нужно зажать кнопку **RTN** (не просто нажать, а именно зажать)

- Выберите пункт **Wifi Connectivity**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0791.png&sig=e040a7330e3705e718a3b4f7892b5cf26df577cf6548cf5aef06e7d9419925bd)


- Выберите пункт **Enable Wifi** — аппаратура управления начнёт раздавать свою Wi-Fi сеть

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0793.png&sig=af785215947f4a5cc9963f73542943040f8adda61792904466efd37f820cf101)


- Подключитесь к сети Wi-Fi **ExpressLRS TX** на своём устройстве (телефон, ноутбук или компьютер) с паролем `expresslrs`

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor4.png&sig=734bdeec9e5ac4a34dfd14f0049c9b7da0ee6c9b841650b3fb770dfb1ad719e4)


- Откройте браузер и перейдите на адрес `10.0.0.1`

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor5.png&sig=36175cd465693107eeb08e026050042046035a8aa2911dc0862d946cbdc5e154)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor6.png&sig=eca41269618a1d8097c7c55e82846f6d826d8f876723734e40cf21b52e63822b)



>

**Примечание** В шапке страницы можно узнать название передатчика TX (первая строка) и версию прошивки (вторая строка). Если версия прошивки ниже [3.3.1](https://drive.google.com/file/d/1OUVBTHfTgQ36D4WrX5AeVcz1UwrWtQMS/view?usp=drive_link) — обновите её через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

- В поле **Binding Phrase** введите свою уникальную фразу и нажмите **SAVE**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor7.png&sig=f41e3c167aefefa5acc4849c6cf7d2a954d1d1f2a936ba923596d063585f24b0)



>

**Внимание** Придумайте действительно уникальную фразу — например, сочетание вашего имени и числа: `vasya_drone_42`. Это нужно, чтобы ваша аппаратура управления случайно не подключилась к чужому дрону. После сохранения дополнительных действий не нужно — связь установится автоматически.

- В открывшемся окне нажмите **REBOOT** для перезагрузки передатчика

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor8.png&sig=dbbb8d4af61108b18c00d49e4286adea5671152cea6c56c7c9571c601083aa9e)



---


## Настройка приёмника (RX) — модуля на дроне


Теперь **та же самая** Binding Phrase устанавливается на приёмнике Обрика.

-

Включите Обрик


>

**Внимание** Если включаете Обрик с помощью [АКБ](/learn/obrik-ros-2/battery-li-po) — убедитесь, что воздушные винты сняты

-

Подождите 60 секунд — после этого приёмник перейдёт в режим раздачи Wi-Fi

-

Подключитесь к сети Wi-Fi **ExpressLRS RX** на своём устройстве с паролем `expresslrs`


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor4.1.png&sig=86be93d59c863e2a83517918a6f04e7daebaa5c1e941156c63b7f2ca7cbdb156)


- Перейдите на адрес `10.0.0.1` в браузере

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor5.png&sig=36175cd465693107eeb08e026050042046035a8aa2911dc0862d946cbdc5e154)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor6_2.png&sig=8c06e5b64cc59eefb3891bde6100829519fed5910d506f8db944f8cacdeb15fd)



>

**Примечание** В шапке страницы — название приёмника RX и версия прошивки. Если версия ниже [3.3.1](https://drive.google.com/file/d/1OUVBTHfTgQ36D4WrX5AeVcz1UwrWtQMS/view?usp=drive_link) — обновите через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

- В поле **Binding Phrase** введите **точно такую же** фразу, как вводили в передатчике (с учётом регистра букв), и нажмите **SAVE**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor7_2.png&sig=44186205745e96be0f66a23c1d746b9372adae42565bfa411bb87ebdc9fd132b)


- В открывшемся окне нажмите **REBOOT** для перезагрузки приёмника

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor8.png&sig=dbbb8d4af61108b18c00d49e4286adea5671152cea6c56c7c9571c601083aa9e)



---


## Проверка связи


После перезагрузки:

- Аппаратура управления **коротко завибрирует** — это знак успешного сопряжения
- **Светодиод на приёмнике** перестанет мигать и начнёт гореть постоянно
- На **главном экране аппаратуры управления** появится индикация связи и прозвучит оповещение

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0797.png&sig=c096c91714bbf135a766dc47910dc7e0c72283b59aaf358e9c656bba4587816c)



>

**Подсказка** Если связь не устанавливается, убедитесь, что Binding Phrase на передатчике (TX) и приёмнике (RX) совпадает **полностью** — каждая буква, каждый символ, включая регистр (заглавные/строчные буквы различаются).


>

**Подсказка** Если аппаратура управления видит Обрик, но QGC не реагирует на движения стиков — в меню **ExpressLRS** на аппаратуре управления измените параметр **Model Match** с положения **off** в положение **on**, а затем обратно в **off**. Это сбрасывает «привязку к модели» и помогает в большинстве случаев.
