# Основы ручного пилотирования

> Раздел: Микродрон (Whoop) · slug: `manual-flight`
> Источник: https://edu.sverk.tech/learn/whoop/manual-flight

---

# Основы ручного пилотирования


Управление микродроном происходит с помощью двух стиков аппаратуры управления. По умолчанию **левый стик** отвечает за газ и рысканье, а **правый стик** за крен и тангаж. Данные термины используются для всех летательных аппаратов, от самолётов до квадрокоптеров.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage6.png&sig=4569941aca34131ab38900786a40ba30911dd73d6e09203291488c935e603c50)



![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage3.png&sig=1759e63d12d478b8e62912255c80b2d37959a38292e7408e9f875e339d70560b)



**Газ (throttle)** — отвечает за скорость вращения двигателей.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage4.png&sig=7d980939c37cf8a7135b1d2df28329b42151c70c829556bc8906c7fb4c1f305e)



**Рысканье (yaw)** — отвечает за повороты вокруг вертикальной оси (Z), смещение стика вправо (влево) приводит к вращению по (против) часовой стрелки.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage2.png&sig=cab19e6588602eda03ee2c2a8fbbd17d775be560bf85a9ef51175b468c479874)



**Тангаж (pitch)** — отвечает за наклон или движение вперёд/назад.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage1.png&sig=573dae6afc49a47990c13163e3620d25e0bad11b614814b23222e96adfe370c3)



**Крен (roll)** — отвечает за наклон или движение влево/вправо.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fmanual-flight%2Fimage5.png&sig=7cfbd2b43d412f3e66059a86f83c59c78fb964dd81f4b3e383637098ab206376)



>

**Примечание** Все описанные действия микродрона подразумеваются относительно его ориентации в пространстве.


**Визуальный полёт (ручное управление)**


При визуальном пилотировании оператор управляет дроном напрямую.


**Режимы полёта:**


>

**Примечание** Действия стиков **Yaw**, **Pitch** и **Roll** в полётных режимах одинаковы: поворот, наклон вперёд-назад и влево-вправо.

- **STABILIZED** — стабилизация горизонтального положения, необходимо **ручное поддержание высоты**

>

**Примечание** **Throttle** — управление газом из нижнего положения стика. При возврате правого стика в центральное положение микродрон выровняется, но продолжит движение по инерции и под воздействием внешних сил.

- **ALTITUDE** — удержание высоты

>

**Примечание** **Throttle** — управление газом из центрального положения стика, отвечает за скорость подъёма/спуска. При возврате обоих стиков в центр микродрон выровняется и будет удерживать текущую высоту, но продолжит движение по инерции и под воздействием внешних сил.

- **[POSITION](/learn/whoop/manual-flight-position)** — полное удержание положения в пространстве и компенсации воздействия внешних сил.

>

**Примечание** **Throttle** — управление газом из центрального положения стика, отвечает за скорость подъёма/спуска. При возврате обоих стиков в центр микродрон зафиксируется в точке пространства, компенсируя ветер и другие силы.
