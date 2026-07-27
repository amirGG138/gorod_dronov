# Инструкция по сборке конструктора программируемого квадрокоптера «Обрик»

> Раздел: Обрик ROS 1 (Clover) · slug: `assemble`
> Источник: https://edu.sverk.tech/learn/clover-2/assemble

---

# Инструкция по сборке конструктора программируемого квадрокоптера «Обрик»


## Этап 1: Подготовка и пайка силовых компонентов


### Шаг 1. Лужение проводов двигателей

-

Выпрямите провода на четырех бесколлекторных моторах, чтобы жилы не были перекручены

-

Отрежьте коннектор проводов моторов вплотную к коннектору

-

Снимите 2-3 мм изоляции с провода


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcut_motors_lines.svg&sig=a3230c73c4142f4ae0eeac0403a708015b95e2ab66fc0208c1294b4b5801b93b)


-

Нанесите флюс и залудите кончики всех проводов


>

**Caution** Выпрямите оголённые провода. Никогда не перекручивайте жилы оголенного провода.


### Шаг 2. Подготовка конденсатора

-

Возьмите электролитический конденсатор. Определите полярность (длинная ножка — плюс)

-

Вставьте в отверстия на плате регулятора скорости оборотов (ESC) , зафиксируйте на 10-12 мм, соблюдая полярность


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2Bcondenser1.svg&sig=861ccfd30bee7a0b217e6775be10e240d38e354b774ba0f49ee3917998955e85)



>

**Caution** Модель конденсатора может отличаться длиной

- Согните ножки под углом 90 градусов так, чтобы конденсатор мог лечь на плату горизонтально

### Шаг 3. Пайка конденсатора к ESC

-

Припаяйте ножки конденсатора к регулятору скорости (ESC)

-

Отрежьте лишнюю длину ножек бокорезами


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2Bcondenser2.svg&sig=9ca652af5ff603984250c3ceeb657d27ca58eb43e7afbe0e6ddf44045eb9b6ee)


-

Залудите контактные площадки регулятора скорости оборотов (ESC)


### Шаг 4. Пайка силового кабеля к ESC

- Припаяйте силовые кабели к контактным площадкам питания регулятора скорости оборотов платы (ESC)

>

**Info** Красный провод к плюсу (+), черный к минусу (-)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2Bsupply.svg&sig=3995a542e33426d77214684b32f090532429153f741f2d80d9e34ffc8c6f4845)



>

**Info** Обеспечьте качественный прогрев для надежного соединения

-

Наденьте термоусадку на конденсатор и усадите феном


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2Bshrinkable.svg&sig=9d6e962d053e266d9ef68fc92659904da4c9a8f06190491f481b50d0182610db)



### Шаг 5. Сборка силового разъема XT30

- Предварительно наденьте термоусадку на провода
- Снимите 3-4 мм изоляции с силовых проводов
- Залудите концы толстых силовых проводов (красный и черный)
- Припаяйте их к разъему XT30

>

**Hint** Плоская грань разъема — обычно плюс, сверьтесь с маркировкой

-

Подвиньте термоусадки к месту пайки и усадите их феном


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2BX30.svg&sig=732931988e53d72e5bddd0bdda9bd5267b1541e99dcaaf951a4ff4e6a92996ce)


-

Следите, чтобы нагрев от фена не распаял разъём


### Шаг 6. Подготовка понижающих преобразователей (UBEC)

-

Возьмите два понижающих преобразователя (модуля UBEC) (для питания Raspberry Pi и периферии)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUBEC_5V-3A.svg&sig=06dfeb8546a08598515d412cf80ff7f56b59a2db4e43cc964d77670fe55e7050)


-

Наденьте термоусадочную трубку на платы UBEC и усадите их феном, чтобы избежать короткого замыкания


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUBEC_5V-3A%2B.svg&sig=3299983c60f55f47830a90479f2dfa67b641604b620f144a7fc3227578ffa2db)


-

Укоротите провода на входе UBEC до 25-30 мм

-

Зачистите и залудите концы

-

Спаяйте вместе два плюсовых провода от двух модулей в один, и два минусовых в один на выход


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUBEC_5V-3A%2B%2B.svg&sig=e47335a5b73fbfe8dd805bf9f05157f5a70970cac784efc81f2d36a20bc11d3a)



### Шаг 7. Пайка UBEC к ESC

- Припаяйте спаренные провода питания UBEC к тем же силовым площадкам на ESC, куда припаян основной кабель питания

>

**Info** удобнее паять с нижней стороны платы


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2BUBEC_5V-3A.svg&sig=718501b4264f9de19b3a5ee1526e8ac7a2db0f0871eca9cefb468dd29d8a632e)



![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2BUBEC_5V-3A_f.svg&sig=89db6337e92f329a5580d2dccabde0b3479228616de24257fe7fb5da36864dcb)



### Шаг 8. Пайка двигателей к ESC

-

Припаяйте по три провода от каждого двигателя к соответствующим тройкам контактных площадок по углам платы ESC

-

Порядок проводов внутри тройки не важен (направление вращения меняется программно)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2F%2Bmototrs.svg&sig=349fc53e73827b81a4230119becbc699fc562e3bbd1eb6c7468dd26c0e6008de)



### Шаг 9. Завершение подготовки ESC

-

Используя зубную щетку и средство Flux-OFF (или спирт), тщательно смойте остатки флюса с мест пайки на ESC

-

Соберите восьмиконтактный кабель: вставьте провода в адаптер

-

Закрутите и вставьте восьмиконтактный кабель в коннектор регулятора скорости


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fshleyf.svg&sig=74b7436c78a0f1980c914c617cb2037a2c3c93fdf7788d5041d3d13998e170a3)


-

Установите красные резиновые втулки в отверстия регулятора скорости оборотов


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fred_spindle.svg&sig=fa801a80fd6f5cfa91f867b73ffb5d054d514acb3577440784882d936434243a)



## Этап 2: Подготовка электроники управления


### Шаг 10. Подготовка радиоприемника управления

-

Припаяйте четыре провода (GND, 5V, RX, TX) к радиоприемнику


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Freceiver%2Blines.svg&sig=0c60bffd6131b3a1a823cb0a885a066199d010cf7410cd3ca75649b72d6c8e53)


-

Скрутите провода в жгут

-

Наденьте прозрачную термоусадку на приемник и нагрейте феном


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Freceiver.svg&sig=432f2a5ff20b0957ba16a7a09120791603f12a80014b88f02a223a0131776f87)


-

Припаяйте провода приемника к полётному контроллеру соответственно:

  - GND - G (черный)
  - 5V - 4V5 (красный)
  - TX - RX6 (жёлтый)
  - RX - TX6 (белый)

>

**Hint** По стандарту UART всегда идет соединение TX→RX, а RX→TX


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Freceiver%2Bmatek.svg&sig=c96142185f8b5dba5b3ab9dcf151392b3120f8d22b78335d3bd32aeb8cc6314c)


-

Установите радиатор на микроконроллер

-

Установите прозрачные резиновые втулки в отверстия полётного контроллера, затем - металлические вутлки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fwhite-metal_spindle.svg&sig=beab397ed60b7b451d9cb72cccb43cb30ad62da532ef1961c4c7526d31ea0470)



## Этап 3: Сборка нижней рамы и установка собранного стека


### Шаг 11. Установка регулятора скорости

-

Вставьте в нижнюю раму в центральные 4 отверстия болты M2x25 и закрепите их винтами M2


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fm2x25.svg&sig=d06d54bc10256a66d1991eba31fa0b0172a7c15791cdce7c5510d235021a4f67)


-

Установите регулятор скорости оборотов на эти болты


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Belectro.png&sig=0bbfff91123580a6431950a94e2fb4d79153287b768de3bf40aca9c41fe603e4)



>

**Hint** Провода понижающих преобразователей проходит под регулятором скорости оборотов и оказываются на противоположной стороне от конденсатора


### Шаг 12. Установка моторов

-

Закрутите моторы на “лучах” рамы на винты M2x5, по два винта на мотор


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bmotors.png&sig=b3edb85658644b18751bd7886db5c4189c729b13482173aaf1014e5f3759e99f)


-

Закрепите провода моторов по одной стяжки на “луч” и через центральные разъёмы рамы - всего 8 * стяжек, отрезать излишки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fmotors_buckles.png&sig=ef8f26df3568d2bb548c28af1b853ab3c8aec9be7d6393b115f4ae5b5973d0df)



>

**Hint** Хвостики стяжки должны смотреть вниз

-

Зафиксируйте понижающие преобразователи стяжкой через специальные технологические отверстия рамы вместе, отрежьте излишки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2BUBEC.png&sig=ed3bee6e7969cca16b996eb2c92a754bafffcd6aa13d0c9c60db7fff67578e97)



>

**Hint** Хвостиком вверх

-

Установите последовательно на ранее установленные болты M2x25 силиконовые проставки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fred_spindle2.png&sig=50b405e882457a81f4eae9207b291d9f56b8fe24b0293e6fa0580a1ab097d740)



### Шаг 13. Монтаж регулятора скорости оборотов

-

Подключите восьмиконтактный кабель из регулятора скорости оборотов в полётный контроллер


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FESC%2BMatek.png&sig=b154b4b49f02dad708dc1b5a63e33e82e83a8d5fe95a927d1e6f71e1586c8f18)


-

Установите полётный контроллер, таким образом, чтоб восьмиконтактный кабель проходил между платами


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2BMatek.png&sig=ce8f93684013d15c4c5ba95c971dd5f54119c3641c1f86fc70069d69f026f71c)



>

**Hint** Разъем полётного контроллера для восьмиконтактного кабеля смотрит в сторону конденсатора

-

Закрутите болты M2x25 винтами M2


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fmain_electro.png&sig=c6910a4cd42e0e2f471bd6609a74729debbacf4f265b15dee0273a06214f3948)


-

Зафиксируйте приёмник за конденсатор контроллера регулятора полётов стяжкой


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Ffix_receiver.png&sig=996231b17eab51a114c5b1bd810501a1a8b0986d1c1f5d54fe622911bf18b3b2)



### Шаг 14. Установка SD карты и подключение USB

-

Установите SD-карту 16GB в полётный контроллер

-

Установите провод microUSB - USB через отверстие нижней рамы в полётный контроллер


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUSB-Matek.png&sig=32a6c8c11c189bda2dfa35d33c8bdc35a00a9d3fe905007f72ef7bd49e6ba3ef)



>

**Hint** Можно проверить правильность собранной электрической схемы подключением мультиметра


## Этап 4: Установка микрокомпьютера


### Шаг 15. Подготовка плат

-

Вставьте в материнскую плату коннектор-гребенку(2*20 пинов) и припаяйте с обратной стороны платы


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcomp-mode.svg&sig=d18224187da2e1c8f6c82d8b5042a58e07d5f7dafff776e4cc3948aa563315c1)


-

Соедините Raspberry Pi с материнской платой


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fraspberry%2Bcomp-mode.svg&sig=1a55beaa843e828b77fe417aeac6a0f882a346ca8d86d735d35463193407638e)



>

**Hint** Следите за контактными площадками

-

Нанесите термопасту на процессор и оперативную память Raspberry Pi


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcomp-mode%2Bterm.svg&sig=e74c67f47abe13e1d3d9a71134573efd3e093185c44e7babe919ed7a026e1dcd)



>

**Note** Для хорошего термоконтакта с радиатором


### Шаг 16. Сбор компьютерного модуля

-

Установите конструкцию в рамку радиатора и прижимы болтами M2x10


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcomp-mode%2Bits_construction.svg&sig=39aca61d2676d694141781bb6f22c3540e5ce20285b2967b8177d3deecb31c1a)



>

**Caution** Затяните болты, но не до конца, чтоб не повредить

-

Установите г-образный шлейф камеры:


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcomp-mode%2Bcamera_loop.svg&sig=3267832de01aeb6833d894a184ac763c0c48011402d022ac74139da6a468bdc5)



>

**Hint** Шлейф камеры вставляется в разъем Raspberry Pi контактами наружу, затем загните шлейф под радиатор


### Шаг 17. Монтаж компьютерного модуля

-

Устанавите под нижнюю раму вместе с проставкой и зафиксируйте 4мя болтами M2x10 через нижнюю раму


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bcomp-mode.png&sig=b51701a68c8e5ae866cf5f66b5f054cd35cf18043cf42b8af179a16ff242d537)



>

**Tips** Шлейф выходит с той же стороны, что и конденсатор, выемки проставки должны смотреть на радиатор

-

Подключите провод USB к Raspberry Pi


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUSB-raspberry.png&sig=cbd84b0431c1b06909270038cf1aaef542666a09cb1498af7de90053c186c67b)



## Этап 5. Установка камеры


### Шаг 18. Установка модуля

-

Установите корпус камеры на раму и закрутите болтами M2x6


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Blow_cam_mode.png&sig=830cecff8808444f95fbffec904fb3962d462e6ff1e012b12e96567d989122e9)



>

**Hint** Корпус камеры устанавливается со стороны понижающих преобразователей, закручивайте болты с небольшим усилием


### Шаг 19. Подключение проводов

-

Провода понижающих преобразователей проденьте через корпус камеры


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FUBEC-cam_mode.png&sig=9347ead8e1cee386c4d6f1a66b5bee63297ac261e11162227ae22ee0e627127b)


-

Шлейф в разъем камеры и с помощью 4х болтов M2x6 закрепите камеру внутри её модуля


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bcamera.png&sig=f8d9bf6b5e1a2b9637461a079c0d1981bff20216ee070c64fea65e398fbaae14)



## Этап 6. Сборка защит


### Шаг 20. Установка ножек

-

Установите ножки на 8 болтов M2х8 на концах лучей нижней рамы: по два болта на одно место соединения ножки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Blegs.png&sig=a239506abaa8f5f96dcc3f601ee21209397c10670ba39ccfb843803283b4503a)



### Шаг 21. Установка защит

-

Закрутите два болта M2х8 между “лучей” рамы


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bprotectors1.png&sig=0766ead6d4e45e1c27b19b80f170ed73c582a5c7278eeb7bd00bd3d2a3e738f5)


-

Закрутите два болта M2х12 через модуль камеры и нижней рамы в ножку защиты


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bprotectors2.png&sig=1a09962ff81c8164fbf23eb4c6a83b2004e923455681b8b8cd882f8b0a9bd2c2)


-

Закрутите два болта M2х10 с противоположной стороны через нижнюю раму


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Bprotectors3.png&sig=f6fdc0ea2871d9e39fcfab8b76d3388870c8ee1987a434b4f78e0deee4586b02)


-

Закрутите верхнюю деку в защиту 4 болтами M2x8


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Ftop_frame.png&sig=56b15c53c08d316bfc5a7bf46eacb996a7ce0909427bfe07c2d45023b2e78720)



### Шаг 22. Подключение RGB-ленты

-

Обрежьте провода не подключенного понижающего преобразователя (так, чтобы осталось 8 см)


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcut_UBEC.png&sig=0220d5da4fb7c3479ef347b8be95b5e1ddcc344d4df0f41375cf3cd58de6d5e8)


-

Скрутите два провода вместе и зачистите концы

-

Припаяйте два куска RGB-ленты между собой через провода (они примерно по 14,2 см). Припаяйте провод длиной ~10 см с разъемом “мама” к контакту * RGB-ленты


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Frgb-tipe.svg&sig=d2dcf61cde1f262060b2f1f438cbbb53f4a31c0c106aaeae809e80714a05310f)



>

**Caution** Соблюдите направление ленты

-

Проведите RGB-ленту через канал защиты и припаяйте провода не подключенного понижающего преобразователя к RGB-ленте


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FLED1.png&sig=7a3d04fe90f995d2227f47bf0c744d6753f0f172be4e29331212a0cc86b46723)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FLED2.png&sig=a89f244793b41b4e2c120245b5e44f150645c61f385b93c3f71fff8af721efa3)


-

Подключите к разъёму гребенки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2FLED%2Bcomp_mode.png&sig=b7a784497ace2a8537eb0c711ed0fc6f78eb854cd72926ca30d2aadeade3ad58)



### Шаг 23. Установка крышки камеры

-

Закрепите верхнюю крышку дрона на 2 болта M2x6


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2F%2Broof_cam.png&sig=51991e6922a8003f740635af76d00bf28a3604bd6e00cae904f03a9868a77fc3)



>

**Note** Туда можно установить любой датчик для кастомных проектов


## Заключительный этап


### Шаг 24. Установка датчика расстояния

-

Зачистите и припаяйте 4 провода типа Dupont по ~4 см в датчику расстояния


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fjust_laser.svg&sig=4e9e4d1160a451df5f5417ebc6660c769a30326367fd8aa675b48b1088b654ba)


-

Закрепите датчик расстояния снизу материнской платы двумя болтами M2x6 и двумя гайками M2


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Flow_frame%2Brange-finding_sensor.png&sig=02cff2174f14cfe12dd02c68535f51364097ec496ca275bdbc15062b6901b5c4)


-

Подключите к пинам гребенке материнской платы соотвественно (подробнее см. [Работа с лазерным дальномером](/learn/clover-2/laser)):

  - VSS - 3v3 (красный)
  - GND - GND (черный)
  - SCL - GPIO1 (жёлтый)
  - SDA - GPIO2 (белый)

![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Frange-finding_sensor-pins.png&sig=3744423f5edce9ecb80cf27db48fbeb3cef6f5a99ba9b21dd6120dabf607d224)



>

**Hint** Нанесите клей t700 на контактную площадку датчика расстояния для надёжности


### Шаг 25. Установка пропеллеров

-

Установите 4 пропеллера на моторы на 8 болтов M2x8: по 2 болта на пропеллера


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fprops.png&sig=8a1a1152dae028324df013ad2ddb709cfcc20165585dbcaf60d36cbb3f91bb10)



>

**Tips** При установке ориентируетесь по оси дроны так, чтобы они закручивались внутрь


### Финальный шаг - Питание

-

Подключите оставшиеся провода UBEC к пинам гребенки материнской платы


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fcharge_com-mode.png&sig=501542c6e9fa61fbd814af7059a5b28fcc6a6af4a0442f528a04cc50526aa92a)


-

Вставьте провода питания в аккумулятор


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fend.png&sig=48da5090b7aee906aae44b8af8cf8cc1348ba0dcdaccdb357c994d5c4597fa82)


-

Закрепите аккумулятор лентой-липучкой за верхнюю раму


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fassemble%2Fend2.png&sig=363ed419d1de8dda732c2565b584d5325c561228a8735e61ed15a6a7df9312e6)
