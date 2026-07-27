# Загрузка параметров полётного контроллера

> Раздел: Обрик ROS 2 · slug: `params-upload`
> Источник: https://edu.sverk.tech/learn/obrik-ros-2/params-upload

---

# Загрузка параметров полётного контроллера


Готовый файл параметров переносит все настройки полётного контроллера за один шаг.


---


## Параметры PX4


Полётный контроллер **PX4** управляется через сотни параметров — числовых значений, которые определяют поведение дрона:

- как быстро реагировать на отклонение стика,
- как сильно наклоняться при повороте,
- какой уровень заряда аккумулятора считать критическим,
- с каких датчиков брать данные о высоте.

Вкладка **Parameters** в QGC показывает все эти параметры. Их там так много, что настраивать их вручную с нуля — долго. Поэтому используется **файл параметров**.


>

**Примечание** Файл параметров — это список значений, которые уже проверены и работают на Обрике. После загрузки файла вам останется только откалибровать датчики и аппаратуру управления.


---


## Загрузка параметров из файла

- Откройте вкладку **Parameters** в Vehicle Configuration

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F6.png&sig=aca8a3838ff393ac41a06d8b9790bdd776745d53be701d5a3f2b7c83e7848ab6)


- Нажмите кнопку **Tools** (в правом верхнем углу вкладки Parameters)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F7.png&sig=19bd89a56fdebdbe638460c26546d35e5e3b45ce32c7d68ef13592173e0ffdd7)


- В открывшемся меню выберите **Load from file for review**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F8.png&sig=924b26e47f2c768a59fc40c1b45714707e03ad4aa1a3aa8e9f3b92bf41bc099a)



>

**Примечание** Опция for review сначала показывает, какие параметры изменятся, и только потом применяет их — это безопаснее слепой загрузки.

- Выберите скачанный [файл с параметрами](https://drive.google.com/file/d/1392MPugvBD1SA4eytPBsy4nv05whPwLh/view?usp=drive_link)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F9.png&sig=ae03cd82c00c3694fb2d346d1c57fee2dfd1b2e9f5a11987f22f6db716e315d2)


- Посмотрите на список изменяемых параметров в открывшемся окне, затем нажмите **Ok**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F10.png&sig=bc439168a46b7e119b0573378c83499225a28aa2d02dc1f1813617f5715ac8b0)



---


## Перезагрузка Обрика


После загрузки параметров нужно перезагрузить полётный контроллер, чтобы новые настройки вступили в силу.

- Снова нажмите кнопку **Tools**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F11.png&sig=b3f0a3087d21b68972a960fc68ecb83a82b7c21282594555d5207fddd7895e35)


- Выберите **Reboot Vehicle**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F12.png&sig=708fa0786a48217542eb5e891bdc0718944ffd9d555e161e931ca5fcade43a4e)


- В появившемся диалоге нажмите **Ok**

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=obrik%2Fros2%2Fassets%2F1sverk%2Fsetup_flight_controller%2F13.png&sig=f2494c195b158a4499ad07f952e851629052bc0808b1b349befba29b02e7b581)


- Дождитесь перезагрузки — Обрик отключится и снова появится в QGC через 20–30 секунд

---


## Дальнейшие шаги


После перезагрузки параметры применены. Теперь нужно откалибровать датчики — гироскоп, акселерометр и уровень горизонта.
