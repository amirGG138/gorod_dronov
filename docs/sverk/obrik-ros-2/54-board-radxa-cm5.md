# Radxa CM5 с платой Waveshare CM4-NANO-B/C

> Раздел: Обрик ROS 2 · slug: `board-radxa-cm5`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/board-radxa-cm5

---

# Radxa CM5 с платой Waveshare CM4-NANO-B/C


Этот раздел описывает настройку бортового компьютера на базе Radxa Compute Module 5: установите операционную систему, подключите камеру, настроите Docker и соедините с полётным контроллером.


---


## Чем Radxa CM5 отличается от Raspberry Pi CM5


Оба модуля — это вычислительные модули без лишних разъёмов, которые вставляются в плату расширения. Radxa CM5 использует процессор Rockchip RK3588S — тот же, что стоит в Orange Pi 5 Pro. Он мощнее, но и настраивается немного по-другому. Главное отличие в настройке: на Radxa большинство параметров меняются через утилиту `rsetup`, а не вручную через файлы конфигурации.


---


## 1. Установка операционной системы


### 1.1. Скачайте образ

- Зайдите на страницу загрузок Radxa: [https://docs.radxa.com/en/som/cm/cm5/download](https://docs.radxa.com/en/som/cm/cm5/download)
- Скачайте образ **Radxa OS (Debian Bookworm CLI)**. Пример ссылки:

```
https://github.com/radxa-build/radxa-cm5-rpi-cm4-io/releases/download/rsdk-b3/radxa-cm5-rpi-cm4-io_bookworm_cli_b3.output.img.xz

```


### 1.2. Подготовь карту памяти

- Отформатируйте карту microSD через **SD Memory Card Formatter** ([скачать](https://files.waveshare.com/upload/d/d7/Panasonic_SDFormatter.zip)).
- Распакуйте образ:

```
unxz radxa-cm5-rpi-cm4-io_bookworm_cli_b3.output.img.xz

```

- Запустите **balenaEtcher** от имени администратора.
- Выберите распакованный файл `.img`, укажите карту microSD и нажмите Flash.
- Дожди завершения записи и проверки.

### 1.3. Первый запуск


#### Включите SSH


**Что такое SSH?** SSH — это способ управлять компьютером дрона с ноутбука по сети, как будто вы сидите прямо за ним.


По умолчанию SSH в образе Radxa выключен. Включить его можно до первого запуска:

- Снова подключите записанную карту к компьютеру.
- На разделе `boot` откройте файл `before.txt` и отредактируйте его:

```
# disable_service ssh
# disable_service ssh.socket
# if headless enable_service ssh
enable_service ssh

```


#### Подключитесь к плате

- Вставьте карту в плату Waveshare, подключите питание и сетевой кабель.
- Узнайте IP-адрес платы через интерфейс роутера или утилиту сканирования сети.
- Подключитесь по SSH:

```
ssh rock@<IP_АДРЕС_ПЛАТЫ>

```
 **Логин:** `rock`, **Пароль:** `rock`

#### Обновите систему


```
sudo rsetup

```


В меню утилиты: **System -> System Update -> Yes**. После завершения перезагрузите систему:


```
sudo reboot

```


---


## 2. Настройка камеры


>

**Внимание** На Radxa CM5 настройка камеры выполняется только через утилиту `rsetup`. Ручное редактирование конфигурационных файлов не поддерживается.


Проверенные конфигурации:

- Сенсор **IMX219** (плата Waveshare CM4-NANO-C)
- Сенсор **OV5647** (плата Waveshare CM4-NANO-B)

### 2.1. Активируйте драйвер камеры


```
sudo rsetup

```

- В главном меню: **Overlays -> (Yes) -> Manage overlays**
- Найдите нужный сенсор:
  - Для IMX219: `Enable Raspberry Pi Camera V2 on CAM0`
  - Для OV5647: `Enable Raspberry Pi Camera V1.3 on CAM0`
- Нажмите **ПРОБЕЛ**, чтобы отметить пункт галочкой `[*]`
- Нажмите `Enter`, затем `Ok`
- Выберите **Rebuild overlays -> Yes**
- Выйдите клавишей `Esc` и перезагрузитесь:

```
sudo reboot

```


### 2.2. Установите инструменты для работы с камерой


```
sudo apt-get update
sudo apt-get install -y v4l-utils gstreamer1.0-tools \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav ffmpeg

```


### 2.3. Проверьте камеру


После перезагрузки камера доступна как `/dev/video11`.


Просмотр доступных режимов:


```
v4l2-ctl -d /dev/video11 --list-formats-ext

```


Запись тестового видео для IMX219 (640x480):


```
v4l2-ctl -d /dev/v4l-subdev2 --set-ctrl exposure=2000
v4l2-ctl -d /dev/video11 --set-fmt-video=width=640,height=480,pixelformat=NV12
gst-launch-1.0 -q v4l2src device=/dev/video11 num-buffers=900 ! \
    video/x-raw,format=NV12,width=640,height=480 ! \
    videoconvert ! jpegenc ! avimux ! filesink location="test_imx219.avi"

```


Запись тестового видео для OV5647 (1920x1080):


```
gst-launch-1.0 v4l2src device=/dev/video11 io-mode=4 ! \
    videoconvert ! video/x-raw,format=NV12,width=1920,height=1080 ! \
    jpegenc ! avimux ! filesink location="test_ov5647.avi"

```


Поддерживаемые разрешения:

|  Сенсор IMX219 (~21 FPS) |  Сенсор OV5647 (~15 FPS) |
|  640x480 |  640x480 |
|  800x600 |  800x600 |
|  1024x768 |  1024x768 |
|  1280x720 |  1280x720 |
|  1280x960 |  1280x960 |
|  1600x1200 |  1600x1200 |
|  1920x1080 |  1920x1080 |
|  2592x1944 |  2592x1944 |
|  3280x2464 |  нет |


---


## 3. Установка Docker


### Подготовка


```
sudo apt update
sudo apt install ca-certificates curl

```


### Добавьте GPG-ключ Docker


```
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

```


### Добавьте репозиторий Docker


```
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

```


### Установите Docker


```
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

```


### Проверьте установку


```
sudo systemctl status docker

```


Строка `active (running)` — всё работает.


### Настройте права доступа


```
sudo usermod -aG docker $USER
sudo usermod -aG dialout $USER
sudo usermod -aG tty $USER
sudo usermod -aG i2c $USER
sudo usermod -aG video $USER
sudo usermod -aG gpio $USER
sudo reboot

```


Документация: [Официальная инструкция по установке Docker](https://docs.docker.com/engine/install/debian/)


---


## 4. Подключение полётного контроллера (Matek H743 Mini V3)


### 4.1. Физическое подключение

|  Контакт на Waveshare CM4-NANO-B/C |  Контакт на Matek H743 Mini V3 |
|  TXD (UART2_TX_M0, Pin 8) |  RX4 |
|  RXD (UART2_RX_M0, Pin 10) |  TX4 |
|  Любой GND |  GND |


[Распиновка CM5](https://docs.radxa.com/en/som/cm/cm5/hardware/hw-interface#gpio-interface)


### 4.2. Настройка UART через rsetup


```
sudo rsetup

```

- **Overlays -> (Yes) -> Manage overlays**
- Найдите и выберите пробелом `Enable UART2-M0`
- Пересоберите оверлеи и перезагрузитесь

После перезагрузки проверьте, что порт появился:


```
ls -la /dev/ttyS2

```


Добавьте пользователя в группу dialout:


```
sudo usermod -aG dialout $USER

```


Для применения изменений нужно переподключиться по SSH.


### 4.3. Проверка связи (опционально)


```
sudo apt install minicom
sudo minicom -D /dev/ttyS2 -b 921600

```


---


## 5. Настройка Wi-Fi


### 5.1. Установка драйвера для TP-LINK TL-WN725N


Адаптер TP-LINK TL-WN725N (чип Realtek RTL8188EUS) требует отдельного драйвера.


Убедитесь, что система видит адаптер:


```
lsusb | grep -i realtek

```


Ожидаемый вывод:


```
Bus 001 Device 003: ID 0bda:8179 Realtek Semiconductor Corp. RTL8188EUS 802.11n Wireless Network Adapter

```


Установите драйвер:


```
sudo apt update
sudo apt install -y git build-essential dkms linux-headers-$(uname -r)

git clone https://github.com/petayyyy/rtl8188eus.git
cd rtl8188eus

sudo make clean
sudo make all -j$(nproc)
sudo make install

sudo modprobe 8188eu

```


Проверьте установку:


```
lsmod | grep 8188
ip a | grep -A 2 wl

```


После установки появится сетевой интерфейс с именем вида `wlxXXXXXXXXXXXX`.


### 5.2. Подключение к Wi-Fi через nmcli


`nmcli` — это утилита управления сетью в командной строке.


Просмотр доступных сетей:


```
sudo nmcli device wifi list

```


Подключение к сети:


```
sudo nmcli connection add type wifi con-name "Router" \
  ifname <имя_интерфейса> ssid "Router_name" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "Router_password" \
  connection.autoconnect yes

```


Создание нескольких профилей с приоритетами:


```
# Домашняя сеть (высший приоритет)
sudo nmcli connection add type wifi con-name "Wifi" \
  ifname <имя_интерфейса> ssid "Wifi" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "11111111" \
  connection.autoconnect yes connection.autoconnect-priority 100

# Сеть "Poletka" (средний приоритет)
sudo nmcli connection add type wifi con-name "Poletka" \
  ifname <имя_интерфейса> ssid "Poletka" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "sosatusa" \
  connection.autoconnect yes connection.autoconnect-priority 50

```


Управление профилями:


```
nmcli connection show             # список профилей
sudo nmcli connection up "Имя"    # активировать
sudo nmcli connection down "Имя"  # деактивировать
sudo nmcli connection delete "Имя" # удалить

```


### 5.3. Графический интерфейс (альтернатива)


```
sudo nmtui

```


В меню выберите **Activate a connection**, потом свою сеть и введите пароль.


### 5.4. Устранение неполадок с Wi-Fi


Если адаптер не появился после установки драйвера:


```
sudo rmmod 8188eu
sudo modprobe 8188eu
sudo systemctl restart NetworkManager

```


---


## 6. Работа с GPIO


```
sudo apt install gpiod libgpiod-dev python3-libgpiod

```


Основные команды:

- `gpiodetect` — список GPIO-чипов
- `gpioinfo` — состояние линий GPIO
- `gpioset`, `gpioget` — установить и прочитать состояние пина

[Распиновка CM5](https://docs.radxa.com/en/som/cm/cm5/hardware/hw-interface#gpio-interface)


---


## 7. Системное администрирование


### Мониторинг температуры


Создайте файл `temp.sh`:


```
#!/bin/bash
cpu_temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp)
cpu_temp_c=$(echo "scale=1; $cpu_temp_raw / 1000" | bc)
echo "CPU Temperature: $cpu_temp_c°C"

```


Запустите:


```
chmod +x temp.sh
./temp.sh

```


### Базовые команды

- `sudo shutdown -h now` — безопасное выключение
- `sudo reboot` — перезагрузка
- `sudo systemctl status <имя_сервиса>` — состояние сервиса

Всегда выключайте плату через команду, а не прямым отключением питания: иначе файловая система на SD-карте может повредиться.


---


## 8. Полезные ресурсы

- [Radxa CM5 — официальная документация](https://docs.radxa.com/en/som/cm/cm5)
- [Waveshare CM4-NANO-C](https://www.waveshare.com/wiki/CM4-NANO-C)
- [Waveshare CM4-NANO-B](https://www.waveshare.com/wiki/CM4-NANO-B)
- [Форум поддержки Radxa](https://forum.radxa.com/)
- [Репозиторий Radxa на GitHub](https://github.com/radxa/)
