# Веб-интерфейс

> Раздел: Обрик ROS 1 (Clover) · slug: `web-interface`
> Источник: https://edu.sverk.tech/learn/clover-2/web-interface

---

# Веб-интерфейс


Веб-интерфейс Обрика доступен через браузер после подключения по Wi-Fi. Он содержит основные инструменты для работы с бортовым компьютером: терминал, просмотр камеры, визуализацию и многое другое.


## Подключение

- Убедитесь, что воздушные винты сняты
- Включите Обрик используя [АКБ](/learn/clover-2/akb) либо кабель USB Type-C
- Подключитесь к сети Wi-Fi Обрика (см. [Подключение к QGroundControl](/learn/clover-2/connect-wi-fi))
- Откройте браузер и введите в адресной строке: `http://192.168.11.1`

После подключения доступен веб-интерфейс с основными инструментами:

- Документация
- Список всех [топиков](https://wiki.ros.org/ROS/Tutorials/UnderstandingTopics)
- Список топиков для работы с камерой
- Онлайн-терминал
- 3D-визуализация
- Блочное программирование
- Логи дрона

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_pc%2F1.png&sig=8686ed3dd007c895c4e341aba1cbd5c65deab01a0ded759f6259e437a26211de)



## Вход в систему

- В веб-интерфейсе найдите и откройте раздел **Web Terminal**

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_pc%2F2.png&sig=1151f661f9b757eef668289d651f9516939c83e806a18357bb3827111b9e3c46)


- В открывшемся терминале введите пароль: `raspberry`

>

**Caution** Символы пароля не отображаются при вводе в целях безопасности.

- После успешного ввода вы увидите командную строку:

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fsetup_pc%2F3.png&sig=d1e57988a8c19bd6ef2fefc779c2ec2f5ee0524827774418990eeb6e04311d6d)



>

**Hint** [Ознакомьтесь с основными командами для работы с терминалом](/learn/clover-2/cli). Для подключения с компьютера через SSH см. [Доступ по SSH](/learn/clover-2/ssh).


## Проверка камеры


В веб-интерфейсе перейдите в раздел **View image topics** и выберите топик `image_raw`. Убедитесь, что передаётся чёткое изображение.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start2.png&sig=8c2be413c7c7dfe0ed70882b38150e8d4d5c1b149c122c1246b5ca6942673ba6)
