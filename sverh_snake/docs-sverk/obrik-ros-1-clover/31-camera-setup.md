# Настройка камеры

> Раздел: Обрик ROS 1 (Clover) · slug: `camera-setup`
> Источник: https://edu.sverk.tech/learn/clover-2/camera-setup

---

# Настройка камеры


Для корректной работы всех функций, связанных с компьютерным зрением (в том числе [полёта по ArUco-маркерам](/learn/clover-2/aruco) и [Optical Flow](/learn/clover-2/optical-flow)) необходимо сфокусировать основную камеру, а также выставить ее расположение и ориентацию. Улучшить качество работы также может опциональная калибровка камеры.


## Настройка фокуса камеры


Для успешного осуществления полётов с использованием камеры, необходимо настроить фокус камеры.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcam_setup.png&sig=8eb43f1b47b515b11917e1bae7ce483af4424fca6e7dbe16c5036b79c82fe599)


- Откройте трансляцию изображения с камеры используя [web_video_server](/learn/clover-2/web-video-server).
- С помощью вращения объектива камеры добейтесь максимальной резкости деталей (предпочтительно на расстоянии предполагаемой высоты полёта – 2–3 м).
|  Расфокусированное изображение |  Сфокусированное изображение |
|
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Funfocused.png&sig=b690ca6f27dfb57105733271040957968f2b377ac54edac9ab966932f4902605)
 |
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Ffocused.png&sig=2a5a28c368990a5ff89d8d0b8fc5662c2da805b9b188ae4967fbd96aad20c34d)
 |


## Настройка расположения камеры


Расположение и ориентация камеры [задается в файле](/learn/clover-2/cli#%D1%80%D0%B5%D0%B4%D0%B0%D0%BA%D1%82%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-%D1%84%D0%B0%D0%B9%D0%BB%D0%BE%D0%B2) `~/catkin_ws/src/sverk/sverk/launch/main_camera.launch`:


```
<arg name="direction_z" default="down"/>
<arg name="direction_y" default="backward"/>

```


Для того, чтобы задать ориентацию, необходимо установить:

- направление обзора камеры `direction_z`: вниз (`down`) или вверх (`up`);
- направление, в которое указывает шлейф камеры `direction_y`: назад (`backward`) или вперед (`forward`).

### Примеры


#### Камера направлена вниз, шлейф назад


```
<arg name="direction_z" default="down"/>
<arg name="direction_y" default="backward"/>

```


<p>
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcamera_option_1_rviz.png&sig=b13d3fc0d287d69db5906b41bfe25ff030f6aae886442e0002438ed20ea5ac87)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera_option_1.png&sig=5708f809f0d600c0ec1bb7be90c1e7dd81bb8fbb69e74b532d271ff30f6624e0)
</p>


#### Камера направлена вниз, шлейф вперёд


```
<arg name="direction_z" default="down"/>
<arg name="direction_y" default="forward"/>

```


<p>
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcamera_option_2_rviz.png&sig=3121a376637d9096876af5d635628ba0438d1325072fd76ff72f3593eb3d04d9)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera_option_2.png&sig=4a62e0b7436dcda7f10daa5ff6c8bb497b4b6cfe38c0ba2032940f9fd4f9b944)
</p>


#### Камера направлена вверх, шлейф назад


```
<arg name="direction_z" default="up"/>
<arg name="direction_y" default="backward"/>

```


<p>
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcamera_option_3_rviz.png&sig=0bfa81e23e7e69a718868bb2b15d149e2f2b428ca36f6b2dfc53957c0a8efaf9)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera_option_3.png&sig=13543c2267132616146f39a80edc6ca1eb30ba8f2d09a2254151eb4cb7aec7fc)
</p>


#### Камера направлена вверх, шлейф вперёд


```
<arg name="direction_z" default="up"/>
<arg name="direction_y" default="forward"/>

```


<p>
![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fcamera_option_4_rviz.png&sig=7a80ace2c4efd87c51402876cb30e054f27b5af60d7f7c8e8f745296b90cc427)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera_option_4.png&sig=931577c23ea127514af56f3f716dca60e9e5fb7d0e3e3542b26220ab567adae1)
</p>


>

**Hint** [Утилита `selfcheck.py`](/learn/clover-2/automatic-check) выдает словесное описание установленной в данной момент ориентации основной камеры.


### Произвольное расположение камеры


Также возможны произвольное расположение и ориентация камеры. Для этого раскомментируйте запуск ноды, подписанной как `Template for custom camera orientation`:


```

<node pkg="tf2_ros" type="static_transform_publisher" name="main_camera_frame" args="0.05 0 -0.07 -1.5707963 0 3.1415926 base_link main_camera_optical"/>

```


Эта строка задает статическую трансформацию между фреймом `base_link` ([соответствует корпусу полётного контроллера](/learn/clover-2/frames)) и камерой (`main_camera_optical`) в формате:


```
сдвиг_x сдвиг_y сдвиг_z угол_рысканье угол_тангаж угол_крен

```


Фрейм камеры задается таким образом, что:

- **<font color=red>x</font>** указывает направо на изображении;
- **<font color=green>y</font>** указывает вниз на изображении;
- **<font color=blue>z</font>** указывает от плоскости матрицы камеры.

Сдвиги задаются в метрах, углы задаются в радианах. Корректность установленной трансформации может быть проверена с использованием [rviz](/learn/clover-2/rviz).


## Калибровка


Для улучшения качества работы алгоритмов также рекомендуется произвести калибровку камеры, процесс которой описан [в отдельной статье](/learn/clover-2/camera-calibration).
