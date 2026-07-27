# Сопряжение пульта с микродроном

> Раздел: Микродрон (Whoop) · slug: `setup-controller`
> Источник: https://edu.sverk.tech/learn/whoop/setup-controller

---

# Сопряжение пульта с микродроном


>

**Примечание** Если хотите настроить русскую озвучку и загрузить профиль настроек — см. [Настройка озвучки RadioMaster Pocket](/learn/whoop/setup-controller-voice).


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage12.png&sig=8e372d2e6a1bc5de8a5bc3a4ebd887752ce242ccf01d85e5a2c72bb3c8e7e207)



**Binding Phrase** — это общая кодовая фраза, которая связывает передатчик (TX) и приёмник (RX). Они должны содержать одинаковую фразу, чтобы найти друг друга и установить связь.


Сопряжение выполняется через одинаковую **Binding Phrase** на аппаратуре управления (передатчике TX) и микродроне (приёмнике RX).


## Индикация приёмника

|   |  Режим |  Описание |
|
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage3.gif&sig=711de3b9610df63eb229b182c0b7e4888cd81df3887194d01619bcc82ba41bd8)
 |  Непрерывный свет |  Подключён к передатчику или включён режим загрузчика |
|
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage22.gif&sig=d3b7a957279c648cfd9b404f94ef60d8cf8084560e686d3e141cd3c1968fc31c)
 |  Медленное мигание (500 мс) |  Ожидание соединения с передатчиком |
|
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage2.gif&sig=8498928401b67de9c680e91ad875f26fc1c69091586f2810142abe61ebb29b69)
 |  Быстрое мигание (25 мс) |  Режим раздачи Wi-Fi включён |


## Подготовка аппаратуры управления

- Снимите чёрные резиновые накладки с задней стороны аппаратуры управления.
- Вставьте [АКБ](/learn/whoop/kb-battery), соблюдая полярность.
- Переведите все стики и переключатели в исходное положение:
  - Левый стик — вниз.
  - Тумблеры **SB**, **SC** — от себя.
  - Переключатели **SA**, **SD** — в положение выкл.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage25.png&sig=7d49a3deb370be8336f6f4dcb85e2a9cadab1614b75fc51de047de2767186b90)


-

Подключите зарядное устройство через порт USB Type‑C и оставьте подключённым (можно использовать во время полётов).

-

Включите аппаратуру управления — зажмите **кнопку питания** до появления на экране 4-х точек.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage26.jpg&sig=13e882d8cbe4efdf842e5df9a71d068520ce2a8eae4cf6996987f727810bd70f)



>

**Подсказка** Если при включении на экране появляется предупреждение — перепроверьте положение стиков и тумблеров.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage6.png&sig=a2629083c90a7f19025829ed1da05a69a482fb4abbf3a1e189a0d659fc0e8fbe)



## Настройка передатчика (TX)

- Нажмите кнопку **SYS**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage15.png&sig=211d030065825df2d26f88168b99021a75203bae999107929ed5d916ef41756d)


- Для перехода в меню **ExpressLRS** нажмите на колесо прокрутки.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage8.png&sig=eb6934bd2f5f22e56dc0a9fa6951cb96a39e8e8aa72911062c73238d7300e7e6)



>

**Внимание** Чтобы выйти из меню ExpressLRS, нужно зажать кнопку **RTN**.

- Выберите пункт **Wi-Fi Connectivity**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage10.png&sig=82eeb0f16637bc367c053d973eb77ebbb03f3758f4a7615de93a33b2cb5ef2d3)


- Выберите пункт **Enable Wi-Fi**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage13.png&sig=6972dc84a5deaa028152d743bc7c65973440170d1c4fcb4cd5b70c343eaea673)


- Подключитесь к сети Wi-Fi **ExpressLRS TX** на своём устройстве (телефон, ноутбук, компьютер) с паролем `expresslrs`.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage16.png&sig=c4b87df43c79914e237f06946247fe6d0424e184b399fedfc1a894cab3594e21)


- Перейдите на адрес `10.0.0.1` в браузере.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage18.png&sig=1aaa7a9abc9457fd73781a51816e9695d8c2ea281d80f3c262fe515ebcf4c1f6)



![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage17.png&sig=7bdf53c584194113681194656591849fb6c2f20a5e54b8f473088de534392870)



>

**Примечание** В шапке страницы можно узнать название передатчика TX (первая строка) и версию прошивки (вторая строка). Если версия прошивки ниже 3.3.1 — обновите её через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

- В поле **Binding Phrase** введите уникальную фразу и нажмите **SAVE**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage7.png&sig=3fa11c41e9d95d910b5c0059ab09b154526a0a3c3c9a20f3881aebbd07fe67a8)



>

**Примечание** По этой фразе приёмник будет находить передатчик. Используйте действительно уникальную фразу, чтобы избежать случайного подключения к чужому оборудованию. Никаких дополнительных действий для сопряжения не требуется — всё происходит автоматически.

- В открывшемся окне нажмите **REBOOT** для перезагрузки передатчика.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage4.png&sig=a13814d755edda80f2ee09e8ba8a9b83f36284c95285cb7eaa750243d8c04de4)



## Настройка приёмника (RX)

- Включите микродрон.

>

**Внимание** Если включаете микродрон с помощью АКБ — убедитесь, что воздушные винты сняты.

- Подождите 60 секунд — после этого приёмник перейдёт в режим раздачи Wi-Fi.
- Подключитесь к сети Wi-Fi **ExpressLRS RX** на своём устройстве с паролем `expresslrs`.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage11.png&sig=76fed28bcbf3e9f751cf46d355d1e4a26baa942bf898b7359cb5d7a059ffa39d)


- Перейдите на адрес `10.0.0.1` в браузере.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage18.png&sig=1aaa7a9abc9457fd73781a51816e9695d8c2ea281d80f3c262fe515ebcf4c1f6)



![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage20.png&sig=3f30cf435ebe932d99047ee15fd686643ab263e8c16f262b02a66b4e8c2716be)



>

**Примечание** В шапке страницы можно узнать название приёмника RX (первая строка) и версию прошивки (вторая строка). Если версия прошивки ниже 3.3.1 — обновите её через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

- В поле **Binding Phrase** введите **точно такую же** фразу, как и в передатчике, и нажмите **SAVE**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage23.png&sig=e6a6a0bcbc3dfe1efc8fe2a3929b0569154babea48509ba3a3051f4432c7c050)


- В открывшемся окне нажмите **REBOOT** для перезагрузки приёмника.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage9.png&sig=9f240b4763b6914955f179b14511e96e2b385134275f8b084ae2ffc3b88bcfdd)


- После успешного сопряжения аппаратура управления коротко вибрирует, а светодиод на приёмнике перестанет мигать и будет гореть постоянно.
- Проверить сопряжение можно на главном экране аппаратуры управления — появится индикация связи и звуковое оповещение.

>

**Подсказка** Если связи нет — убедитесь, что **Binding Phrase** на передатчике (TX) и приёмнике (RX) совпадает полностью, включая регистр букв.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-controller%2Fimage21.png&sig=3d8ecaf44174f306940a5179e6a3469f15ca2a4ee1ccb1fa4e10e3ed9866e90d)



>

**Внимание** Если связь есть, но микродрон не воспринимает команды с аппаратуры управления — в меню **ExpressLRS** измените параметр **Model Match** с положения **off** в положение **on**, затем обратно в **off**.
