# Блочное программирование

> Раздел: Обрик ROS 1 (Clover) · slug: `blocks`
> Источник: https://edu.sverk.tech/learn/clover-2/blocks

---

# Блочное программирование


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fblockly.svg&sig=622687288bb644493e570868268289dd25260ea6cedaaf785a934bbe6b4765a0)



Реализация блочного программирования основана на [Google Blockly](https://developers.google.com/blockly). Интеграция Blockly в квадрокоптер позволяет понизить входной порог в программирование автономных полётов до минимального уровня.


## Конфигурация


Для корректной работы блочного программирования аргумент `blocks` в launch-файле (`~/catkin_ws/src/sverk/sverk/launch/sverk.launch`) должен быть в значении `true`:


```
<arg name="blocks" default="true"/>

```


## Запуск


Для того, чтобы открыть интерфейс блочного программирования, [подключитесь к Обрику по Wi-Fi](/learn/clover-2/connect-wi-fi) и перейдите на страницу [http://192.168.11.1/sverk_blocks/](http://192.168.11.1/sverk_blocks/) либо нажмите ссылку *Blocks programming* на [основной веб-странице](/learn/clover-2/connect-wi-fi#%D0%B2%D0%B5%D0%B1-%D0%B8%D0%BD%D1%82%D0%B5%D1%80%D1%84%D0%B5%D0%B9%D1%81).


Интерфейс выглядит следующим образом:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fblocks.png&sig=9d9e27e096190a6d00a5feefdaf8005a21ea9022475421f9865ec29dbf794a2c)



Соберите необходимую программу из блоков в меню слева а затем нажмите кнопку *Run* для ее запуска. Также вы можете просмотреть сгенерированный код на языке Python, переключившись во вкладку *Python*.


Кнопка *Stop* позволяет остановить программу. Нажатие кнопки *Land* также останавливает программу и сажает дрон.


## Сохранение и загрузка


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fsave.png&sig=151685cc1a4438570803105b3dce715a825c0f9ecb49601c20ab55ccd83a2e9c)



Для сохранения программы откройте меню справа сверху, выберите пункт меню *Save* и введите название программы. Название программы может содержать только латинские буквы, дефис, подчеркивание и точку. Все ранее сохраненные программы будут доступны в этом же меню.


На карте памяти сохраненные XML-файлы программ хранятся в каталоге `/catkin_ws/src/sverk/sverk_blocks/programs/`.


В этом же меню доступны примеры программ (подкаталог `examples`).


## Блоки


Набор блоков приблизительно аналогичен набору ROS-сервисов [API автономных полётов](/learn/clover-2/commands-offboard-flight). В этом разделе приведено описание некоторых из них.


Блоки поделены на 4 категории:

- <span style=“padding:2px;color:white;background:#9d5ca6”>Flight</span> – команды, имеющие отношение к полёту.
- <span style=“padding:2px;color:white;background:#ff9b00”>State</span> – блоки, позволяющие получить те или иные параметры текущего состояния коптера.
- <span style=“padding:2px;color:white;background:#01d754”>LED</span> – блоки для управления [LED-лентой](/learn/clover-2/leds).
- <span style=“padding:2px;color:white;background:#5b97cc”>GPIO</span> – блоки для работы с [GPIO-пинами](/learn/clover-2/gpio).

В остальных категориях находятся стандартные блоки Google Blockly.


### take_off


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Ftake-off.png&sig=b804a22d8c5e059a15bfd56a13cf2f1f0db8e77af9f31887c1ce3d5113a94d1a)



Взлететь на указанную высоту в метрах. Высота может быть произвольным блоком, возвращающим числовое значение.


Флаг `wait` определяет, должен ли дрон ожидать окончания взлета перед выполнением следующего блока.


### navigate


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fnavigate.png&sig=ff6174bbb04e78a7630d5aab763c266b76b02758e3bf8220d59ee6307b84aa5a)



Прилететь в заданную точку. Координаты точки задаются в метрах.


Флаг `wait` определяет, должен ли дрон ожидать завершения полёта в точку перед выполнением следующего блока.


#### Поле *relative to*


В блоке может быть выбрана [система координат](/learn/clover-2/frames), в которой задана целевая точка:

- *body* – координаты относительно коптера: вперед (*forward*), влево (*left*), вверх (*up*).
- *markers map* – система координат, связанная с [картой ArUco-маркеров](/learn/clover-2/aruco-map).
- *marker* – система координат, связанная с [ArUco-маркером](/learn/clover-2/aruco-marker); появляется поле для ввода ID маркера.
- *last navigate target* – координаты относительно последней заданной точки для навигации.
- *global* – глобальная система координат (широта и долгота) и относительная высота.
- *global, WGS 84 alt.* – глобальная система координат и высота в [системе WGS 84](https://ru.wikipedia.org/wiki/WGS_84).

### land


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fland.png&sig=943aff8ea22c3c10344c7d8505b01fdf47d8e76d9ca2f83b6068d2982d7076b3)



Произвести посадку.


Флаг `wait` определяет, должен ли дрон ожидать окончания посадки перед выполнением следующего блока.


### wait


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fwait.png&sig=3eaa05e333f02ba1573a7e3d1b63f919f314e107b07b00fc3a528a36f244b1e8)



Ожидать заданное время в секундах. Время ожидания может быть произвольным блоком, возвращающим числовое значение.


### wait_arrival


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fwait-arrival.png&sig=9f4d731ff3f80f4b894d986014ef3e76b796a71ed328a7a0b548c9ee6f3b8c77)



Ожидать, пока дрон долетит до целевой точки (заданной в [navigate](#navigate)-блоке).


### get_position


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fget-position.png&sig=816326c35a48ce43809e88510361974b0c26c1723442e20b768b2634ff9ad42d)



Блок позволяет получить позицию, скорость и угол по рысканью дрона в заданной [системе координат](#relative_to).


### set_effect


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Fset-effect.png&sig=55e2acbde68c0fdbe160412c258d1b07893afb9f9babe7df2a8a7d083c0cb7aa)



Блок позволяет устанавливать различные анимации на LED-ленту аналогично [ROS-сервису `set_effect`](/learn/clover-2/leds#%D0%B2%D1%8B%D1%81%D0%BE%D0%BA%D0%BE%D1%83%D1%80%D0%BE%D0%B2%D0%BD%D0%B5%D0%B2%D0%BE%D0%B5-%D1%83%D0%BF%D1%80%D0%B0%D0%B2%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BB%D0%B5%D0%BD%D1%82%D0%BE%D0%B9).


Пример использования блока для установки случайного цвета (блоки, связанные с цветами находятся в категории *Colour*):


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fblocks%2Frandom-color.png&sig=9b7f2946bd4f61d08dc19c69ab630025110ef70c5ce40cd91dddd198f7851da2)



### Работа с GPIO


Категория <span style=“padding:2px;color:white;background:#5b97cc”>GPIO</span> содержит блоки для работы с GPIO. Обратите внимание, что для корректной работы этих блоков демон для работы с GPIO `pigpiod` должен быть включен:


```
sudo systemctl enable pigpiod.service
sudo systemctl start pigpiod.service

```


Более подробную информацию о GPIO читайте в [соответствующей статье](/learn/clover-2/gpio).
