# Сопряжение аппаратуры управления и приёмника

> Раздел: Обрик ROS 1 (Clover) · slug: `hardware-control`
> Источник: https://edu.sverk.tech/learn/clover-2/hardware-control

---

# Сопряжение аппаратуры управления и приёмника


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fradiomaster_front2.png&sig=07990e7194ba65705ac05dbc99679f2af0d9f349ff2a04cf180e1224d076b0e1)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fradiomaster_back2.png&sig=0220fd63a0e2f26dedb40cdd8ec4ae8ba82938c316caf1ac68cd415b04e90888)



>

**Note** Если вы хотите дополнительно настроить русскую озвучку, читайте статью [Настройка русской озвучки RadioMaster Pocket](/learn/clover-2/russian-voice)


**Binding Phrase** — это общая кодовая фраза, которая связывает передатчик (TX) и приёмник (RX). Они должны содержать одинаковую фразу, чтобы найти друг друга и установить связь.


Сопряжение выполняется через одинаковую **Binding Phrase** на аппаратуре управления (передатчике TX) и Обрике (приёмнике RX).


## Подготовка аппаратуры управления

- Снимите чёрные резиновые накладки с задней стороны аппаратуры управления
- Вставьте АКБ, соблюдая полярность
- Переведите все стики и переключатели в исходное положение:
  - Левый стик — вниз
  - Тумблеры **SB, SC** — от себя
  - Переключатели **SA, SD** — в положение выкл.

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fconsole_position.png&sig=e54f2e0760df845d56b333ee3563ac8ffa99b0a5aed97112e74f4fd179623510)


-

Подключите зарядное устройство через порт USB Type‑C и оставьте подключённым (можно использовать во время полётов)

-

Включите аппаратуру управления — зажмите **кнопку питания** до появления на экране 4-х точек


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0883.png&sig=5da8035b43bc980e1c0a82426df4865249c0107fbebc9e23bd0494b718bf73ae)



>

**Hint** Если при включении на экране появляется предупреждение — перепроверьте положение стиков и тумблеров


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0887.png&sig=849150de96cbccf964a1121a1ae01bc6e1f6f8acf0e11dfc475b2b128eaa9e54)



### Настройка передатчика (TX)

-

Нажмите кнопку **SYS**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763-.png&sig=b5d5566c10b88ec997a135868bd02538fcfc00faea4ee2b4f106618b393bab0d)


-

Для перехода в меню **ExpressLRS** нажмите на колесо прокрутки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0789.png&sig=6e3fe3e18e84aadb53634dc7c7320ce0bd69eacc761015bf311f53a2416ed599)



>

**Caution** Чтобы выйти из меню ExpressLRS, нужно зажать кнопку **RTN**

-

Выберите пункт **Wifi Connectivity**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0791.png&sig=042e0b91dd9bc5b9294d08de79b1df93630e6ffb3ac8eed607bc9a743f7125b9)


-

Выберите пункт **Enable Wifi**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0793.png&sig=97c35661cb12252d6c6d63268cc65d60f0fec6e50443d747d8d8cd4a60b15487)


-

Подключитесь к сети Wi-Fi **ExpressLRS TX** на своём устройстве (телефон, ноутбук, ПК) с паролем `expresslrs`


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor4.png&sig=d34e1a1896dd2c3a62538a70d5e2b69edc88040ed928a4c2712df289d968ae20)


-

Перейдите на адрес `10.0.0.1` в браузере


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor5.png&sig=e356ab6d2a03637535ebc3ea71efdc7fcea4a71b9b2f1cf20ba05d4887f93e61)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor6.png&sig=0cd6fb39245ce45d735bb1dacb153a988f5675d1db36bcbefb0708aee5e34ff7)



>

**Note** В шапке страницы можно узнать название передатчика TX (первая строка) и версию прошивки (вторая строка). Если версия прошивки ниже [3.3.1](https://drive.google.com/file/d/1OUVBTHfTgQ36D4WrX5AeVcz1UwrWtQMS/view?usp=drive_link) — обновите её через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

-

В поле **Binding Phrase** введите уникальную фразу и нажмите **SAVE**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor7.png&sig=155cebefcf963b7456e8009869b91f4731b16f5af8d08756e4f8f42d069758eb)



>

**Note** По этой фразе приёмник будет находить передатчик. Используйте действительно уникальную фразу, чтобы избежать случайного подключения к чужому оборудованию. Никаких дополнительных действий для сопряжения не требуется — всё происходит автоматически.

-

В открывшемся окне нажмите **REBOOT** для перезагрузки передатчика


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor8.png&sig=302d2970e7f2b578cd448c27f24687a4395fc5ef7467065bf2519452a7460ef0)



### Настройка приёмника (RX)

- Включите Обрик

>

**Caution** Если включаете Обрик с помощью [АКБ](/learn/clover-2/akb) — убедитесь, что воздушные винты сняты

-

Подождите 60 секунд — после этого приёмник перейдёт в режим раздачи Wi-Fi

-

Подключитесь к сети Wi-Fi **ExpressLRS RX** на своём устройстве (телефон, ноутбук, ПК) с паролем `expresslrs`


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor4.1.png&sig=7db03785282f40e9dc80921d2baa805d3db7a4cb68f5fa5272419a60bda84046)


-

Перейдите на адрес `10.0.0.1` в браузере


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor5.png&sig=e356ab6d2a03637535ebc3ea71efdc7fcea4a71b9b2f1cf20ba05d4887f93e61)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor6_2.png&sig=9ee36fc1c7e1296b2b0b973a64cf1b051f9d8a9a5ccad5a4f1183921ae09cbbe)



>

**Note** В шапке страницы можно узнать название приёмника RX (первая строка) и версию прошивки (вторая строка). Если версия прошивки ниже [3.3.1](https://drive.google.com/file/d/1OUVBTHfTgQ36D4WrX5AeVcz1UwrWtQMS/view?usp=drive_link) — обновите её через [веб-прошивальщик](https://expresslrs.github.io/web-flasher/).

-

В поле **Binding Phrase** введите **точно такую же** фразу, как и в передатчике, и нажмите **SAVE**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor7_2.png&sig=8ec9aae4391426c38acf3265c19b09ab272423346bb3bce411b73c5853b7e136)


-

В открывшемся окне нажмите **REBOOT** для перезагрузки приёмника


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor8.png&sig=302d2970e7f2b578cd448c27f24687a4395fc5ef7467065bf2519452a7460ef0)


-

После успешного сопряжения аппаратура управления коротко вибрирует, а светодиод на приёмнике перестаёт мигать и горит постоянно

-

Проверить сопряжение можно на главном экране аппаратуры — появится индикация связи и звуковое оповещение


>

**Hint** Если связи нет — убедитесь, что **Binding Phrase** на передатчике (TX) и приёмнике (RX) совпадает полностью, включая регистр букв


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0797.png&sig=67a306af6030769f09c714f9d2b7053a3019023bb9c3047c0b9c4cb134e46f48)



>

**Caution** Если связь есть, но Обрик не воспринимает команды с аппаратуры управления — в меню **ExpressLRS** измените параметр **Model Match** с положения **off** в положение **on**, затем обратно в **off**
