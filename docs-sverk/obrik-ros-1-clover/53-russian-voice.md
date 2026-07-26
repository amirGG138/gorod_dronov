# Настройка русской озвучки RadioMaster Pocket

> Раздел: Обрик ROS 1 (Clover) · slug: `russian-voice`
> Источник: https://edu.sverk.tech/learn/clover-2/russian-voice

---

# Настройка русской озвучки RadioMaster Pocket

-

Подключите аппаратуру управления к компьютеру через верхний разъём USB-C (находится на верхней грани аппаратуры управления) с помощью USB-кабеля


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0843.png&sig=5fef0ea1b222273a765ae776c987145b42a1240959113a18547bc5192df17538)


-

В появившемся окне на экране аппаратуры управления выберите **USB Storage (SD)**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0783.png&sig=c9d3f4f2ce52cf18d59151ba1605aff92d00f005c4d55b4298045206fd3b6717)


-

Откройте на компьютере папку со скачанным [архивом](https://drive.google.com/drive/folders/13V-xxbfMj9bZtWU3VrE0vCBnuwDvGQ82?usp=drive_link) готовых настроек аппаратуры управления, архив содержит следующие файлы:

|  model00.yml |  Профиль настроек для управления Обриком |
|  radio.yml |  Настройки передатчика (аппаратуры управления) |
|  ru |  Архив русской озвучки |

- Откройте хранилище аппаратуры управления, в папку **MODELS** скопируйте файл *model00.yml*

>

**Caution** Если в этих папках уже есть файлы с такими названиями, удалите их или согласитесь на замену при копировании


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor1.png&sig=9e91159fa939dc10e760ff797d7144dded032ad95d70d39d90318b85b69d9853)


- В папку **RADIO** скопируйте файл *radio.yml*

>

**Caution** Если в этих папках уже есть файлы с такими названиями, удалите их или согласитесь на замену при копировании


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor2.png&sig=3f602cdc912e8748b03e1fea0e9749ff941e2790ff8b77de0ef8eba1e9bdbb2a)


- В папку **SOUNDS** скопируйте папку *ru*

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2Fscreen_monitor3.png&sig=2ac6c41733f7c14889961a99448df8775f824f63d28eb8f244d36ed88fc35214)


- Отключите аппаратуру управления от компьютера

Для применения русской озвучки:

-

Нажмите кнопку **SYS**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763-.png&sig=b5d5566c10b88ec997a135868bd02538fcfc00faea4ee2b4f106618b393bab0d)


-

С помощью кнопки **PAGE>** перейдите в третью (3/7) вкладку **RADIO SETUP**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fhardware_control%2FDSCF0763_1.png&sig=c95d4b9202b7a14d4604325b041f1c2c182aa0fc9255ed5d4478d19d9f9190bb)


-

Пролистайте до **voice language** и выберите **Russian**


### Индикация приемника

|   |  Непрерывный свет |  Подключен к передатчику или включен режим загрузчика |
|   |  Медленное мигание (500 мс вкл/выкл) |  Ожидание соединения с передатчиком |
|   |  Быстрое мигание (25 мс вкл/выкл) |  Режим раздачи Wi-Fi включен |
