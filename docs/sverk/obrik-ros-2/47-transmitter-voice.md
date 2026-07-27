# Русская озвучка RadioMaster Pocket

> Раздел: Обрик ROS 2 · slug: `transmitter-voice`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/transmitter-voice

---

# Русская озвучка RadioMaster Pocket


RadioMaster Pocket — аппаратура управления Обриком, работающий по протоколу ELRS (ExpressLRS). По умолчанию системные сообщения воспроизводятся на английском. Инструкция описывает, как загрузить готовые профили и переключить озвучку на русский язык.


---


## Шаг 1. Скачайте архив с настройками


Скачайте [архив с готовыми настройками](https://www.google.com/url?q=https://drive.google.com/drive/folders/13V-xxbfMj9bZtWU3VrE0vCBnuwDvGQ82?usp%3Ddrive_link&sa=D&source=docs&ust=1773057066587064&usg=AOvVaw2IXGQhfwC7kRUnIrMfr3Ho). Внутри три файла:

|  Файл |  Что содержит |
|  model00.yml |  Профиль настроек для управления Обриком |
|  radio.yml |  Настройки самого передатчика (аппаратуры управления) |
|  ru |  Папка с файлами русской озвучки |


---


## Шаг 2. Подключите аппаратуру управления к компьютеру


Подключите аппаратуру управления к компьютеру через верхний разъём USB-C (разъём на верхней грани).


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0843.png&sig=bc8d642525b98d1830494a3b36082966fb5b31463f6b3c7fe7575972c55e2d50)



На экране аппаратуры управления появится меню. Выберите **USB Storage (SD)**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0783.png&sig=1db4d19c02641b96cd6475ada410b3982a349b113c2f79d0adc3bfe2c1b532a3)



Аппаратура управления появится на компьютере как флешка.


---


## Шаг 3. Скопируйте файлы


Откройте хранилище аппаратуры управления на компьютере.


В папку **MODELS** скопируйте файл `model00.yml`.


>

**Примечание** Если в папке MODELS уже есть файл с таким именем, удалите его или подтвердите замену при копировании.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor1.png&sig=7ff57f7ebf4ad116872e55846de81185c1071d2cb793b94240cdc49de896a02e)



В папку **RADIO** скопируйте файл `radio.yml`.


>

**Примечание** Если в папке RADIO уже есть файл с таким именем, удалите его или подтвердите замену при копировании.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor2.png&sig=ae22c2e7bb26fcd91ac4ab3f94b283669359d8835c01951a9d67158fc27cc9f4)



В папку **SOUNDS** скопируйте папку `ru` целиком.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor3.png&sig=f4207853bee5ec4b62ebcfd4d687d635d564fccb5e501cfac9a19aa891077b0d)



Отключите аппаратуру управления от компьютера.


---


## Шаг 4. Активируйте русскую озвучку


На аппаратуре управления нажмите кнопку **SYS**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763-.png&sig=e67479d5a40faf1801fd9ddc22d278c67567b3d9aa58a17a9e646cf00a6d6941)



С помощью кнопки **PAGE>** перейдите в третью вкладку (3/7) **RADIO SETUP**.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763_1.png&sig=6a98fffab111284e4e68dda28c72d352b70aa44563efa071e1b64384f732189d)



Пролистайте вниз до строки **voice language** и выберите **Russian**.


Готово. Аппаратура управления будет говорить по-русски.


---


## Что означает мигание на приёмнике


Приёмник ELRS стоит на дроне и принимает сигналы от аппаратуры управления. По миганию светодиода на нём можно понять, что происходит:

|   |  Непрерывный свет |  Приёмник подключён к аппаратуре управления, или включён режим загрузчика |
|   |  Медленное мигание (500 мс вкл/выкл) |  Ожидание сигнала от аппаратуры управления |
|   |  Быстрое мигание (25 мс вкл/выкл) |  Режим Wi-Fi включён (для обновления прошивки приёмника) |


Если приёмник медленно мигает, а аппаратура управления включена и рядом, значит они не связаны. Нужно выполнить привязку (binding).
