# Бортовые компьютеры

> Раздел: Обрик ROS 2 · slug: `boards-overview`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/boards-overview

---

# Бортовые компьютеры


Здесь собраны инструкции для всех поддерживаемых бортовых компьютеров Обрика.


---


## Что такое бортовой компьютер и зачем он нужен


Дрон состоит из двух вычислительных блоков. Полётный контроллер следит за тем, чтобы дрон не упал — он работает в реальном времени и управляет моторами тысячи раз в секунду. Бортовой компьютер — второй блок: он запускает ROS 2, обрабатывает данные с камер, принимает команды по Wi-Fi и передаёт их полётному контроллеру.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fcontrol-chain.svg&sig=be46e9cfc9db93611fdce89ca77e5d636339fcef56e339201e33a7eb7d207804)



## Чем Compute Module отличается от стандартного Raspberry Pi


Стандартный Raspberry Pi — это плата со всеми компонентами сразу: процессором, памятью, USB-портами, HDMI.


**Compute Module (CM5)** — это только вычислительный модуль: процессор, оперативная память и флеш-память, упакованные в маленький модуль без лишних разъёмов. Разъёмы находятся на отдельной плате расширения, которую можно сделать любой формы и размера. Для дрона это идеально: плата расширения Обрика занимает всего 55 x 40 мм и весит около 20 граммов.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2Fdiagrams%2Fcompute-module-vs-pi.svg&sig=ee8c623358d2f8a4753578afb8b06e3af89459041094c0c7e364ba64e0e398f9)



## Поддерживаемые платформы


Обрик работает с несколькими разными бортовыми компьютерами. Выберите свой:

- [Raspberry Pi CM5 (BCM2712)](/learn/obrik-ros-2/board-rpi-cm5)
- [Radxa CM5 (RK3588S)](/learn/obrik-ros-2/board-radxa-cm5)
- [Orange Pi Zero 3W (Allwinner A733)](/learn/obrik-ros-2/board-opi-zero3w)
- [Orange Pi 5 Pro (RK3588S)](/learn/obrik-ros-2/board-opi-5pro)
- [Horizon RDK X3 (Sunrise X3 + BPU)](/learn/obrik-ros-2/board-rdk-x3)

Перейдите в раздел, который соответствует вашему модулю.


>

**Примечание** Для Raspberry Pi CM5 и Orange Pi Zero 3W есть краткие руководства быстрого старта: [`quick_start_rpi.md`](../dev/quick_start_rpi.md) и [`quick_start_orangepi_zero3w.md`](../dev/quick_start_orangepi_zero3w.md).


---


## Интерфейсы и пути устройств по платам


Все платы дают одни и те же интерфейсы (UART, SPI, GPIO, камера), но в Linux они называются по-разному — отсюда разные пути `/dev/...`. Внутри контейнера `sverk_ros2` пути те же, что на хосте.

|  Интерфейс |  RPi CM5 |  Orange Pi Zero 3W |  Orange Pi 5 Pro |
|  UART_A (PX4) |  /dev/ttyAMA0 |  /dev/ttyS2 |  /dev/ttyS0 |
|  UART_B (свободен) |  /dev/ttyAMA10 |  /dev/ttyS6 |  /dev/ttyS1 |
|  SPI (LED-лента) |  /dev/spidev1.0 |  /dev/spidev3.0 |  /dev/spidev1.0 |
|  GPIO |  /dev/gpiochip0 |  /dev/gpiochip0 |  /dev/gpiochip0 |
|  CSI-камера |  cam0 (videocore) |  CAM1 (vin_v4l2) |  CAM1 (rkisp1) |


Что означает каждая строка:

- **UART_A (PX4)** — аппаратный последовательный порт, по которому бортовой компьютер общается с полётным контроллером (протокол uXRCE-DDS). **Занят системой — не подключайте сюда свои устройства.**
- **UART_B (свободный)** — второй UART для вашей периферии: Arduino, GPS, лидар. Именно его указывают при подключении внешних serial-устройств.
- **SPI** — быстрая шина, к которой подключена адресуемая светодиодная лента WS2812B.
- **GPIO** — контроллер пинов общего назначения (кнопки, светодиоды, сервоприводы, электромагнит). На всех платах одинаков — `/dev/gpiochip0`.
- **CSI-камера** — драйвер MIPI-камеры. Имя драйвера у каждой платы своё, но ROS 2 топик камеры везде один и тот же — `/camera_1/image_raw`, поэтому код от платы не зависит.

>

**Примечание** Здесь — три основные платы. Полный перечень файлов `/dev` по всем платформам (включая Radxa CM5 и RDK X3) и как их искать → [Устройства /dev](/learn/obrik-ros-2/devices-raw).
