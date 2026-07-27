# Предполётная проверка

> Раздел: Микродрон (Whoop) · slug: `check`
> Источник: https://edu.sverk.tech/learn/whoop/check

---

# Предполётная проверка


Перед каждым полётом необходимо выполнить автоматическую проверку корректности настроек и работы всех подсистем микродрона.


Подключитесь к микродрону по SSH и выполните команду:


```
drone selfcheck

```


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fcheck%2Fimage1.jpg&sig=cb66333c37d2cd0ee0fa2a1d8cafdff0ead5925fa75ba779f67de76621ee2cb9)



Что проверяется:

- **FCU** — соединение с полётным контроллером;
- **gyro** — гироскоп;
- **accelerometer** — акселерометр;
- **magnetometer** — магнетометр;
- **gps** — глобальная позиция;
- **vision position** — оптическая навигация;
- **xy position control** — определение положения в пространстве;
- **rc receiver** — связь с аппаратурой управления.

Убедитесь, что следующие пункты отмечены как **PASS**:

- FCU
- gyro
- accelerometer
- rc receiver

>

**Примечание** Пункт **gps** будет иметь статус FAIL — это норма, так как микродрон использует оптический поток вместо GPS.


Если остальные ключевые пункты показывают FAIL — **взлёт запрещён!** Выполните [калибровку датчиков](/learn/whoop/setup-calibration).
