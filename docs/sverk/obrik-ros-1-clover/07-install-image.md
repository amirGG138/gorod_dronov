# Установка образа на бортовой компьютер

> Раздел: Обрик ROS 1 (Clover) · slug: `install-image`
> Источник: https://edu.sverk.tech/learn/clover-2/install-image

---

# Установка образа на бортовой компьютер


Установка образа позволяет подключаться к полётному контроллеру по Wi-Fi и программировать автономные полёты.


## Подготовка


Убедитесь, что выполнен раздел [Настройка](/learn/clover-2/preinstallation) — образ и Balena Etcher уже скачаны.


Установите MicroSD-карту в компьютер (используйте адаптер при необходимости).


## Запись образа с помощью Balena Etcher

-

Запустите **Balena Etcher**. Нажмите **Flash from file** и выберите скачанный архив образа


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F1.png&sig=15a1b2a707aee9024c8692d94bdc5841820b4c0db7defa9cbce7761bd578d74c)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F2.png&sig=bf1b67aba73184bd8ecbeae71ced2f5b3a09f35719029775e875af7573d69c48)


-

Нажмите **Select target**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F3.png&sig=e9b6834bcca5167921d2f0660376c3ddef6c29c184027e2e8aebae1c80c7e3c6)



>

**Caution** Убедитесь, что вы выбрали корректную SD-карту. Неправильный выбор носителя может привести к удалению операционной системы и потере всех данных на выбранном устройстве.

-

Выберите SD-карту в списке подключённых устройств и нажмите **Select 1**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F4.png&sig=3bc6e0d1fabeba9c2e824c9babcfd941d5ae671feac4b7851098ed1630f8f3de)


-

Нажмите **Flash!**. Процесс записи и проверки может занять несколько минут


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F5.png&sig=201500900aebe98dc9834f8b0301ce1d34842babebe513525ca521ce63e3f5e8)


-

Дождитесь, пока программа покажет сообщение **Flash Complete!** и зелёную галочку


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Finstall_image%2F6.png&sig=41883fa767f1d6a76fbcae256b577a142474ff864218aa9206446611691b119e)



>

**Caution** Завершите работу с картой через функцию **Безопасное извлечение устройства** в вашей ОС, прежде чем физически извлекать карту.

-

Извлеките SD-карту

-

Установите SD-карту в слот на плате расширения Raspberry Pi CM4

-

Подайте питание на Raspberry Pi через USB Type-C или [АКБ](/learn/clover-2/akb)

-

Дождитесь загрузки — появится эффект «радуга» на светодиодной ленте (~60 секунд)


## Индикация состояний дрона


### Светодиодная лента

|  Сигнал |  Значение |
|  Белый |  Дрон запускается (инициализация систем) |
|  Эффект «радуга» |  Есть связь с полётным контроллером |
|  Мигающий красный |  Связь с полётным контроллером потеряна |
|  Оранжевый |  Режим ACRO |
|  Бирюзовый |  Режим Stabilized |
|  Жёлтый |  Режим Altitude |
|  Синий |  Режим Position |
|  Фиолетовый |  Режим OFFBOARD |
|  Быстро мигающий красный |  Низкий заряд аккумулятора |


### Светодиоды платы расширения

|  Светодиод |  Сигнал |  Значение |
|  **PWR** (красный) |  Горит непрерывно |  Стабильное питание 5В |
|  **PWR** (красный) |  Мигает или гаснет |  Недостаток питания (просадка напряжения) |
|  **ACT** (зелёный) |  Мигает |  Идёт загрузка, чтение с SD-карты |
|  **ACT** (зелёный) |  Не горит |  Нет обращения к карте / карта не читается |
|  **ACT** (зелёный) |  Горит постоянно |  Сбой загрузки (kernel panic) или отсутствие образа |
