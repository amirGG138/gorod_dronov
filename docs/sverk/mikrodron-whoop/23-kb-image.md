# Установка образа

> Раздел: Микродрон (Whoop) · slug: `kb-image`
> Источник: https://edu.sverk.tech/learn/whoop/kb-image

---

# Установка образа


Для дальнейшей настройки и работы с микродроном необходимо установить образ на бортовой компьютер. Это обеспечит подключение к полётному контроллеру по Wi-Fi и программирование автономных полётов.


**Подготовка SD-карты**

-

Установите MicroSD-карту в компьютер (используйте адаптер при необходимости).

-

Отформатируйте MicroSD-карту.


**Запись образа с помощью Balena Etcher**

-

Запустите Balena Etcher.

-

Нажмите **Flash from file** и выберите скачанный ZIP-архив образа.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage2.png&sig=d240e27897a99daafa20de40dca59a0882d847e2974e4269c3018f80532d4473)

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage6.png&sig=27c9a749c231dde25a6193f72f8245209b037c0f1bf36d1e9720a78f68877a56)


- Нажмите **Select target**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage5.png&sig=d2b2008165a28d67bfbc0549d03d62e7f3a061bc08304ed69de3a960cd7c29a7)


- В списке выберите вашу SD-карту из списка подключенных устройств и нажмите **Select 1**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage3.png&sig=b608f6bd46bb97aeb18755e82ec44b778e1542b57f8555f62a1d4204e69a81c0)



>

**Внимание** Убедитесь, что вы выбрали корректную SD-карту. Неправильный выбор носителя может привести к удалению текущей операционной системы и потере всех данных.

- Нажмите **Flash!.** Процесс записи и проверки может занять несколько минут.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage4.png&sig=448a893f26dd3f1388b92e62acf8a1287a0f70c68754071e88820eeb79eedf1c)


- Дождитесь, пока программа покажет сообщение **Flash Completed!** и зелёную галочку.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fkb-image%2Fimage1.png&sig=40012f22d0895431ca06de1efa80a80d0f689327ff1126068f9cb7de4b66437b)



>

**Примечание** Завершите работу с картой через функцию **Безопасное извлечение устройства** в вашей ОС.

-

Извлеките SD-карту.

-

Найдите слот для SD-карты на плате расширения бортового компьютера и установите в него SD-карту.

-

Дождитесь загрузки образа.
