# Новые скрипты frida: setup.py, interactive.py, update_dns.py

Документация на русском. Все скрипты — только стандартная библиотека Python,
работают на Windows, macOS и Linux (включая debian-nested по SSH).

## Файлы

| Файл | Назначение |
|---|---|
| `setup.py` | Подготовка свежего Android + Python: frida-tools, adb, root, заглушка su, Chrome, Google One |
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
- ставит заглушку `su` в `/system/bin/su`, если её нет
  (в этой сборке Bliss OS бинаря `su` нет; заглушка просто запускает
  команду, потому что оболочка adb уже от root; проверяется через
  `su -c id` → `uid=0`);
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
  если есть — предлагает выбрать существующий или добавить новый;
  если нет — открывает экран добавления аккаунта и проводит через вход:
  email → пароль (ввод скрыт, `getpass`) → 2FA, если нужна.
  Текст отправляется в активное поле через `adb shell input text`,
  дальше — `input keyevent 66` (Enter). После каждого шага скрипт ждёт
  нажатия Enter, чтобы можно было ткнуть в поле мышкой в окне VNC,
  если фокус не там. Пароль и код 2FA никогда не берутся из аргументов
  командной строки.
- открывает Google One;
- показывает нумерованный список тарифов (берётся из `GROUPS` в `main.py`,
  если импорт не удался — из `offers.txt`) и вызывает
  `python main.py --serial <serial> --plan <id>` (интерпретатор выбирается
  тот, где импортируется `frida`);
- после отработки `main.py` спрашивает: «Экран оформления тарифа открылся /
  план сработал? (да/нет)». Если да — напоминает, что дальше ввод карты
  вручную. В обоих случаях предлагает выбрать другой тариф или выйти (`q`).

Флаги: `--plan pro_12m` (пропустить меню), `--renew` (режим продления),
`--email user@gmail.com` (предзаполнение), `--serial`, `--adb`.

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

### Cron на debian-nested

Раз в 5 минут (токен — в окружении cron-задачи, не в файле):
```
*/5 * * * * CF_API_TOKEN="..." /usr/bin/python3 /home/gru_avkus/frida/update_dns.py >> /var/log/update_dns.log 2>&1
```

### Развёрнуто на debian-nested (live, 2026-11-25)

Автообновление эфемерного IP работает. Домен — реальный, не пример:

- Записи (обе тип A, DNS-only, proxied=false, TTL auto):
  - ADB: `adb.avkus.bond`, Record ID `af2f9579ed8155694038657b813c0ea8`
  - SSH: `debian-nested.avkus.bond`, Record ID `957df734f2628270f68092daf2dafd33`
- Зона: `avkus.bond`, Zone ID `bc227290b895883d4d95fcf466b42953`
- SSH-запись — точка входа по домену (порт 2222, нестандартный):
  `ssh -p 2222 dave@debian-nested.avkus.bond`. Имя `ssh.avkus.bond` занято
  (CNAME на Cloudflare Tunnel), поэтому взяли `debian-nested.avkus.bond`.
- Токен Cloudflare лежит в `config.py` (600, в .gitignore), а не в окружении
  cron-задачи — в отличие от примера выше.

Как получали Zone ID и Record ID (токен уже был в `config.py`):
1. `GET /client/v4/zones` — список зон, нашли `avkus.bond` и его Zone ID.
2. `GET /zones/{zone_id}/dns_records?name=adb.avkus.bond` — запись уже
   существовала (создал Андрей), взяли её Record ID и текущий content
   (тогда был старый IP 34.122.243.84).
3. Вписали Zone ID, Record ID, `CF_RECORD_NAME=adb.avkus.bond` и
   `ADB_SERIAL=adb.avkus.bond:5555` в `config.py`.

Развёртывание:
- Симлинк: `/home/avkuska/bin/update_dns.py` -> `/home/avkuska/frida/update_dns.py`
  (скрипт через `Path(__file__).resolve()` находит `config.py` и `state/`
  в репозитории, поэтому симлинк работает).
- Cron (пользователь avkuska, каждые 5 минут):
```
*/5 * * * * /home/avkuska/bin/update_dns.py >> /home/avkuska/frida/update_dns.log 2>&1
```
- Лог: `/home/avkuska/frida/update_dns.log`, state: `state/dns_last_ip.txt`.

Ручной тест 2026-11-25: пройден. Скрипт определил IP 34.27.239.29
(через GCP metadata), обновил `adb.avkus.bond` с 34.122.243.84 на
34.27.239.29, записал IP в state-файл. Проверка через API подтвердила:
запись указывает на 34.27.239.29.

Боевой тест 2026-11-25: пройден. Сервер выключили и включили, новый IP
34.136.139.241; cron сам обновил `adb.avkus.bond` на новый IP без ручных
действий (в логе: определил 34.136.139.241 против 34.27.239.29 в state →
PUT → state записан).

Вторая запись (SSH) 2026-11-25: `update_dns.py` расширен на две записи
(основная + `CF_DNS_RECORD_ID_SSH` / `CF_RECORD_NAME_SSH` из config.py;
та же зона). Проверка `--force`: обновил обе записи на 34.136.139.241,
API подтвердил обе DNS-only.


Telegram-хук в update_dns.py 2026-11-25: после успешной смены IP
скрипт шлёт одно сообщение в Telegram (Bot API sendMessage):
`IP debian-nested обновлён на <новый IP>` + имена обновлённых записей.
Токен и chat_id — TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID из env или
config.py (Андрей заполнил сам). Если IP не изменился — ничего не шлётся.
Неудача отправки НЕ отменяет обновление DNS (предупреждение в лог).
ПРОБЛЕМА 2026-11-25: тест `--force` — DNS обновился, а Telegram ответил
`Unauthorized` (401): токен бота в config.py не принимается API.
Хук работает, нужен рабочий токен (от @BotFather) в config.py.

## Сторож KVM: vm_watch.py (live, 2026-11-25)

Отдельный скрипт, тоже лежит во frida. Каждые 5 минут спрашивает
у libvirt (`virsh -c qemu:///system`), какие VM запущены, какие у них
внутренние IP и VNC/SPICE-порты, и сравнивает со снимком в
`state/vm_state.json`. Telegram — ТОЛЬКО если что-то изменилось:
VM включилась/выключилась, IP переназначился, VNC-порт поменялся,
внешний IP хоста сменился. Сообщение: текущее состояние всех машин
+ список изменений.

- Симлинк: `/home/avkuska/bin/vm_watch.py` -> `/home/avkuska/frida/vm_watch.py`
- Cron (пользователь avkuska, каждые 5 минут):
```
*/5 * * * * /home/avkuska/bin/vm_watch.py >> /home/avkuska/frida/vm_watch.log 2>&1
```
- Лог: `/home/avkuska/frida/vm_watch.log`, state: `state/vm_state.json`.
- IP берётся из `virsh domifaddr`, запасной источник — DHCP-аренды
  `/var/lib/libvirt/dnsmasq/virbr0.status` (по MAC из dumpxml).
- VNC-порт: у запущенной VM — из `virsh vncdisplay` (:N = 5900+N),
  у выключенной — из dumpxml (port='-1' = autoport, назначится при старте).
- VNC-пароль: **virsh его НЕ отдаёт** (в XML его нет — пароль только
  записывается через QMP, не читается). Если пароль нужен в сообщении —
  задайте `VNC_PASSWORD` в config.py (ключ уже есть в config.example.py).
- Работает от avkuska без sudo: avkuska в группе libvirt, но virsh
  по умолчанию ходит в qemu:///session (пусто) — скрипт явно указывает
  `-c qemu:///system`.
- Первый запуск: пишет начальный снимок и шлёт его в Telegram как
  «начальное состояние». Дальше — только изменения.
- Тест 2026-11-25: `--dry-run` показал корректный снимок (bliss-01
  running 10.166.0.128 VNC 5902; win11 running, IP не виден, SPICE 5900;
  bliss-02/blisstemplate shut off). Второй запуск — «Без изменений,
  Telegram не трогаем». Telegram не дошёл из-за того же `Unauthorized`
  (токен, см. выше) — снимок при этом записался.


DNAT убит 2026-11-25: прямой путь ADB снаружи (adb.avkus.bond:5555 →
DNAT → 10.166.0.129:5555) больше не используется. Удалёны оба правила
DNAT (5555 → .129 и 3389 → .128, оба указывали на несуществующие /
не те машины) и оба FORWARD ACCEPT, правила сохранены через
netfilter-persistent. Теперь только SSH-туннели (см. tunnel.py).
Правило GCP allow-adb-5555 осталось, но никуда не ведёт (на хосте
на 5555 ничего не слушает без DNAT) — можно закрыть.

## SSH-туннель к VM: tunnel.py (live, 2026-11-25)

Простой скрипт, запускается на твоём компьютере (Windows/macOS/Linux)
и держит окно туннеля. Сам спрашивает у хоста, какие VM запущены
(vm_watch.py --inventory по SSH), и динамически строит пробросы:
на каждую запущенную VM — свой локальный порт ADB и свой VNC.
Одна VM — одна пара портов, две — две, три — три.

  python3 tunnel.py              # поднять туннель (ssh на переднем плане)
  python3 tunnel.py --dry-run    # только показать пробросы и команду

Порты (локальные): ADB 15551, 15552, ...; VNC 15901, 15902, ...
(по порядку имён VM). Пример для bliss-01:
  adb connect 127.0.0.1:15551
  VNC-клиент → 127.0.0.1:15901
ADB идёт на внутренний IP VM (:5555), VNC — на порт хоста
(у bliss-01 это 5902). Опции: --host/--port/--user, --adb-base,
--vnc-base, --no-adb/--no-vnc, --ssh (путь к ssh), --ssh-opts
(доп. опции одной строкой, например -F путь-к-конфигу).

Тест 2026-11-25: --dry-run показал bliss-01 → ADB 15551 + VNC 15901.
Живой туннель поднят, проверено: `adb connect 127.0.0.1:15551` →
device, boot_completed=1, модель Generic Android-x86_64; TCP до
VNC 15901 доходит. Туннель закрыт после теста.

## Запуск на debian-nested по SSH

Скрипты можно запускать прямо на хосте — репозиторий клонируется и туда.
На хосте серийник устройства — внутренний IP VM:
```
python3 setup.py --serial 10.166.0.129:5555
python3 interactive.py --serial 10.166.0.129:5555
```
Тот же `interactive.py` может запустить и агент (например, Муся) по SSH
до шага ввода карты: дальше работа ручная. Пароль и 2FA агент спросит
у пользователя, сам он их не знает.

## Заметки

- **Заглушка su.** В этой сборке Bliss OS нет бинаря `su`, а `main.py`
  проверяет root через `su -c id`. `setup.py` ставит заглушку
  `/system/bin/su` (перемонтирует `/` в rw, пишет маленький sh-скрипт,
  `chmod 755`). Проверка: `adb shell su -c id` → `uid=0`.
  После перезагрузки Android `adb root` нужно повторить (не сохраняется),
  а заглушка `su` остаётся на диске.
- **Буфер обмена в VNC не работает** (VNC-сервер QEMU его не передаёт).
  Текст в поля вводится через `adb shell input text` или руками с клавиатуры.
- **Порт ADB 5555 открыт в мир.** Пока планшет/VM включается только
  на время работы — это приемлемо. Если понадобится держать включённым
  постоянно — закрыть порт и ходить через Cloudflare Tunnel.
- **Scrcpy не работает** в этой сборке (сломан видео-энкодер, `err=-38`).
  Экран — только через VNC (порт 5901). Перепроверено 2026-11-25 на
  клоне bliss-01: `adb shell screenrecord` → `Encoder failed (err=-38)`,
  тот же энкодер, что и у исходной VM. ADB при этом работает (connect,
  shell, boot_completed=1).
