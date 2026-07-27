# Работа с камерой

> Раздел: Обрик ROS 1 (Clover) · slug: `camera`
> Источник: https://edu.sverk.tech/learn/clover-2/camera

---

# Работа с камерой


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera-connect.png&sig=1c608e3dfe22b37e8235242fbd17a5c0d024aebe437b85b55689f25178b28afb)



![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera-connect2_1.png&sig=85fa956037728dd64cbe3b5154746ee902dbb4c5a5f706df04080719531e0992)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fcamera-connect2_2.png&sig=4050c8a5d3e55281442382e0ced6fe0847ff498fdc8075917f3494a273c5e56f)



Для работы с основной камерой необходимо убедиться что она включена в файле `~/catkin_ws/src/sverk/sverk/launch/sverk.launch`:


```
<arg name="main_camera" default="true"/>

```


Также нужно убедиться, что камера [сфокусирована и для нее указано корректное расположение и ориентация](/learn/clover-2/camera-setup).


При изменении launch-файла необходимо перезапустить пакет `sverk`:


```
sudo systemctl restart sverk

```


Для мониторинга изображения с камеры можно использовать [rqt](/learn/clover-2/rviz) или [web_video_server](/learn/clover-2/web-video-server).


## Неисправности


Если изображение с камеры отсутствует, попробуйте проверить ее с помощью утилиты [`raspistill`](https://www.raspberrypi.org/documentation/usage/camera/raspicam/raspistill.md).


Остановите сервисы дрона:


```
sudo systemctl stop sverk

```


Получите картинку с камеры утилитой `raspistill`:


```
raspistill -o test.jpg

```


Если команда завершается с ошибкой, проверьте качество подключения шлейфа камеры к Raspberry Pi или замените его.


## Настройки камеры


Ряд параметров камеры - размер изображения, максимальную частоту кадров, экспозицию - можно настроить в файле `main_camera.launch`. Список настраиваемых параметров можно [посмотреть в репозитории cv_camera](https://github.com/OTL/cv_camera#parameters).


Параметры, не указанные в этом списке, можно указывать через [код параметра OpenCV](https://docs.opencv.org/3.3.1/d4/d15/group__videoio__flags__base.html). Например, для установки фиксированной экспозиции добавьте следующие параметры в ноду камеры:


```
<param name="property_0_code" value="21"/>
<param name="property_0_value" value="0.25"/>
<param name="cv_cap_prop_exposure" value="0.3"/>

```


## Компьютерное зрение


Для реализации алгоритмов компьютерного зрения рекомендуется использовать предустановленную на [образ SD-карты](/learn/clover-2/install-image) библиотеку [OpenCV](https://opencv.org).


### Python


Пример создания подписчика на топик с изображением с основной камеры для обработки с использованием OpenCV:


```
import rospy
import cv2
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from sverk import long_callback

rospy.init_node('cv')
bridge = CvBridge()

@long_callback
def image_callback(data):
    img = bridge.imgmsg_to_cv2(data, 'bgr8')  # OpenCV image
    # Do any image processing with cv2...

image_sub = rospy.Subscriber('main_camera/image_raw', Image, image_callback)

rospy.spin()

```


#### Ограничение использования CPU


При использовании топика `main_camera/image_raw` скрипт будет обрабатывать максимальное количество кадров с камеры, активно используя CPU (вплоть до 100%). В задачах, где обработка каждого кадра не критична, можно использовать топик, где кадры публикуются с частотой 5 Гц: `main_camera/image_raw_throttled`:


```
image_sub = rospy.Subscriber('main_camera/image_raw_throttled', Image, image_callback, queue_size=1)

```


#### Публикация изображений


Для отладки обработки изображения можно публиковать отдельный топик с обработанным изображением:


```
image_pub = rospy.Publisher('~debug', Image)

```


Публикация обработанного изображения:


```
image_pub.publish(bridge.cv2_to_imgmsg(img, 'bgr8'))

```


Получаемые изображения можно просматривать используя [web_video_server](/learn/clover-2/web-video-server) или [rqt](/learn/clover-2/rviz).


#### Получение одного кадра


Существует возможность единоразового получения кадра с камеры. Этот способ работает медленнее, чем подписка на топик; его не следует применять в случае необходимости постоянной обработки изображений.


```
import rospy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

rospy.init_node('cv')
bridge = CvBridge()

# ...

# Retrieve a frame:
img = bridge.imgmsg_to_cv2(rospy.wait_for_message('main_camera/image_raw', Image), 'bgr8')

```


### Примеры


#### Работа с QR-кодами


>

**Hint** Для высокоскоростного распознавания и позиционирования лучше использовать [ArUco-маркеры](/learn/clover-2/aruco).


Для программирования различных действий коптера при детектировании нужных [QR-кодов](https://ru.wikipedia.org/wiki/QR-%D0%BA%D0%BE%D0%B4) можно использовать библиотеку [pyZBar](https://pypi.org/project/pyzbar/). Она уже установлена в последнем образе для Raspberry Pi.


Распознавание QR-кодов на Python:


```
import rospy
from pyzbar import pyzbar
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from sverk import long_callback

rospy.init_node('cv')
bridge = CvBridge()

@long_callback
def image_callback(msg):
    img = bridge.imgmsg_to_cv2(msg, 'bgr8')
    barcodes = pyzbar.decode(img)
    for barcode in barcodes:
        b_data = barcode.data.decode('utf-8')
        b_type = barcode.type
        (x, y, w, h) = barcode.rect
        xc = x + w/2
        yc = y + h/2
        print('Found {} with data {} with center at x={}, y={}'.format(b_type, b_data, xc, yc))

image_sub = rospy.Subscriber('main_camera/image_raw_throttled', Image, image_callback, queue_size=1)

rospy.spin()

```


>

**Hint** Смотрите другие примеры по работе с компьютерным зрением в каталоге `~/examples` [образа для RPi](/learn/clover-2/install-image).


## Запись видео


Для записи видео может использована нода [`video_recorder`](http://wiki.ros.org/image_view#image_view.2Fdiamondback.video_recorder) из пакета `image_view`:


```
rosrun image_view video_recorder image:=/main_camera/image_raw

```


Видео будет сохранено в файл `output.avi`. В аргументе `image` указывается название топика для записи видео.
