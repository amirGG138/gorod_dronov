# Основы ручного пилотирования

> Раздел: Обрик ROS 1 (Clover) · slug: `visual-flight`
> Источник: https://edu.sverk.tech/learn/clover-2/visual-flight

---

# Основы ручного пилотирования


Управление Обриком происходит с помощью двух стиков аппаратуры управления. По умолчанию **левый стик** отвечает за газ и рысканье, а **правый стик** за крен и тангаж. Данные термины используются для всех летательных аппаратов, от самолетов до квадрокоптеров.


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fconsole_functionality.png&sig=2ff82c457261087634996ef650c2f72282f3b7a11e3c6385bc941572b2933d02)



![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdrone_lines.png&sig=61f712d0b8108fefb684df0205703227812a076c702a2cecf936ce3fd95371c4)



**Газ (throttle)** – отвечает за скорость вращения двигателей


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdrone_vert.png&sig=384dc3cdfd163be0e243e45ee2ea4fdd90ff87b4bafcc78ca7af7b485f2e4af5)



**Рысканье (yaw)** – отвечает за повороты вокруг вертикальной оси (Z), смещение стика вправо (влево) приводит к вращению по (против) часовой стрелки


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdrone_z.png&sig=bfde43f0ef16a49971710f987beb8b2deca8884243e131b75480add5142df3ad)



**Тангаж (pitch)** – отвечает за наклон или движение вперёд/назад


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdrone_y.png&sig=72d1b268e1c28af6d93810f5bf58aa8dfa36aab6630a060e2404e37263ed4e23)



**Крен (roll)** – отвечает за наклон или движение влево/вправо


![](https://api.edu.sverk.tech/api/courses/import/github/asset?owner=SeliverstovaE&repo=clover_sverk&ref=master&path=docs%2Fassets%2F1sverk%2Fvisual_flight%2Fdrone_x.png&sig=d8ef688fb9129cde894b8fed119a64e4d741e2f01e3e145a92f96ab24ccc1566)



>

**Note** “Вперёд” и “назад”, “влево” и “вправо” задаются относительно носа дрона, а не оператора. Если дрон развернулся к вам спиной, стик “вперёд” полетит от вас.


## Режимы полёта


>

**Note** Действия стиков **Yaw, Pitch и Roll** в полётных режимах не отличаются и отвечают за поворот, наклон вперед-назад и влево-вправо.

-

**STABILIZED** — стабилизация горизонтального положения, необходимо **ручное поддержание высоты**;<br> **Throttle** - управление газом происходит из нижнего положения стика;<br> При возврате правого стика в центральное положение **Обрик выровняется**, но продолжит движение по инерции и под воздействием внешних сил.

-

**ALTITUDE** — удержание высоты;<br> **Throttle** - управление газом происходит из центрального положения стика и отвечает **за скорость подъема/спуска**<br> При возврате обоих стиков в центральное положение **Обрик выровняется и будет удерживать текущую высоту**, но продолжит движение по инерции и под воздействием внешних сил.

-

**POSITION** — полное удержание положения в пространстве и компенсации воздействия внешних сил;<br> **Throttle** - управление газом происходит из центрального положения стика и отвечает за **скорость подъема/спуска**;<br> При возврате обоих стиков в центральное положение **Обрик будет зафиксирован в позиции в пространстве, компенсируя ветер и другие силы**.
