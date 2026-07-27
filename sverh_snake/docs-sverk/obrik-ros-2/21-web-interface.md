# Веб-интерфейс Обрика

> Раздел: Обрик ROS 2 · slug: `web-interface`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/web-interface

---

# Веб-интерфейс Обрика


После запуска системы бортовой компьютер открывает два веб-интерфейса, доступных с любого устройства в той же сети.

|  Адрес |  Что открывается |
|  `http://192.168.X.X` |  СВЕРХ WEB — стартовая страница со ссылками на все инструменты |
|  `http://192.168.X.X:5173` |  Sverk Drone Tools — интерфейс управления и мониторинга дрона |


IP-адрес бортового компьютера уточните в настройках вашей сети или на дисплее, если он подключён.


---


## СВЕРХ WEB


Стартовая страница открывает доступ ко всем инструментам разработки.


![Стартовая страница СВЕРХ WEB](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-home.png&sig=2eb24d98eb96890fe4a3c8e45a912e66380eafe51a023e528f2d5304c8425bf9)


|  Инструмент |  Описание |
|  **VSCode** |  Редактор кода прямо в браузере — открывает папку `~/sverk_ws` |
|  **Документация** |  Встроенная документация Обрика |
|  **Файловый менеджер** |  Загрузка, скачивание и переименование файлов |
|  **Aruco Map Editor** |  Редактор карты ArUco-маркеров |
|  **Butterfly (Web Terminal)** |  Веб-терминал для выполнения команд в оболочке |
|  **Flight Review** |  Просмотр и анализ логов полётов |
|  **Web video server** |  Стриминг ROS-топиков с изображением в браузере |
|  **ROS-сервисы** |  Список и вызов ROS 2 сервисов |
|  **ROSboard** |  Визуализация данных из ROS-топиков |


---


## Sverk Drone Tools


Основной интерфейс управления и мониторинга. Открывается на порту `:5173`.


### Шапка статуса


![Шапка статуса Sverk Drone Tools](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-drone-tools-header.png&sig=3d0c56a02e55370708bf5a34d8a0f26fdcea83f95eec877a1c51195e4c328fea)



В верхней строке отображается состояние дрона в реальном времени:

|  Поле |  Значение |
|  Статус моторов |  Моторы выключены / Моторы запущены / В полёте |
|  Уровень сигнала |  Качество связи с аппаратурой управления |
|  Скорость |  Текущая скорость, км/ч |
|  X, Y, Z |  Координаты дрона в системе `map`, м |
|  До разрядки |  Оставшееся время до разряда аккумулятора |
|  Заряд |  Процент заряда аккумулятора |


В нижней панели — иконки для открытия виджетов: документации, VSCode, камеры, файлового менеджера и терминала.


### Панели


![Панели виджетов Sverk Drone Tools](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-drone-tools-panels.png&sig=20525c0a70f3294048132302a40ea31b25a7f41df408eda296cbe6df76a99b3f)



Каждый виджет открывается кнопкой на нижней панели. Можно открыть несколько сразу. Панель **«Видео с камеры»** показывает поток с `/camera_1/image_raw` или топика `/out_detection`, если запущена обработка.


---


## VSCode в браузере


Полноценный редактор кода, открывает рабочее пространство `~/sverk_ws` напрямую на бортовом компьютере.


![VSCode в браузере](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-vscode.png&sig=f9b68a2b966fbb9c1018404d37c5bb2fec550c7218a09c68983dbef7deb6cb92)



Встроенный терминал позволяет запускать программы, не выходя из браузера:


```
cd ~/sverk_ws
source install/setup.bash
python3 src/sverk_drone/sverk_interfaces/examples/simple_takeoff_land.py

```


---


## Файловый менеджер


Позволяет загружать файлы на бортовой компьютер и скачивать с него без SSH.


![Файловый менеджер](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-files.png&sig=925337265795c6ce988f6608100227f78a20a1c35a213f00e32d1790900d6160)



Перетащите файл в область загрузки или нажмите **Загрузить файл**. Удобно для загрузки своих программ в `~/sverk_ws/src`.


---


## Butterfly — веб-терминал


Полноценный терминал в браузере. Подключается к оболочке бортового компьютера.


![Веб-терминал Butterfly](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-terminal.png&sig=7a11535fb284d52672fc997073e4507e51eea2faff9727bae5983ca53750697e)



>

**Внимание** Соединение незашифрованное — не вводите пароли и ключи в этом терминале.


---


## Просмотр ROS-топиков с видео


**Web video server** публикует ROS-топики с изображением как HTTP-поток — смотреть можно прямо в браузере без ROS.


![Просмотр ROS-топиков с видео](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-topics.png&sig=ec9c704cad3283efbaf095910448e2bb9f8b89e294fc7336e71f3884a20ec7a0)



Доступные топики: `aruco_map/debug_image`, `aruco_map/debug_image/plane_1`, `camera_1/image_raw`. Нажмите **Stream Viewer** рядом с нужным топиком.


---


## ROSboard


Визуализирует данные из любых ROS-топиков в виде графиков, карт и таблиц.


![ROSboard: визуализация ROS-топиков](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-rosboard.png&sig=c189c4680023069e35f6b4c46f34a3f5423caed370bac1df3b37fc66d36a0e5a)



На скриншоте открыты топики `/fmu/out/battery_status` (напряжение, заряд, ток) и `/aruco_map/pose_cov` (положение дрона). Кликните по топику в левой панели, чтобы открыть его виджет.


---


## Aruco Map Editor


Визуальный редактор карты ArUco-маркеров. Позволяет создавать и редактировать файл карты прямо в браузере, без работы с `nano` в терминале.


Редактор заменяет ручное редактирование файла `sverk.txt` — те же параметры (ID маркеров, размер, расположение), но с графическим интерфейсом.


---


## ROS-сервисы


Показывает список всех активных ROS 2 сервисов Обрика и позволяет вызвать любой из них прямо в браузере — без терминала.


Удобно для быстрой проверки: можно вызвать `takeoff`, `land` или любой другой сервис и посмотреть ответ.


---


## Flight Review


Просмотр и анализ логов полётов в браузере. Загрузите `.ulg`-файл с SD-карты — и Flight Review покажет графики: высота, скорость, наклоны, обороты моторов, напряжение.


>

**Подсказка** Логи сохраняются на SD-карту полётного контроллера. Скачать их удобно через [Файловый менеджер](#%D1%84%D0%B0%D0%B9%D0%BB%D0%BE%D0%B2%D1%8B%D0%B9-%D0%BC%D0%B5%D0%BD%D0%B5%D0%B4%D0%B6%D0%B5%D1%80).
