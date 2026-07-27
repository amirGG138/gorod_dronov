# Быстрый старт

> Раздел: Обрик ROS 1 (Clover) · slug: `quick-start`
> Источник: https://edu.sverk.tech/learn/clover-2/quick-start

---

# Быстрый старт

-

Подключение питания и сети

  - Подключите заряженный [АКБ](/learn/clover-2/akb), ждите загрузки бортового компьютера (около 30-60 секунд).
  - Подключитесь к Wi-Fi сети, который раздаёт Обрик. Если Обрик подключен к роутеру, узнайте его IP-адрес у организатора или посмотрите на экране.
-

Доступ к управлению. Подключиться к Обрику можно двумя способами:

  - через веб-интерфейс. Введите IP-адрес в адресную строку браузера. В веб-интерфейсе доступен терминал. На главной странице нажмите на Open web terminal. Введите пароль:

```
raspberry

```


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start1.png&sig=8723aae7477cb7a1a588fda63b94f6f365534a4e7eab2ef54d303dab8986821a)


  - SSH доступ через терминал ПК:

```
ssh pi@айпи_адрес_дрона

```

-

Проверка камеры и ArUco карты. В веб-интерфейсе перейдите в раздел View image topics

  - Проверка камеры. Выберите топик image_raw. Убедитесь, что передается четкое изображение.

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start2.png&sig=8c2be413c7c7dfe0ed70882b38150e8d4d5c1b149c122c1246b5ca6942673ba6)


  - Проверка карты. Выберите топик `aruco_map/image`. Проверьте, какая ArUco карта загружена на Обрик.

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start3.png&sig=fb30f3e053f7132f1060db42a86a5e23d35bd4a41586ef02d77de7b32dd66ba7)


-

Настройка ArUco карты


Если в aruco_map/image карта не соответствует той, по которой вы будете летать, её нужно заменить.

  - Зайдите в терминал, введите команду:

```
cd catkin_ws/src/sverk/aruco_pose/map

```


>

**Note** В этой директории расположены txt файлы с ArUco-картами.

  - Если среди файлов нет нужной вам карты, создайте её при помощи команды:

```
nano название_файла.txt

```

  - Сохраните файл:

```
Сtrl+X  -> Y  ->Enter

```

  - Далее нужно заменить данные об ArUco-карте в launch файле:

```
cd catkin_ws/src/sverk/sverk/launch/aruco.launch``
nano aruco.launch

```

  - Перезагрузите Обрик:

```
sudo systemctl restart sverk

```

-

Диагностика


Для автоматической проверки Обрика выполните команду:


```
rosrun sverk selfcheck.py

```


>

**Hint** Убедитесь, что все критические показатели отмечены как ОК.

-

Настройка полётного контроллера в QGroundControl


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start4.png&sig=34d6503bcba54a46b87719e22a15c8892749d150aa81f759ccab01164e4acbc9)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start5.png&sig=0faf1e80a3a7fa588fd34b31aafc91ff35a8d2d699defa3147f8db0bad7208cd)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start6.png&sig=b940c10cb8bc77c3bded37fdc295116036ef84af1f58f678564f51a1fa7dfa2c)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start7.png&sig=89c6ec42610404d3b2b3591460e30ac2576846e81934d1a480fcdae4c4e32560)


  -

Откалибруйте гироскоп (Sensors -> Gyroscope)

  -

Откалибруйте акселерометр (Sensors -> Accelerometer). Поочерёдно зафиксируйте Обрик во всех положениях, дожидаясь появления зелёной рамки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fknowledge_base%2Fquick_start8.png&sig=06a8e407875815b21b3169ddf6821a5088c24e79d3eafa49cab2847ea3867f22)


  - Откалибруйте линию горизонта (Sensors -> Level Horizon)
  - Установите дрон на ровную поверхность
  - Нажмите **Оk**

После калибровки Обрик готов к запуску.
