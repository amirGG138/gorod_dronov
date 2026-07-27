# Установка виртуальной машины

> Раздел: Обрик ROS 1 (Clover) · slug: `simulation-vm`
> Источник: https://edu.sverk.tech/learn/clover-2/simulation-vm

---

# Установка виртуальной машины


Для работы с дроном рекомендуется иметь [установленное окружение ROS](/learn/clover-2/ros) на своём компьютере. К сожалению, [установка ROS и симулятора](/learn/clover-2/simulation-native) сопряжена с рядом трудностей: требуется использовать операционную систему Ubuntu 20.04, процесс установки длительный и требует выполнения большого количества команд в терминале.


Для облегчения процесса настройки окружения мы предлагаем использовать виртуальную машину со всем необходимым для работы с дроном. В состав виртуальной машины входят:

- операционная система Ubuntu 20.04 с легковесной графической оболочкой XFCE;
- предустановленные пакеты ROS для работы с дроном;
- QGroundControl;
- предварительно настроенный симулятор Gazebo;
- среда разработки Visual Studio Code с плагинами для разработки на Python и C++.

>

**Info** Имя пользователя по умолчанию на виртуальной машине — `clover`, пароль — `clover`.


Виртуальная машина может использоваться как для запуска симуляторов, так и для работы с настоящим дроном.


## Скачивание


Скачать текущую версию виртуальной машины можно [в релизах репозитория виртуальной машины](https://github.com/CopterExpress/clover_vm/releases/latest).


## Установка виртуальной машины


Для запуска виртуальной машины разработчика требуется использовать одну из совместимых сред виртуализации: [VirtualBox](https://www.virtualbox.org/wiki/Downloads), [VMware Player](https://www.vmware.com/products/workstation-player.html), [VMware Workstation](https://www.vmware.com/products/workstation-pro.html).


>

**Note** На момент написания данной статьи VirtualBox не обеспечивал достаточный уровень совместимости с виртуальной машиной. Рекомендуется по возможности использовать VMware Player или VMware Workstation; дальнейшая инструкция будет преимущественно написана для VMware Player.


Убедитесь, что поддержка аппаратной виртуализации включена в настройках BIOS/UEFI вашего компьютера. Шаги для включения аппаратной виртуализации, как правило, описаны в руководстве пользователя компьютера. Проконсультируйтесь с производителем компьютера, если включить виртуализацию не получается.

-

Импортируйте архив виртуальной машины в среду виртуализации. Для VMware Player используйте опцию **Open a Virtual Machine**:


![Open dialog with clever-devel.ova selected](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F01_import_vm.png&sig=b4187350c29a9fd5688a445173b115c24f1441726f5908683e46c00bc36ae2fb)



>

**Note** При импорте архива, скорее всего, появится окно с предупреждением о формате виртуальной машины:
![Import failure dialog](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F02_import_failure.png&sig=a060a645d609ad74e76dc53433809ae57eeaa2521e8db8696e79157416e8101c)
 Это предупреждение можно игнорировать и нажать кнопку **Retry**.

-

Откройте окно настроек виртуальной машины и измените параметры для наилучшего соответствия основной системе:

  - увеличьте объём оперативной памяти, отводимый для виртуальной машины:
![Increasing avaliable memory](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F03_max_memory.png&sig=d71dcf2c9388959484920d40056431eed4f192e7805035a65c5dcd0e6a21b471)

  - увеличьте количество доступных процессорных ядер:
![Increasing cpu cores](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F04_core_count.png&sig=b9711dc532ef158db7701d88ef8dfc694a265b014a2a34993594a6d66c78f51f)

  - включите 3D-ускорение:
![Enabling 3D acceleration](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F05_3d_acceleration.png&sig=0a0a63c8013c9447302a275da92621ab7e789e47683e9527e500146087f41426)

  - включите использование USB 2.0/3.0:
![USB 3.0 controller](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F06_usb_3_0.png&sig=409cf6670148b09fa1edf8754c6a3004fa8904538d743089fa6f35c00bc2bb5e)

  - опционально включите режим “мост” для виртуального сетевого адаптера:
![Enabling bridge networking](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F07_bridge_networking.png&sig=6340357836e27492f426317afe266847e053bb2200e6a2d5a02bbacc34192b0f)


>

**Note** Режим “мост” может некорректно работать с некоторыми сетевыми адаптерами. Если в режиме “мост” вы не можете подключиться к дрону, используйте USB Wi-Fi-адаптеры, “проброшенные” в виртуальную машину.

-

Запустите виртуальную машину. Возможно, при первом запуске справа появятся сообщения об отсутствии поддержки 3D-ускорения со стороны основной системы:


![No 3D support from host](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F08_no_3d_acceleration.png&sig=222b5853cf43fe7f15bfe62e95cb86d69b11ac198f4703507c1ff9081de4f78c)



В этом случае убедитесь, что у вас установлены самые последние драйверы для видеокарты в основной системе. Если сообщения появляются при повторных запусках виртуальной машины, добавьте строку


```
mks.gl.allowBlacklistedDrivers = "TRUE"

```


в файл `clever-devel.vmx`, находящийся в папке, в которую был импортирован архив в п. 1.

-

Настройте режим моста через настройки виртуальной машины (если используется VMware Player для Windows) или с помощью утилиты `vmware-netcfg` (если используется версия для Linux-дистрибутивов):


![vmware-netcfg interface](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2Fsimulation_setup_vm%2F09_netcfg.png&sig=daf32b145360185e8163bcc19376f33075c46eade6101b3c7917903d1695739b)



В списке сетей выберите `vmnet0`, ниже - режим *Bridged*, в выпадающем списке *Bridged to* - название беспроводного адаптера, с помощью которого будет производиться подключение к дрону.
