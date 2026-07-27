# Автозапуск ПО

> Раздел: Обрик ROS 1 (Clover) · slug: `autolaunch`
> Источник: https://edu.sverk.tech/learn/clover-2/autolaunch

---

# Автозапуск ПО


## systemd


Основная документация: [https://wiki.archlinux.org/index.php/Systemd_(Русский)](https://wiki.archlinux.org/index.php/Systemd_(%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9))


Всё автоматически запускаемое ПО дрона работает в виде systemd-сервиса `sverk.service`.


Перезапустить сервис:


```
sudo systemctl restart sverk

```


Просмотреть текстовый вывод ПО:


```
journalctl -u sverk

```


Запустить ПО непосредственно в текущей консольной сессии:


```
sudo systemctl stop sverk
roslaunch sverk sverk.launch

```


Выключить автозапуск ПО дрона:


```
sudo systemctl disable sverk

```


## roslaunch


Основная документация: [http://wiki.ros.org/roslaunch](http://wiki.ros.org/roslaunch)


Список нод для автозапуска указывается в файле:


```
/home/pi/catkin_ws/src/sverk/sverk/launch/sverk.launch

```


Вы можете добавить собственную ноду в список автозапускаемых. Для этого разместите ваш запускаемый файл (например, `my_program.py`) в каталог `/home/pi/catkin_ws/src/sverk/sverk`. Затем добавьте запуск вашей ноды в `sverk.launch`:


```
<node name="my_program" pkg="sverk" type="my_program.py" output="screen"/>

```


Запускаемый файл должен иметь права на запуск:


```
chmod +x my_program.py

```


При использовании скриптовых языков в начале файла должен стоять <a href=“[https://ru.wikipedia.org/wiki/Шебанг_(Unix)](https://ru.wikipedia.org/wiki/%D0%A8%D0%B5%D0%B1%D0%B0%D0%BD%D0%B3_(Unix))”>shebang</a>:


```
#!/usr/bin/env python3

```
