# Доступ по SSH к Raspberry Pi

> Раздел: Обрик ROS 1 (Clover) · slug: `ssh`
> Источник: https://edu.sverk.tech/learn/clover-2/ssh

---

# Доступ по SSH к Raspberry Pi


На [образе для RPi](/learn/clover-2/install-image) преднастроен доступ по SSH для редактирования файлов, загрузки данных и запуска программ.


Для доступа по SSH необходимо [подключиться к Raspberry Pi по Wi-Fi](/learn/clover-2/connect-wi-fi) (также возможно подключение через Ethernet-кабель).


В GNU/Linux или macOS необходимо запустить Терминал и выполнить команду:


```
ssh pi@192.168.11.1

```


Пароль: `raspberry`.


Для доступа по SSH из Windows можно использовать [PuTTY](https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html) или веб-доступ (см. далее). Также можно получить доступ по SSH со смартфона с помощью приложения [Termius](https://www.termius.com).


>

**Hint** Для того, чтобы не вводить пароль при каждом подключении по SSH, см. [статью об использовании SSH-ключей](/learn/clover-2/ssh-keys).


Подробнее: [https://www.raspberrypi.org/documentation/remote-access/ssh/README.md](https://www.raspberrypi.org/documentation/remote-access/ssh/README.md).


## Веб-доступ


Доступ к терминалу также доступен через веб-браузер (с использованием [Butterfly](https://github.com/paradoxxxzero/butterfly)). Для доступа откройте страницу [http://192.168.11.1](http://192.168.11.1) и выберите на ней ссылку *Open web terminal*:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fbutterfly.png&sig=df337bda32e0bd4c3533ce125169508143fcd7f86493c92b092df486e709ff6d)



**Далее**: [Командная строка](/learn/clover-2/cli).
