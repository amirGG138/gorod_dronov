# Подключение к QGroundControl

> Раздел: Микродрон (Whoop) · slug: `kb-qgc`
> Источник: https://edu.sverk.tech/learn/whoop/kb-qgc

---

# Подключение к QGroundControl


**Перед подключением убедитесь, что воздушные винты сняты!**

-

Подключите микродрон к компьютеру с помощью кабеля **USB Type-C**;

-

Запустите программу **QGroundControl** (QGC);

-

Нажмите на **логотип** QGC в верхнем левом углу;


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage3.png&sig=6bec7ced8fa7cd9a4d4c629ffbddd831f4b45497ddf12d33801e57d1f3af6234)


- В открывшемся окне выберите **Application Settings**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage1.png&sig=16bba94bf12e74cbc60a173a264146064ad6da65b227ad2b69a708e5003ea3d6)


- Выберите окно **Comm Links**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage7.png&sig=677ad9ecd2128e935e2269bd299e06faf4e03dfb52b530a1f67e4a6391bb71ba)


- В окне **Links** нажмите **Add**, чтобы добавить новое подключение;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage4.png&sig=282ca341462ff0b6cc3c100c482a468ad3de0aa3fe0deba3dd1ccce0b4bd6fe1)


- Выберите тип **UDP**, введите название (например, Sverk), включите автоматическое подключение (ползунок **Automatically Connect on Start**). При этом должен автоматически заполниться порт (**Port**) 14550. Введите **Server Addresses**: 10.10.1.1 и нажмите **Add Server**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage6.png&sig=007e0c41e178caa74c96c7c03a4ca234d48791120d8c19d251138a555af0ae59)


- Сохраните параметры подключения, нажав **Save**;

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage2.png&sig=a8d766d2fece4f70c10f75f6fc85272bedfe387f73e52caf39c2687aedbfcbc7)


- Выберите созданное подключение и нажмите **Connect**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-qgc%2Fimage5.png&sig=05da22bbdbcc3239caec665429ddb6f2996b5380c0f238f2c949bbe17e2eed64)
