# Подключение по Wi-Fi

> Раздел: Микродрон (Whoop) · slug: `setup-wifi`
> Источник: https://edu.sverk.tech/learn/whoop/setup-wifi

---

# Подключение по Wi-Fi


Для беспроводного подключения нужно прописать данные вашей Wi-Fi сети в конфигурационный файл на бортовом компьютере микродрона. Это делается через [проводное подключение](/learn/whoop/setup-wire) по SSH.


>

**Примечание** Компьютер и микродрон должны быть в одной Wi-Fi сети.

- Откройте конфигурационный файл управления беспроводными сетями:

```
nano /etc/wpa_supplicant.conf

```


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wifi%2Fimage1.png&sig=1ebff7df96335488b580f708e109f2e30fe96824fa2b47b8f366367f149cc55c)


- Пропишите **имя сети** и **пароль**:

```
network={
  ssid="ИМЯ СЕТИ"
  psk="ПАРОЛЬ"
}

```


>

**Внимание** Имя сети и пароль не должны содержать кириллицу.

- Определите **тип безопасности** сети:

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wifi%2Fimage3.png&sig=0437f7c48d66ba57d61013424971305517ad7f35427b65239ec855137d45857a)



![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fsetup-wifi%2Fimage2.png&sig=2fdde1cd7e71b5e300d78002f6b73e70ce98de973264e7540af6ff632725c081)


- Допишите строки в зависимости от типа сети:

**WPA/WPA2**


```
network={
  ssid="ИМЯ СЕТИ"
  psk="ПАРОЛЬ"
  key_mgmt=WPA-PSK
  proto=WPA RSN    # WPA и WPA2
  pairwise=TKIP CCMP  # шифрование TKIP и AES
  group=TKIP CCMP
}

```


**WPA2**


```
network={
  ssid="ИМЯ СЕТИ"
  psk="ПАРОЛЬ"
  key_mgmt=WPA-PSK
  proto=RSN        # только WPA2
  pairwise=CCMP    # только AES
  group=CCMP
}

```


**WPA2/WPA3**


```
network={
  ssid="ИМЯ СЕТИ"
  psk="ПАРОЛЬ"
  key_mgmt=WPA-PSK-SHA256 SAE
  proto=RSN
  ieee80211w=1
  pmf=optional
}

```


**WPA3**


```
network={
  ssid="ИМЯ СЕТИ"
  psk="ПАРОЛЬ"
  key_mgmt=SAE
  proto=RSN
  ieee80211w=2
  pmf=required
}

```

-

Сохраните файл: **Ctrl+X → Y → Enter**.

-

Подключитесь к Wi-Fi:


```
wpa_supplicant -Dnl80211 -iwlan0 -c/etc/wpa_supplicant.conf

```
