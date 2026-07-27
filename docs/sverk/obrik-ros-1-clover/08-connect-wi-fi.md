# Подключение к QGroundControl

> Раздел: Обрик ROS 1 (Clover) · slug: `connect-wi-fi`
> Источник: https://edu.sverk.tech/learn/clover-2/connect-wi-fi

---

# Подключение к QGroundControl


После включения бортовой компьютер либо раздаёт локальную Wi-Fi точку доступа, либо подключается к роутеру.


В обоих случаях доступны:

- Веб-доступ к инструментам управления и мониторинга.
- Сквозной канал связи (через TCP) между программой QGroundControl (QGC) на вашем ПК и полётным контроллером PX4 внутри дрона.

## Безопасное включение дрона

-

**Убедитесь, что воздушные винты сняты**

-

Включите Обрик с помощью [АКБ](/learn/clover-2/akb) или кабеля USB Type-C


>

**Hint** Рекомендуем использовать USB для первого подключения


<p>
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2Fdrone1.jpg&sig=e4bac7b9c68e75411b1c349c08f7a9485d988ae5b911ad94409838045367c2c4)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2Fdrone2.jpg&sig=7e38865945e819cef8b5f287a45fc564f7c9fc40cb2983f2f185a485093b25a8)
</p>

- Через 30–60 секунд загорится светодиодная лента и в списке Wi-Fi сетей появится сеть Sverk-xxxxx

>

**Info** SSID (имя сети) — Sverk-xxxxx, где xxxxx — 5 случайных цифр, назначаемых при первом включении бортового компьютера.


## Шаг 1: Подключитесь к сети Обрика

-

На вашем компьютере/ноутбуке найдите в списке Wi-Fi сеть с именем **Sverk-xxxxx** (например, Sverk-58421)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F1.png&sig=2a0ec17a9416db3b1127c6788cb15098d2603ed98f78def36a7af44a5a37a2ee)


-

Подключитесь к сети, используя пароль: `sverkwifi`


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F2.png&sig=2444c9dfdbe2ab2d52077b2cf326d29cc1da1d02d1bba2437c33a7aba72c1a46)



## Шаг 2: Подключение полётного контроллера к QGC по Wi-Fi


>

**Hint** По умолчанию на Обрике настроена возможность подключения QGC по протоколу TCP.

-

Запустите программу **QGC**

-

Нажмите на **логотип QGC** в левом верхнем углу


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F4.png&sig=31581daee7caf2889f1b48999808d3587351301168ca60f811e15b8d04f86a72)


-

В открывшемся списке выберите **Application Settings**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F5.png&sig=5507a1a9df7cd6455886cd5c0d9d0fe8fb8dbb89af19b8541085c3a6d0668c23)


-

Выберите меню **Comm Links** и в окне **Links** нажмите **Add**, чтобы добавить новое подключение


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F6.png&sig=062890a3715ca6a5d89f1ea99a331628eb18fbc09ba6561f65ce660866cf7d0c)


-

Введите параметры подключения:

  - **Name:** любое название, например Sverk
  - Активируйте ползунок **Automatically Connect on Start**
  - **Type:** TCP
  - **Server Address:** `192.168.11.1`
  - **TCP Port:** `5760`

>

**Note** Порт 5760 — стандартный порт для передачи MAVLink-данных через TCP. Менять его не нужно, если вы не настраивали порт вручную.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F7.png&sig=a85e575f6c73fbf918bdcbb1c5d971f46b0bea8d799abf847588f629f21f1c08)


-

Нажмите **Save**, затем выберите созданное подключение и нажмите **Connect**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F8.png&sig=a2123d69ee8fbee31c6062f3e7bee1dbf7fb446acecf24ad63ae2d5452aca4a5)



>

**Hint** Теперь, если Обрик включён и раздаёт Wi-Fi, он будет автоматически подключаться к QGC при запуске программы.


## Подключение вручную


Если ползунок **Automatically Connect on Start** не был активирован, при каждом запуске QGC нужно подключаться вручную.

-

На главном экране QGC нажмите **Click to manually connect**


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F9.png&sig=7beb38853ba49142dcf61e8021e90fd2cd00dd44b7646ab08e39f7ef43cfec6a)


-

Нажмите на название вашего подключения к Обрику


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fconnect_wi-fi%2F10.png&sig=14d64342704075370abb24625e10661b63b239a2077971afc10258f46547b3f2)


-

В левом верхнем углу QGC пропадёт надпись **DISCONNECTED** и появятся данные с датчиков (температура батареи, уровень сигнала и т. д.)


>

**Hint** Для изменения имени или пароля Wi-Fi сети Обрика, а также переключения в режим клиента, см. [Настройка Wi-Fi](network.md).
