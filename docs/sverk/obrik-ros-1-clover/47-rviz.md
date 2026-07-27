# Визуализация положения коптера

> Раздел: Обрик ROS 1 (Clover) · slug: `rviz`
> Источник: https://edu.sverk.tech/learn/clover-2/rviz

---

# Использование rviz и rqt


![rviz](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Frviz.png&sig=d12b77d727fd4ab798382efdbc0bec5b793437293eb8a58d2420b98b43bc3194)



Инструмент [rviz](http://wiki.ros.org/rviz) позволяет в реальном времени визуализировать на 3D-сцене все компоненты робототехнической системы — системы координат, движущиеся части, показания датчиков, изображения с камер.


[rqt](http://wiki.ros.org/rqt) – это набор GUI для анализа и контроля ROS-систем. Например, `rqt_image_view` позволяет просматривать топики с изображениями, `rqt_multiplot` – строить графики по значениям в топиках и т. д.


Для использования rviz и rqt необходим компьютер с ОС Ubuntu Linux (либо виртуальная машина, например [Parallels Desktop Lite](https://itunes.apple.com/ru/app/parallels-desktop-lite/id1085114709?mt=12) или [VirtualBox](https://www.virtualbox.org)).


>

**Hint** Вы можете можете использовать готовый [образ для дрона.


На него необходимо установить пакет `ros-noetic-desktop-full` или `ros-noetic-desktop`, используя [документацию по установке](http://wiki.ros.org/noetic/Installation/Ubuntu).


## Запуск rviz


Для запуска визуализация состояния дрона в реальном времени, необходимо подключиться к нему по [Wi-Fi](/learn/clover-2/connect-wi-fi) (`sverk-xxxx`) и запустить rviz, указав соответствующий ROS_MASTER_URI:


```
ROS_MASTER_URI=http://192.168.11.1:11311 rviz

```


>

**Note** В случае использования виртуальной машины для использования rviz и других инструментов может быть необходимо поменять ее сетевую конфигурацию на режим *bridge* ([см. подробности для VMware](https://docs.vmware.com/en/VMware-Workstation-Player-for-Windows/16.0/com.vmware.player.win.using.doc/GUID-826323AD-D014-475D-8909-DFA73B5A3A57.html)).


## Использование rviz


### Визуализация положения коптера


В качестве reference frame рекомендуется установить фрейм `map`. Для визуализации коптера добавьте визуализационные маркеры из топика `/vehicle_markers`. Для визуализации камеры коптера добавьте визуализационные маркеры из топика `/main_camera/camera_markers`.


Результат визуализации коптера и камеры представлен ниже:


![rviz](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcopter_visualization.png&sig=66855e865811bd2f2fccbd3bd60a423b5728c87e2150e93a1d40bad1d1d07359)



### Визуализация окружения


Можно просмотреть картинку с дополненной реальностью из топика основной камеры `/main_camera/image_raw`.


Axis или Grid настроенный на фрейм `aruco_map` будут визуализировать расположение [карты ArUco-меток](/learn/clover-2/aruco).


### jsk_rviz_plugins


Рекомендуется также установка набора дополнительных полезных плагинов для rviz [jsk_rviz_plugins](https://jsk-visualization.readthedocs.io/en/latest/jsk_rviz_plugins/index.html). Это набор позволяет визуализировать топики типа `TwistStamped` (скорость), `CameraInfo`, `PolygonArray` и многое другое. Для установки используйте команду:


```
sudo apt-get install ros-melodic-jsk-visualization

```


## Запуск инструментов rqt


![rqt](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Frqt.png&sig=4e2a70b7ca92bb07e826ae8e920fc3b693fab91cd845ba4e24fc351bc29c4c2a)



Для запуска rqt для мониторинга состояния дрона используйте команду:


```
ROS_MASTER_URI=http://192.168.11.1:11311 rqt

```


Пример запуск конкретного плагина (`rqt_image_view`):


```
ROS_MASTER_URI=http://192.168.11.1:11311 rqt_image_view

```


Краткое описание полезных rqt-плагинов:

- `rqt_image_view` – просмотр изображений из топиков типа `sensor_msgs/Image`;
- `rqt_multiplot` – построение графиков по данным из произвольным топиков (установка: `sudo apt-get install ros-melodic-rqt-multiplot`);
- Bag – работа с [Bag-файлами](http://wiki.ros.org/rosbag).
