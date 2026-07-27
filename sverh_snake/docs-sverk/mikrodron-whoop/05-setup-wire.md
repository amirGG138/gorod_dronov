# Подключение по проводу

> Раздел: Микродрон (Whoop) · slug: `setup-wire`
> Источник: https://edu.sverk.tech/learn/whoop/setup-wire

---

# Подключение по проводу


Подключение к бортовому компьютеру выполняется по протоколу SSH через кабель USB Type-C. IP-адрес микродрона при проводном подключении всегда фиксирован: `10.10.1.1`. Логин и пароль — `root`.


>

**Подсказка** Проводное подключение надёжнее Wi-Fi и рекомендуется для первоначальной настройки и отладки.


Для подключения потребуется SSH-клиент. Варианты по операционным системам:


**Linux**

- OpenSSH Client
- Linux Terminal

**Windows**

- PuTTY
- mRemoteNG
- SecureCRT

**macOS**

- Terminal
- ZOC Terminal

## Подключение через Terminal (Linux / macOS)


Выполните команду:


```
ssh root@10.10.1.1

```


## Подключение через mRemoteNG (Windows)

- Выберите протокол **SSH2**.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wire%2Fimage2.png&sig=fe2b72d95534a6a859e62a346922766443352f7c5fe6f29b9069078dd87f2c86)


- В строке «подключение» введите IP-адрес: `10.10.1.1`.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wire%2Fimage1.png&sig=80005d971ff2f0259acd7113be0be7f32f7e351bb0d7dbad4beca83e75cffb68)


- Введите логин и пароль (`root` для обеих строк).

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wire%2Fimage3.png&sig=53eff7b5007fce2386eca28684c7533719769cc749ef54bf7a0a01234eb8abca)



>

**Примечание** Для подключения к QGroundControl через USB-кабель — см. [Подключение к QGroundControl](/learn/whoop/kb-qgc).
