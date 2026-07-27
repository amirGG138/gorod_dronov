# Перепрошивка полётного контроллера

> Раздел: Микродрон (Whoop) · slug: `kb-reflash`
> Источник: https://edu.sverk.tech/learn/whoop/kb-reflash

---

# Перепрошивка полётного контроллера


В случае загрузки некорректных настроек полётного контроллера подключение дрона описанными ранее способами может стать недоступным. Для решения данной проблемы необходимо выполнить **перепрошивку полётного контроллера**.

-

С помощью шестигранника открутите винты и **снимите крышку** микродрона;

-

Открутите 4 крепёжные гайки полётного контроллера и слегка приподнимите его для доступа к разъёму;

-

Соедините полётный контроллер с компьютером при помощи кабеля **micro-USB**;

-

Запустите программу **QGroundControl** (QGC);

-

Нажмите на **логотип** QGC в верхнем левом углу;


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage5.png&sig=44dcdc8f62b13c7410cb9e50b124944153773480fc4e52efab6408e011cfd3b3)


- В открывшемся окне выберите **Application Settings**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage3.png&sig=db63c9890612c30af38c8fb5e150c18e4044f773812d105eaf9af90957dfbcd9)


- Выберите окно **Comm Links**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage4.png&sig=c372dfc7c82a143d61d0f7966b8142c8c37576f9377fe178644bbed8507daa29)


- В окне **Links** нажмите **Add**, чтобы добавить новое подключение;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage1.png&sig=8b769dcad740fd7081c2f04d82fb3cb3cb55a482a96b4b4fcc8271c909156e46)


- Выберите тип **Serial**, введите название (например, FCU), включите автоматическое подключение (ползунок **Automatically Connect on Start**), в графе **Baud Rate** выберите значение 57600 и нажмите **Save**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage7.png&sig=c71c2c162011ceaa7e3746e610ce944bb5091e1dd4505ab4cb51040f08002721)


- Нажмите **Connect** для подключения;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage2.png&sig=b6c220ac3bdf7870e676d01bc6244dddec53c166503afbf44331855a1552f40d)


- При выходе в главное меню можно увидеть подключение и выполнить **повторную настройку** так же, как это было описано ранее.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-reflash%2Fimage6.png&sig=41778d3f82893e330c24a24803c0bbfbb58b6de4405be37afa28c16c972dbc3b)
