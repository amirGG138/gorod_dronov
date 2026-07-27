# Инструкция по сборке конструктора программируемого квадрокоптера «Обрик»

> Раздел: Обрик ROS 2 · slug: `assemble`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/assemble

---

# Инструкция по сборке конструктора программируемого квадрокоптера «Обрик»


## Этап 1: Подготовка и пайка силовых компонентов


### Шаг 1. Лужение проводов моторов

-

Выпрямите провода на четырёх бесколлекторных моторах, чтобы жилы не были перекручены

-

Отрежьте коннектор проводов моторов вплотную к коннектору

-

Снимите 2-3 мм изоляции с провода


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcut_motors_lines.svg&sig=c930e55683a4b1b54d2a750d49f119d5aea77e6cc8ed5ad70f940ff58041df1d)


-

Нанесите флюс и залудите кончики всех проводов


>

**Внимание** Выпрямите оголённые провода. Никогда не перекручивайте жилы оголённого провода.


### Шаг 2. Подготовка конденсатора

-

Возьмите электролитический конденсатор. Определите полярность (длинная ножка — плюс)

-

Вставьте в отверстия на плате регулятора скорости оборотов (ESC), зафиксируйте на 10-12 мм, соблюдая полярность


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2Bcondenser1.svg&sig=e936c7290754efe883004f00ae3cf44af175c8a80c891f5829804b3dccad7182)



>

**Примечание** Модель конденсатора может отличаться длиной

- Согните ножки под углом 90 градусов так, чтобы конденсатор мог лечь на плату горизонтально

### Шаг 3. Пайка конденсатора к ESC

-

Припаяйте ножки конденсатора к регулятору скорости (ESC)

-

Отрежьте лишнюю длину ножек бокорезами


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2Bcondenser2.svg&sig=fd6c746d6c75482c24ac5b39023d8f371ad810d528380c95549537e33ae57180)


-

Залудите контактные площадки регулятора скорости оборотов (ESC)


### Шаг 4. Пайка силового кабеля к ESC

- Припаяйте силовые кабели к контактным площадкам питания регулятора скорости оборотов платы (ESC)

>

**Примечание** Красный провод к плюсу (+), чёрный к минусу (-)


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2Bsupply.svg&sig=1818997d1fdaee260aae6fa1ed46d6f0a71cfa0973d3e2e8e9e5acd0303706f2)



>

**Примечание** Обеспечьте качественный прогрев для надежного соединения

-

Наденьте термоусадку на конденсатор и усадите феном


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2Bshrinkable.svg&sig=131958d84d73d046835616867c8b771a9be9f4c441efb7ed8cf4d9f208840a7d)



### Шаг 5. Сборка силового разъёма XT30

-

Припаяйте силовой разъём XT30 к плате распределения питания


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcharge.svg&sig=667c5ff675556f7cac094fb3a53eef2bc08d90e6a0e703234caa283c963c76c8)



>

**Подсказка** Плоская грань разъёма — обычно плюс, сверьтесь с маркировкой

-

Залудите концы толстых силовых проводов (красный и чёрный)

-

Припаяйте их к силовому разъёму XT30


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fesc%2Badapter.svg&sig=ed544b60acb1f93d99cb327b35758841d3f98d4a6b0806cd92b5a390fd6a7087)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fesc%2Badapter2.svg&sig=0ae201220344fbcf5893d00cea792a895d5372e619b3315f5e7ce5c4227657c7)



### Шаг 6. Подготовка понижающих преобразователей (2BEC-B)

-

Возьмите понижающий преобразователь (модуль 2BEC-B)


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2F2BEC.png&sig=c6ed06fb1c40a9da9ff69d9784f84e11d591971796c928a09005747e284319ce)


-

Возьмите адаптер Z1.5 мама (для led-ленты), отрежьте провода питания до ~2 см, а третий провод оставьте ~12 см (в дальнейшем идущий в Orange Pi)

-

Припаяйте провода питания к понижающему преобразователю


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2F2BEC%2BLED.png&sig=e4e756188f1583f9247b2957fc943a6d1ad306493bf3c70e34d9b928560b24b2)


-

Обожмите оставшийся провод в dupont 2.54


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2F2BEC%2BLED2.png&sig=955191cc4d122a99708ec35645a99bd030b6b7e04b657380ff57bb05aa01f3a9)


-

Укоротите провода на входе UBEC до 25-30 мм

-

Зачистите и залудите концы

-

Спаяйте вместе два плюсовых провода от двух модулей в один, и два минусовых в один на выход


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FUBEC_5V-3A%2B%2B.svg&sig=935c57e814423584db430da0b2b2bfdf9633c34299020a2992134656ad253d8a)



### Шаг 7. Пайка UBEC к ESC

- Припаяйте спаренные провода питания UBEC к тем же силовым площадкам на ESC, куда припаян основной кабель питания

>

**Примечание** удобнее паять с нижней стороны платы


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2BUBEC_5V-3A.svg&sig=90db0d16f2c8172ed420701faf9b82b56657ece96c9580a20195fabd102f64e8)



![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2BUBEC_5V-3A_f.svg&sig=9d5d7c3cbefbf3dcfff16b14f12092f0bd557aa2b4422a44cdda7576ddd35308)



### Шаг 8. Пайка моторов к ESC

-

Припаяйте по три провода от каждого мотора к соответствующим тройкам контактных площадок по углам платы ESC

-

Порядок проводов внутри тройки не важен (направление вращения меняется программно)


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2F%2Bmototrs.svg&sig=aef351ca40c1c40956f40ba49347d27999bdf81a4edc8c2b93208ad44629d55f)



### Шаг 9. Завершение подготовки ESC

-

Используя зубную щётку и средство Flux-OFF (или спирт), тщательно смойте остатки флюса с мест пайки на ESC

-

Соберите восьмиконтактный кабель: вставьте провода в адаптер

-

Закрутите и вставьте восьмиконтактный кабель в коннектор регулятора скорости


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fshleyf.svg&sig=9f15271f05efbfeb14224c59d0e71f21888a89caba1b0aa3d159d9ea041eeb78)


-

Установите красные резиновые втулки в отверстия регулятора скорости оборотов


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fred_spindle.svg&sig=23ceae4ec5d7626bd7b9e3b2d9850eed28a4559e4b458305cba9cad6dccb8e47)



## Этап 2: Подготовка электроники управления


### Шаг 10. Подготовка радиоприёмника управления

-

Припаяйте четыре провода (GND, 5V, RX, TX) к радиоприёмнику


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Freceiver%2Blines.svg&sig=94c361a8d8cb7c3a8eb0482199c79b02f5b544bb9c21f7081d0134f01d8f1c31)


-

Скрутите провода в жгут

-

Наденьте прозрачную термоусадку на приёмник и нагрейте феном


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Freceiver.svg&sig=46f11e45954583deb4d059ef33f91eb7fa4e47ed637e1a2ead5f9e32ec4ec906)


-

Припаяйте провода приёмника к полётному контроллеру соответственно:

  - GND - G (чёрный)
  - 5V - 4V5 (красный)
  - TX - RX6 (жёлтый)
  - RX - TX6 (белый)

>

**Подсказка** По стандарту UART всегда идёт соединение TX→RX, а RX→TX


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Freceiver%2Bmatek.svg&sig=b17cc3d15e9cf212038aac251e3928cd7f7bd5c1025a032c019281fe4b5d1efd)


-

Установите радиатор на микроконтроллер

-

Установите прозрачные резиновые втулки в отверстия полётного контроллера, затем — металлические втулки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fwhite-metal_spindle.svg&sig=f23049c5b03eaa0ecbac5101193df75d05e13983dcbda5e0b84ad94dc1acc1a4)



## Этап 3: Сборка нижней рамы и установка собранного стека


### Шаг 11. Установка регулятора скорости

-

Вставьте в нижнюю раму в центральные 4 отверстия болты M2x25 и закрепите их винтами M2


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fm2x25.svg&sig=fb265ce2e62aac004c0be79687dc8266d956157309f55215cb3d312b8e9e0847)


-

Установите регулятор скорости оборотов на эти болты


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Belectro.png&sig=5d19e1da13cebce575651f3bbafe7b772915627c5785fb9e4fd020c97dcd2307)



>

**Подсказка** Провода понижающих преобразователей проходят под регулятором скорости оборотов и оказываются на противоположной стороне от конденсатора


### Шаг 12. Установка моторов

-

Закрутите моторы на “лучах” рамы на винты M2x5, по два винта на мотор


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bmotors.png&sig=67c7b73721b0d83e5d6f1fa67d9d741e5b9e9fbfccdf9a3bf6594e50907df7bd)


-

Закрепите провода моторов по одной стяжке на “луч” и через центральные разъёмы рамы — всего 8 стяжек, отрезать излишки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fmotors_buckles.png&sig=3244bbc8aa7145d49249f875d48b53031e09792e4e138fcc6073e6980fbb93a6)



>

**Подсказка** Хвостики стяжки должны смотреть вниз

-

Зафиксируйте понижающие преобразователи стяжкой через специальные технологические отверстия рамы вместе, отрежьте излишки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2BUBEC.png&sig=13075f156508ee9117c11cb02376b5641dc499f8985df66983d466cb4b2517fd)



>

**Подсказка** Хвостиком вверх

-

Установите последовательно на ранее установленные болты M2x25 силиконовые проставки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fred_spindle2.png&sig=9012ab5a2cefd28be6e8e685c30d8ccad0e2515daa9f841ef465e0ad233e3559)



### Шаг 13. Монтаж регулятора скорости оборотов

-

Подключите восьмиконтактный кабель из регулятора скорости оборотов в полётный контроллер


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FESC%2BMatek.png&sig=ddde1b60787f39e66badfcde4417cad367c0ab7037b99b9e89f382d62759c100)


-

Установите полётный контроллер таким образом, чтобы восьмиконтактный кабель проходил между платами


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2BMatek.png&sig=63be9f6accbaec84efad05f8362ad4e8e15d78aba7a506c9e9601c2f1d9e62d8)



>

**Подсказка** Разъем полётного контроллера для восьмиконтактного кабеля смотрит в сторону конденсатора

-

Закрутите болты M2x25 винтами M2


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fmain_electro.png&sig=bb251b5c308a86d04ce41f024c9b183b0c47a92ae77c79d31e87260bca2fd1c3)


-

Зафиксируйте приёмник за конденсатор контроллера регулятора полётов стяжкой


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Ffix_receiver.png&sig=9f363534e10f9211a3e77ff17205b45ed8d565447442a70ea6305117669ccf0c)



### Шаг 14. Установка SD карты и подключение USB

-

Установите SD-карту 16GB в полётный контроллер

-

Установите провод microUSB - USB через отверстие нижней рамы в полётный контроллер


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FUSB-Matek.png&sig=f3d6953bafe19897955e7e115cbc377be132d309338012504583a494aad7ead5)



>

**Подсказка** Можно проверить правильность собранной электрической схемы подключением мультиметра


## Этап 4: Установка микрокомпьютера


### Шаг 15. Подготовка плат

-

Вставьте в материнскую плату коннектор-гребёнку (2*20 пинов) и припаяйте с обратной стороны платы


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcomp-mode.svg&sig=9dc7a02aacd661fcef5e1713b17d0a91fb7adaa4f5e4a3fb162afb66ab37080d)


-

Соедините Raspberry Pi с материнской платой


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fraspberry%2Bcomp-mode.svg&sig=b2c124ae5d334ec713332a4f3a08b79127ecb2615dd9305b7c60a7b387a0c295)



>

**Подсказка** Следите за контактными площадками

-

Нанесите термопасту на процессор и оперативную память Raspberry Pi


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcomp-mode%2Bterm.svg&sig=b06bb93998521575b15b19a464de6ee307c8d53e4c717f6253e6610150540a58)



>

**Примечание** Для хорошего термоконтакта с радиатором


### Шаг 16. Сбор компьютерного модуля

-

Установите конструкцию в рамку радиатора и прижимы болтами M2x10


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcomp-mode%2Bits_construction.svg&sig=1cc6f2370de0e7c8b327be4d7b0518eecba1e4272f547db4145d9a7392801041)



>

**Внимание** Затяните болты, но не до конца, чтобы не повредить

-

Установите г-образный шлейф камеры:


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcomp-mode%2Bcamera_loop.svg&sig=fb34ae2a794f236d2a63b74d385c19a47fc4da932e7aeecd8fa1ff7ac2cd7b64)



>

**Подсказка** Шлейф камеры вставляется в разъём Raspberry Pi контактами наружу, затем загните шлейф под радиатор


### Шаг 17. Монтаж компьютерного модуля

-

Установите под нижнюю раму вместе с проставкой и зафиксируйте 4 болтами M2x10 через нижнюю раму


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bcomp-mode.png&sig=e14b2f8e80849199c299e57cb9a8052b394c7aa3c996fef5c6ca55caa4411c6a)



>

**Подсказка** Шлейф выходит с той же стороны, что и конденсатор, выемки проставки должны смотреть на радиатор

-

Подключите провод USB к Raspberry Pi


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FUSB-raspberry.png&sig=e2da1aca92bea1dd83c4b2f183e5b2f9ebb267376e03c32a2ff4b96872fe8840)



## Этап 5. Установка камеры


### Шаг 18. Установка модуля

-

Установите корпус камеры на раму и закрутите болтами M2x6


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Blow_cam_mode.png&sig=c1804b5e4c1c436e0f802f56cb82e1d323d72fb60f6c80e7728083e89830870a)



>

**Подсказка** Корпус камеры устанавливается со стороны понижающих преобразователей, закручивайте болты с небольшим усилием


### Шаг 19. Подключение проводов

-

Провода понижающих преобразователей проденьте через корпус камеры


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FUBEC-cam_mode.png&sig=f71bd7b5f5776b94a57c4f7f4c17c402dd8914b072137208b1cc78e81dfb55cc)


-

Шлейф в разъём камеры и с помощью 4х болтов M2x6 закрепите камеру внутри её модуля


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bcamera.png&sig=79a8b2586ee74e277a8d142c88bce53f1a2efd3ebb0d13308a02f12271687c67)



## Этап 6. Сборка защит


### Шаг 20. Установка ножек

-

Установите ножки на 8 болтов M2х8 на концах лучей нижней рамы: по два болта на одно место соединения ножки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Blegs.png&sig=c2d06c850600204568686d0873543808d4c352edcddbed8011588ad344115506)



### Шаг 21. Установка защит

-

Закрутите два болта M2х8 между “лучей” рамы


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bprotectors1.png&sig=3c921c9b27c9805642f1aac19c43e7cfdee0b08c988ce24a7d6601a80fbcb490)


-

Закрутите два болта M2х12 через модуль камеры и нижней рамы в ножку защиты


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bprotectors2.png&sig=4225854764a4a7766c79c66584c29443027f1168a9269a8609409c9b7704c44b)


-

Закрутите два болта M2х10 с противоположной стороны через нижнюю раму


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Bprotectors3.png&sig=260cbe96bf9db760bf638637804447c9d1bd3f206a2d214b783a3615171f4c54)


-

Закрутите верхнюю деку в защиту 4 болтами M2x8


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Ftop_frame.png&sig=844cd883e2c6ee2d458e9fddf04d92e8ed293bf78be35978b7eaafcbc1fccf33)



### Шаг 22. Подключение RGB-ленты

-

Обрежьте провода не подключенного понижающего преобразователя (так, чтобы осталось 8 см)


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcut_UBEC.png&sig=a89772999568e558fa307ffb76f8249f1690f67512ba159607a25838d0a3db49)


-

Скрутите два провода вместе и зачистите концы

-

Припаяйте два куска RGB-ленты между собой через провода (они примерно по 14,2 см). Припаяйте провод длиной ~10 см с разъёмом “мама” к контакту RGB-ленты


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Frgb-tipe.svg&sig=e880fc5bb49937aa1b651e26f127432cb38d8baa94f4797651009576e8f43619)



>

**Внимание** Соблюдите направление ленты

-

Проведите RGB-ленту через канал защиты и припаяйте провода не подключенного понижающего преобразователя к RGB-ленте


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FLED1.png&sig=4f9ee046b0146702d588f01f8c7c7e388572df3fea3be0c632e9517f43557704)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FLED2.png&sig=688c489bc75e075306896874e81a11c801ad0f5b65a508f9352b1b505c1bdf8d)


-

Подключите к разъёму гребёнки


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2FLED%2Bcomp_mode.png&sig=d8f94b143fb804d1f82ce56fb5876f990ad748744dc2d81e29b86a60df955ef4)



### Шаг 23. Установка крышки камеры

-

Закрепите верхнюю крышку дрона на 2 болта M2x6


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2F%2Broof_cam.png&sig=cce7fcde757e2e82280171d3d3f66e425e3e31a55b0c17621e22e79ecd2eacb2)



>

**Примечание** Туда можно установить любой датчик для кастомных проектов


## Заключительный этап


### Шаг 24. Установка датчика расстояния

-

Зачистите и припаяйте 4 провода типа Dupont по ~4 см к датчику расстояния


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fjust_laser.svg&sig=95f79e6335d13a0226b16f1075cbc0bd2c4b6915efe1e9b521e6207f5b949557)


-

Закрепите датчик расстояния снизу материнской платы двумя болтами M2x6 и двумя гайками M2


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Flow_frame%2Brange-finding_sensor.png&sig=56b05be3bb92d2fdf9e5da567a22b7565346a4c2b328d7417a805223bbbbfc4f)


-

Подключите к пинам гребёнки материнской платы соответственно (подробнее см. [Работа с лазерным дальномером VL53L1X](/learn/obrik-ros-2/sensor-vl53l1x)):

  - VSS - 3v3 (красный)
  - GND - GND (чёрный)
  - SCL - GPIO1 (жёлтый)
  - SDA - GPIO2 (белый)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Frange-finding_sensor-pins.png&sig=51cfd235e41e5817650e6c439c21877a444d1adc41b26095e4badd0f5538efd9)



>

**Подсказка** Нанесите клей t700 на контактную площадку датчика расстояния для надёжности


### Шаг 25. Установка пропеллеров

-

Установите 4 пропеллера на моторы на 8 болтов M2x8: по 2 болта на пропеллер


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fprops.png&sig=e01091f2314f403dcd957dbf83cd9003a9c227c6a88d1b03361a02045d60fd76)



>

**Подсказка** При установке ориентируйтесь по оси дрона так, чтобы они закручивались внутрь


### Финальный шаг - Питание

-

Подключите оставшиеся провода UBEC к пинам гребёнки материнской платы


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fcharge_com-mode.png&sig=f3e79c8ab6b60a75288020df36d40f6fa373fd35d2499908353f226ffb948e89)


-

Вставьте провода питания в аккумулятор


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fend.png&sig=d2a20267a86bbfaa20142897875d13f7f61ae1ebc3ea0dcefe901488a7ff6d5b)


-

Закрепите аккумулятор лентой-липучкой за верхнюю раму


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fassemble%2Fend2.png&sig=433debd63b347147d04983f0e150ad291c94bff6907cf1de600d062b53a0cc24)
