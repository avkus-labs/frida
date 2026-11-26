# Новые скрипты frida: setup.py, interactive.py, update_dns.py

Документация на русском. Все скрипты — только стандартная библиотека Python,
работают на Windows, macOS и Linux (включая debian-nested по SSH).

## Файлы

| Файл | Назначение |
|---|---|
| `setup.py` | Подготовка свежего Android + Python: frida-tools, adb, root (`adb root`), Chrome, Google One |
| `interactive.py` | Вход в Google-аккаунт, выбор тарифа, вызов `main.py`, повтор при неудаче |
| `update_dns.py` | Динамический DNS: обновляет A-запись в Cloudflare, только если IP изменился |
| `config.example.py` | Шаблон конфига (скопировать как `config.py` и заполнить) |
| `main.py`, `frida.js`, `offers.txt` | Существующие скрипты (не менялись) |

## Настройка

1. Скопируйте шаблон конфига:
   ```
   cp config.example.py config.py
   ```
2. В `config.py` укажите:
   - `ADB_SERIAL` — домен устройства, например `adb.example.com:5555`
     (домен обновляется через `update_dns.py`; пока домена нет, можно IP:5555).
   - `CF_ZONE_ID`, `CF_DNS_RECORD_ID`, `CF_RECORD_NAME` — для `update_dns.py`.
   - `CHROME_APK_URL`, `GOOGLE_ONE_APK_URL` — прямые ссылки на APK
     (например, с APKMirror), если APK нет локально.
3. Токен Cloudflare — переменной окружения, а не в файле:
   ```
   export CF_API_TOKEN="..."
   ```
   На Windows (PowerShell):
   ```
   $env:CF_API_TOKEN="..."
   ```
   Настоящий `config.py` и токен **никогда не коммитятся** (см. `.gitignore`).

## Рабочий процесс

### 1. Свежая VM из резервной qcow2
Создайте новую VM из резервной копии `bliss-backup-20261124.qcow2`
(рабочий Android до установки всего лишнего), запустите её.

### 2. setup.py — установка всего нужного
```
python setup.py --serial adb.example.com:5555
```
Что он делает по порядку:
- находит интерпретаторы `python`, `python3`, `py` и ставит `frida-tools`
  в каждый, где его нет (важно: у пользователя два Питона, frida была только
  в одном — из-за этого main.py падал с WinError 193);
- находит `adb` (PATH, `ANDROID_HOME`, типовые места) или берёт `--adb`;
- `adb connect <serial>`, проверяет, что устройство в списке;
- `adb root` (adbd перезапускается от root);
- root — нативный `adb root` (сборка userdebug, `su` не нужен).
  Заглушка `su` в `/system/bin/su` ставится ТОЛЬКО с флагом
  `--install-su-shim` (opt-in, наследие; `main.py` теперь проверяет
  root через `shell_is_root()` и `su` нужен лишь как запасной вариант);
- устанавливает Google Chrome и Google One через `adb install`
  (пропускает уже установленные, если нет `--force`; APK скачиваются
  по ссылкам из конфига в `downloads/` или берутся из
  `--chrome-apk` / `--google-one-apk`);
- печатает итоговую сводку.

Полезные флаги: `--force` (переустановить приложения), `--skip-frida`,
`--skip-apps`, `--adb <путь>`.

Повторный запуск безопасен: уже установленное пропускается.

### 3. Резервная копия настроенной VM
После setup.py сделайте новую резервную копию qcow2 рабочей VM —
это будет эталон для следующих развёртываний.

### 4. interactive.py — аккаунт и тариф
```
python interactive.py --serial adb.example.com:5555
```
Что он делает:
- подключается к устройству, проверяет root (без root предупреждает
  и предлагает сначала прогнать `setup.py`);
- смотрит Google-аккаунты на устройстве (`dumpsys account`):
  показывает список обнаруженных аккаунтов и предупреждает, что активный
  платёжный профиль выбирается внутри самого Google One на устройстве;
  если аккаунта нет — открывает штатный экран Android (`ADD_ACCOUNT_SETTINGS`),
  чтобы пользователь ввёл логин, пароль и 2FA непосредственно в окне VNC
  (учётные данные никогда не запрашиваются в Python и не передаются в ADB).
- открывает Google One;
- показывает полный нумерованный список тарифов из `frida.js` (как в `main.py`,
  а при недоступности — из `offers.txt`) и вызывает
  `python main.py --serial <serial> --plan <id>` (интерпретатор выбирается
  тот, где импортируется `frida`);
- после отработки `main.py` спрашивает: «Экран оформления тарифа открылся /
  план сработал? (да/нет)». Если да — напоминает, что дальше ввод карты
  вручную. В обоих случаях предлагает выбрать другой тариф или выйти (`q`).

Флаги: `--plan pro_12m` (пропустить меню), `--renew` (режим продления),
`--serial`, `--adb`.

## Динамический DNS: update_dns.py

Внешний IP хоста эфемерный (меняется при остановке/запуске VM).
Чтобы не привязываться к IP, домен `adb.example.com` обновляется через
Cloudflare API.

```
python update_dns.py
```

Логика (важно — API дёргается только при смене IP):
1. Узнаёт текущий внешний IP: сначала GCP metadata server
   (`metadata.google.internal`), затем `api.ipify.org`, затем `ifconfig.me`.
2. Читает последний отправленный IP из state-файла
   (`state/dns_last_ip.txt` рядом со скриптом).
3. Если IP совпадает с сохранённым — печатает «IP не изменился, API не трогаем»
   и выходит, **не вызывая Cloudflare API**.
4. Если отличается — делает `PUT` в Cloudflare API
   (`/zones/{zone_id}/dns_records/{record_id}`, `{"type":"A", ...}`).
5. Только при успехе записывает новый IP в state-файл.
   При ошибке API state-файл не меняется (следующий запуск попробует снова).

Флаги: `--ip <ip>` (вручную), `--state-file <путь>`, `--zone-id`,
`--record-id`, `--record-name`, `--force` (обновить, даже если IP тот же),
`--dry-run` (только показать, что было бы сделано).

### Cron на KVM-хосте

Раз в 5 минут (токен — в окружении cron-задачи или в защищённом `config.py` с правами `600`):
```
*/5 * * * * CF_API_TOKEN="..." /usr/bin/python3 /home/vmuser/frida/update_dns.py >> /var/log/update_dns.log 2>&1
```

### Пример развёртывания на KVM-хосте

- Записи в Cloudflare (обе тип A, DNS-only, `proxied=false`):
  - ADB: `adb.example.com`, Record ID `<cf_record_id_adb>`
  - SSH: `vm-host.example.com`, Record ID `<cf_record_id_ssh>`
- Зона: `example.com`, Zone ID `<cf_zone_id>`
- SSH-запись — точка входа по домену (порт 2222):
  `ssh -p 2222 vmuser@vm-host.example.com`.
- Токен Cloudflare хранится в переменной окружения `CF_API_TOKEN` или в локальном `config.py` (`chmod 600`, в `.gitignore`).

Как получить Zone ID и Record ID через API Cloudflare:
1. `GET /client/v4/zones` — найти свою зону и её Zone ID.
2. `GET /zones/{zone_id}/dns_records?name=adb.example.com` — получить Record ID записи.
3. Записать `CF_ZONE_ID`, `CF_DNS_RECORD_ID`, `CF_RECORD_NAME="adb.example.com"` в локальный `config.py`.

Cron (пользователь `vmuser`, каждые 5 минут):
```
*/5 * * * * /home/vmuser/bin/update_dns.py >> /home/vmuser/frida/update_dns.log 2>&1
```

Telegram-хук в `update_dns.py`: после успешной смены IP скрипт шлёт одно сообщение в Telegram (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` из окружения или `config.py`, бот вида `@ExampleBot`). Неудача отправки не отменяет обновление DNS.

## Сторож KVM: vm_watch.py

Отдельный скрипт рядом с `update_dns.py`. Каждые 5 минут спрашивает у libvirt (`virsh -c qemu:///system`), какие VM есть, какие запущены, какие у них внутренние IP и VNC/SPICE-порты, и сверяет со снимком в `state/vm_state.json`.
- При ошибке `virsh list` завершается с кодом ошибки и **не** перезаписывает state-файл пустым списком.
- Отдельно хранит последний опрос (`last_polled`), закреплённые слоты портов (`port_slots`) и последнее доставленное уведомление (`last_notified`) — при сбое Telegram отправка повторится на следующем цикле.
- Пароль VNC никогда не включается в сообщения и не выводится в консоль.

Cron (пользователь `vmuser`, каждые 5 минут):
```
*/5 * * * * /home/vmuser/bin/vm_watch.py >> /home/vmuser/frida/vm_watch.log 2>&1
```

Доступ к гостевым VM с рабочей станции идёт только через SSH-туннель (`tunnel.py`), прямой порт ADB 5555 снаружи закрыт.

## SSH-туннель к VM: tunnel.py

Запускается на рабочей станции (Windows/macOS/Linux) и держит окно туннеля. Опрашивает хост (`vm_watch.py --inventory` по SSH) и строит пробросы с **постоянным закреплением портов** за именами VM (в `state/tunnel_ports.json` и `port_slots` инвентаря), так что остановка одной VM не меняет порт другой:

```
python3 tunnel.py              # поднять туннель (ssh на переднем плане)
python3 tunnel.py --dry-run    # только показать пробросы и команду
```

Порты (локальные): ADB `15551, 15552, ...`; VNC `15901, 15902, ...`.
Параметры хоста берутся из `config.py` (`SSH_HOST`, `SSH_PORT`, `SSH_USER`) или флагов `--host/--port/--user`.

## Запуск на KVM-хосте по SSH

При запуске прямо на хосте укажите внутренний IP нужной VM (актуальный IP виден в `vm_watch.py --inventory`):
```
python3 setup.py --serial 10.166.0.10:5555
python3 interactive.py --serial 10.166.0.10:5555
```

## Заметки

- **Root — нативный `adb root`.** Сборка Bliss OS userdebug: `adb root`
  даёт shell с `uid=0`, `main.py` проверяет это через `shell_is_root()`,
  `su` нужен лишь как запасной вариант. Заглушка `/system/bin/su`
  ставится `setup.py` ТОЛЬКО с `--install-su-shim` (opt-in).
  После перезагрузки Android `adb root` нужно повторить (не сохраняется),
  а заглушка `su` (если ставилась) остаётся на диске.
- **Буфер обмена в VNC не работает** (VNC-сервер QEMU его не передаёт).
  Текст в поля вводится через `adb shell input text` или руками с клавиатуры.
- **Порт ADB 5555 снаружи закрыт.** DNAT убит 2026-11-25, правило GCP
  allow-adb-5555 — DISABLED. Доступ к VM — только через SSH-туннель
  (`tunnel.py`), напрямую снаружи на 5555 ничего не слушает.
- **Scrcpy не работает** в этой сборке (сломан видео-энкодер, `err=-38`).
  Экран — только через VNC (порт 5901). Перепроверено 2026-11-25 на
  клоне bliss-01: `adb shell screenrecord` → `Encoder failed (err=-38)`,
  тот же энкодер, что и у исходной VM. ADB при этом работает (connect,
  shell, boot_completed=1).
