# Настройка полётного контроллера

> Раздел: Обрик ROS 2 · slug: `flight-controller-setup`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/flight-controller-setup

---

# Настройка полётного контроллера


Раздел Vehicle Configuration в QGC содержит основные настройки полётного контроллера. Этот раздел описывает каждый его пункт, который нужно пройти перед первым полётом.


---


## Перед началом — скачайте нужное заранее


Во время настройки через Wi-Fi Обрика у вас **не будет интернета**. Поэтому заранее:

- Скачайте и установите [QGroundControl (QGC)](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html)
- Скачайте [готовый файл параметров полётного контроллера Обрика](https://drive.google.com/file/d/1392MPugvBD1SA4eytPBsy4nv05whPwLh/view?usp=drive_link)

>

**Примечание** QGC (QGroundControl) — программа для настройки и мониторинга дрона. Подробнее о подключении к ней читайте в статье [Подключение к QGroundControl](/learn/obrik-ros-2/qgc-wifi).


---


## Подготовка


Перед открытием QGC убедитесь, что:

- В Обрике вставлена SD-карта (PX4 сохраняет логи на неё)
- Обрик подключён к QGC по Wi-Fi

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F2.png&sig=cd2304ff73951e142afb8ed619da66186b6a5920e538a4edd34d60951e0c73ea)



---


## Раздел Vehicle Configuration

- Нажмите на **логотип QGC** в левом верхнем углу

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F3.png&sig=aeca2ed5a78e9419bd237d62d734bba9f7ea668f360e759e4d54018bc49f67f8)


- Выберите **Vehicle Configuration**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F4.png&sig=7bf3a526261c8c748c4bd3473fe2d44344bf4fece3139d978953801a80bc2091)



---


## Что внутри Vehicle Configuration


Перед вами откроется список вкладок. Каждая отвечает за свою часть настройки:


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F5.png&sig=9747b6d1c5e4af1e5ecd8934e7b5c743b399adba38927652f19c4f9fa43267d2)


|  Вкладка |  Что делает |
|  **Summary** |  Общий статус: зелёный маркер — система настроена, красный — требует внимания |
|  **Airframe** |  Тип летательного аппарата (квадрокоптер) — уже задан в файле параметров, отдельно настраивать не нужно |
|  **Sensors** |  Калибровка датчиков: гироскоп, акселерометр, компас, уровень горизонта |
|  **Radio** |  Калибровка аппаратуры управления (RadioMaster Pocket) |
|  **Flight Modes** |  Назначение режимов полёта на переключатели аппаратуры управления |
|  **Power** |  Настройка аккумулятора: количество ячеек, пороги напряжения |
|  **Parameters** |  Все параметры PX4 вручную — для опытных пользователей |


### Вкладка Summary — ваша «приборная панель»


Вкладка **Summary** — первое, что стоит проверять перед полётом. Зелёный маркер рядом с пунктом означает настроено, красный — нужна настройка.
