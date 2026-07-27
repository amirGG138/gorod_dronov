# Работа с полем ArUco-маркеров

> Раздел: Обрик ROS 2 · slug: `aruco-field`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/aruco-field

---

# Работа с полем ArUco-маркеров


В комплект Обрика входит готовая распечатанная карта меток. Она уже записана в систему бортового компьютера при установке образа.


ArUco-маркер — квадратная бинарная метка с уникальным числовым ID. Камера распознаёт каждый маркер, определяет расстояние до него и ориентацию в пространстве (6 степеней свободы), и передаёт координаты в систему навигации. Дрон видит маркеры на полу и понимает, где он находится — без GPS.


<p align=“center”>
![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_pc%2F11.jpg&sig=e313e96ec307ad1781594262fc447b02934af01df12c185ce88d3b0d1c8b8d88)
 </p>


>

**Примечание** Точность навигации напрямую зависит от качества калибровки камеры, освещённости и физического состояния меток. Регулярно проверяйте систему. Подробнее о калибровке: [Настройка камеры](/learn/obrik-ros-2/camera-focus).


Убедитесь, что ваш компьютер подключён к Wi-Fi сети Обрика.


---


## Проверка ArUco-карты


Откройте [СВЕРХ WEB](/learn/obrik-ros-2/web-interface) → **Web video server**. В списке топиков найдите `aruco_map/debug_image/plane_1` и нажмите **Stream Viewer** — топик выводит рендер карты ArUco, настроенной в системе как основная.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fweb-interface%2Fsverk-web-topics.png&sig=ec9c704cad3283efbaf095910448e2bb9f8b89e294fc7336e71f3884a20ec7a0)



---


## Генерация файла карты


>

**Примечание** Подробности описаны в статье [«Навигация по ArUco-маркерам»](/learn/obrik-ros-2/aruco-navigation).


Чтобы создать файл карты, выполните команду с параметрами своей карты:

- `LENGTH` — размер маркера (в метрах)
- `X` — количество маркеров по оси X (столбцов)
- `Y` — количество маркеров по оси Y (строк)
- `DIST_X` — расстояние между центрами маркеров по оси X (в метрах)
- `DIST_Y` — расстояние между центрами маркеров по оси Y (в метрах)
- `FIRST_ID` — ID первого маркера
- `--bottom-left` (опционально) — нумерация с левого нижнего угла

```
ros2 run aruco_pose genmap.py LENGTH X Y DIST_X DIST_Y FIRST_ID [--bottom-left] [-o MAP_NAME]

```


### Пример для карты из комплекта


Параметры карты из комплекта:

- `LENGTH` — 0.3 м
- `X` — 3 столбца
- `Y` — 2 строки
- `DIST_X` — 0.5 м
- `DIST_Y` — 0.5 м
- `FIRST_ID` — 42

```
ros2 run aruco_pose genmap.py 0.3 3 2 0.5 0.5 42 -o sverk.txt

```


>

**Примечание** Первая метка — №42, поэтому карта создастся с метками 42, 43, 44, 45, 46, 47. Если номера отличаются, отредактируйте файл вручную (см. ниже).


---


## Редактирование карты вручную


Откройте файл карты:


```
nano ~/sverk_ws/src/sverk_drone/odomerty/aruco/aruco_map/config/sverk.txt

```


Измените первый столбец (ID меток) и при необходимости размер первой метки для взлёта.


Для перемещения по файлу используйте стрелки на клавиатуре.


Было:


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_pc%2F6.png&sig=13195bdabc7bb72f3b1987f0a665f196759d886c82a0cf9e884ae9ed138ed015)



Стало:


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_pc%2F7.png&sig=0bf37cd95bdc72db4879d3754779ab8ac08fdb21d3da665730a8257afdc44153)



Сохраните и выйдите: `Ctrl+X`, затем `Y`, затем `Enter`.


Перезапустите сервис, чтобы изменения применились:


```
sudo systemctl restart sverk-ros2-docker.service

```


>

**Примечание** Эта команда выполняется на бортовом компьютере вне Docker-контейнера (через SSH или терминал).


---


## Проверка навигации


После запуска системы проверьте, что ArUco-навигация работает:


```
ros2 topic echo /aruco_map/pose

```


Если дрон видит маркеры, в терминале появится поток сообщений с координатами.


Убедитесь, что карта сгенерировалась корректно — в веб-интерфейсе откройте **Web video server** и выберите топик `aruco_map/debug_image/plane_1`.


---


Описание всех инструментов веб-интерфейса → [Веб-интерфейс Обрика](/learn/obrik-ros-2/web-interface).
