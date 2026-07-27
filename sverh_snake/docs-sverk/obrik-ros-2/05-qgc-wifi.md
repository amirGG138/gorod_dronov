# Подключение к QGroundControl по Wi-Fi

> Раздел: Обрик ROS 2 · slug: `qgc-wifi`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/qgc-wifi

---

# Подключение к QGroundControl по Wi-Fi


Через Wi-Fi программа QGroundControl на вашем компьютере связывается с полётным контроллером Обрика: позволяет настраивать его, следить за состоянием дрона и видеть данные с датчиков в реальном времени.


---


## QGroundControl


**QGroundControl (QGC)** — бесплатная программа для настройки и мониторинга дронов. Она показывает телеметрию (данные с датчиков), позволяет менять параметры полётного контроллера PX4, калибровать датчики и запускать автоматические полёты.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fqgc-wifi-link.svg&sig=a4d65e1dbf3108642dd972f16a5e37c52fbc9e1516085ccd154f6c8efe83f7c4)



---


## Как работает подключение


Бортовой компьютер Обрика после включения делает одно из двух:

- **Подключается к роутеру** — к известной Wi-Fi сети (в нашем случае сеть называется **Poletka**)
- **Раздаёт собственную Wi-Fi точку доступа** — создаёт сеть, к которой подключаются другие устройства

Через Wi-Fi бортовой компьютер передаёт команды и данные между QGC на вашем компьютере и полётным контроллером PX4 внутри Обрика по протоколу **UDP** (протокол быстрой передачи данных через сеть). Ретрансляцию выполняет mavlink-router на борту, открывая порт **14550**.


>

**Примечание** Сейчас используется прямое UDP-подключение к порту 14550. Альтернативное подключение через мост (по аналогии с `gcs_bridge` в документации Клевера) — в разработке.


---


## Безопасное включение дрона


>

**Внимание** Снимите воздушные винты перед включением. Во время настройки моторы могут случайно запуститься — без пропеллеров это безопасно.

-

Включите Обрик, используя АКБ или кабель USB Type-C


>

**Подсказка** Для первого подключения рекомендуется использовать USB — так не нужен заряженный аккумулятор


<p>
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2Fdrone1.jpg&sig=61f5229e3426e0b845bc863735274b08dbc671ad6c4dc29d06d66c331062cfc2)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2Fdrone2.jpg&sig=626fb1fa8e24dbe33df7b79a552b66f9a3f520c40bce3593bb4e441539d9b0e5)
</p>

-

Подождите 30–60 секунд — бортовой компьютер загружается, загорится светодиодная лента


---


## Шаг 1: Подключитесь к Wi-Fi сети Обрика


**Сценарий с роутером**:

- Обрик автоматически подключается к сети Wi-Fi **Poletka**
- Подключите свой компьютер к той же сети с паролем: **poletka1**
- Узнайте IP-адрес своего Обрика в сети:
  - Скачайте и установите программу [Advanced IP Scanner](https://www.advanced-ip-scanner.com/ru/)
  - Запустите программу, нажмите кнопку **IP** — она автоматически определит диапазон адресов вашей сети
  - Нажмите **Сканировать** и дождитесь результатов
  - Найдите в списке устройство с именем Обрика и запомните его IP-адрес (например, `192.168.1.105`)

>

**Примечание** IP-адрес — уникальный адрес устройства в сети. У каждого устройства в Wi-Fi сети он свой.


---


## Шаг 2: Настройте подключение в QGC


>

**Примечание** По умолчанию Обрик готов к подключению QGC по протоколу **UDP** через порт **14550**.

-

Запустите программу **QGC**

-

Нажмите на **логотип QGC** в левом верхнем углу


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F4.png&sig=4e31b36c2ad923a270839f950bf833486f3686e6fad85845b085e2fe73b4cd79)


-

В открывшемся списке выберите **Application Settings**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F5.png&sig=cbe6778b16e87c8d0db477298911a85dfe81efed4f6d2eae49e8a9128a95194a)


-

Выберите меню **Comm Links** и в окне **Links** нажмите **Add** — добавится новое подключение


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F6.png&sig=13327b88c557022026dee5e5eed9c2cc090ba1147de7b89346d6da2e32312fae)


-

Введите параметры подключения:

  - **Name:** любое название, например `Sverk`
  - **Automatically Connect on Start:** включите ползунок (тогда QGC будет подключаться к Обрику автоматически при запуске)
  - **Type:** `UDP`
  - **Server Address:** `IP-адрес вашего Обрика` (тот, что нашли в Advanced IP Scanner)
  - **UDP Port:** `14550`

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F7.png&sig=0f141dac9f051d01a380f6ce1b0502e2ef449c117cd1688f4768e2117ec02cd6)


-

Нажмите **Save** для сохранения, затем выберите созданное подключение и нажмите **Connect**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F8.png&sig=f7090d276ca5cae6c995aeda78c75bab16fafc48768dc4a9de9127dc6e9b4435)



>

**Примечание** Если «Automatically Connect on Start» включено — при следующем запуске QGC подключится к Обрику автоматически.


---


## Подключение вручную (если автоматическое не включено)

-

На главном экране QGC нажмите **Click to manually connect**


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F9.png&sig=7f668edecbeac24980e74ab46d647e5cb575e0fe34dddf71da145f1254d6aeac)


-

Нажмите на название своего подключения к Обрику


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fconnect_wi-fi%2F10.png&sig=cab68e8ffa4c426400d95861346f5196182168d64f3ab46058db07795f1d6042)


-

В левом верхнем углу QGC пропадёт надпись **DISCONNECTED** и появятся данные с датчиков: температура аккумулятора, уровень сигнала и т.д.
