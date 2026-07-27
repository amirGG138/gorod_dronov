# Просмотр изображений с камер

> Раздел: Обрик ROS 1 (Clover) · slug: `web-video-server`
> Источник: https://edu.sverk.tech/learn/clover-2/web-video-server

---

# Просмотр изображений с камер


Для просмотра изображений с камер (или других ROS-топиков) можно воспользоваться [rviz](/learn/clover-2/rviz), rqt, или смотреть их через браузер, используя web_video_server.


См. подробнее про [использование rqt](/learn/clover-2/rviz).


## Просмотр через браузер


Для просмотра видеострима нужно подключиться к Wi-Fi сети дрона (`sverk-xxxx`), перейти на страницу [http://192.168.11.1:8080/](http://192.168.11.1:8080/) и выбрать топик.


![Просмотр web_video_server](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fweb_video_server.png&sig=02981376dade9b5517403fe1ea94e9b7527287997eb969ce090eeda67012717b)



Если передача картинки работает слишком медленно, можно ускорить ее, указав тип передаваемых данных `mjpeg` и меняя GET-параметр `quality` (от 1 до 100), который отвечает за сжатие видеострима, например:


[http://192.168.11.1:8080/stream_viewer?topic=/main_camera/image_raw&type=mjpeg&quality=1](http://192.168.11.1:8080/stream_viewer?topic=/main_camera/image_raw&type=mjpeg&quality=1)


По URL выше будет доступен стрим с основной камеры в минимальном возможном качестве.


Также доступны параметры `width`, `height` и другие. Подробнее о `web_video_server`: [http://wiki.ros.org/web_video_server](http://wiki.ros.org/web_video_server).


## Просмотр через rqt_image_view


Для просмотра изображений через инструменты rqt необходим компьютер с установленной Ubuntu 20.04 и [ROS Noetic](http://wiki.ros.org/noetic/Installation/Ubuntu).


Подключитесь к Wi-Fi сети дрона и запустите `rqt_image_view` с указанием его IP-адреса:


```
ROS_MASTER_URI=http://192.168.11.1:11311 rqt_image_view

```


Выберите топик для просмотра, например, `/main_camera/image_raw`:


![rqt_image_view](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Frqt_image_view.jpg&sig=fb72812e70ea06aff9710d1a08c4be744162f2dbececb662494a79daa5d509f6)



Для снижения нагрузки на сеть и уменьшения задержки используйте сжатый вариант топика – `/main_camera/image_raw/compressed`.


Для изменения настроек сжатия используйте rqt-плагин Dynamic Reconfigure:


![rqt_image_view+rqt_dynamic_reconfigure](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Frqt_image_view_dyn_rec.jpg&sig=64fd97eb9c05b5be6fe99266d15e1565954d987a45c0f01983e5b99c2eaef336)



См. [подробнее об rviz и rqt](/learn/clover-2/rviz).
