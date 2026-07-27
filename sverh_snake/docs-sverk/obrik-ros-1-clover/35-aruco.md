# ArUco-маркеры

> Раздел: Обрик ROS 1 (Clover) · slug: `aruco`
> Источник: https://edu.sverk.tech/learn/clover-2/aruco

---

# ArUco-маркеры


[ArUco-маркеры](https://docs.opencv.org/3.2.0/d5/dae/tutorial_aruco_detection.html) — это популярная технология для позиционирования робототехнических систем с использованием компьютерного зрения.


![ArUco-маркеры](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fmarkers.jpg&sig=b9b0bd85e2ebe65225f9912445a5ed18594f5eebedaa0b333bac4b64ab8496e6)



>

**Hint** При печати визуальных маркеров необходимо использовать максимально матовую бумагу. Глянцевая бумага будет бликовать на свету, сильно ухудшая качество распознавания.


Для быстрого генерирования маркеров для печати можно использовать онлайн-инструмент: [http://chev.me/arucogen/](http://chev.me/arucogen/).


На [образе для RPi](/learn/clover-2/install-image) предустановлен пакет `aruco_pose`, предназначенный для работы с ArUco-маркерами.


## Режимы работы


Режимы работы с ArUco-маркерами:

- [распознавание и навигация по отдельным маркерам](/learn/clover-2/aruco-marker);
- [распознавание и навигация по картам маркеров](/learn/clover-2/aruco-map).

>

**Info** Исчерпывающую документацию по пакету `aruco_pose` на английском языке можно посмотреть [на GitHub](https://github.com/CopterExpress/clover/blob/master/aruco_pose/README.md).
