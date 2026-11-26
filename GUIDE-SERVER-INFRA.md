# Серверная инфраструктура (`vm-host`, KVM, DDNS, мониторинг)

## 1. Сетевая архитектура
- **Хост:** облачная VM с nested KVM (`vm-host`), внешний IP эфемерный.
- **Домены в Cloudflare (зона `example.com`, оба A-записи, строго DNS-only / серое облако):**
  - `vm-host.example.com` — вход по SSH (порт `2222`) и RDP (`3390`)
  - `adb.example.com` — запасная/сервисная A-запись
- **Доступ к ВМ снаружи:** DNAT и порт `5555` снаружи **отключены** (правила `iptables` удалены). Всё общение с гостевыми ВМ (ADB и VNC) с Windows и Mac идёт через **`tunnel.py`** поверх SSH (порт `2222`).
- **Сеть ВМ:** libvirt NAT `default` (`virbr0`, `10.166.0.0/24`).

---

## 2. Эталонная ВМ `blisstemplate` (BlissOS 15.9.2)

### Ключевые настройки эталона
- **GRUB (`/boot/grub/android.cfg`):** `nomodeset HWACCEL=0` (убирает зависимость от 3D-ускорения).
- **Видео:** `model=vga,vram=16384` (вместо `cirrus`, который даёт вертикальные RGB-полосы).
- **VNC:** `sharePolicy='ignore'`, на клонах `port=-1` (автовыбор порта `5900`, `5901`, `5902`...).
- **Ускорение nested KVM:**
  - CPU: `host-passthrough`
  - Диск: `bus='virtio'`, `cache='writeback'`, `io='threads'`, `discard='unmap'`
  - Сеть: `model='virtio'`
  - Ввод: `tablet` и `keyboard` на `bus='virtio'`, USB-контроллер `qemu-xhci`
- **Внутри Android:**
  - Включён `USB debugging` в *Developer options* (автоматически поднимает ADB на порту `5555` по виртуальному Ethernet).
  - Включена 3-кнопочная навигация (`adb shell cmd overlay enable com.android.internal.systemui.navbar.threebutton`).
  - Предустановлены Chrome, Google One и нужные приложения (без сохранённого Google-аккаунта на эталоне).
  - Эталонный диск `/var/lib/libvirt/images/blisstemplate.qcow2` защищён `chmod 444`.

### Обновление эталона из тонкого клона
> Перезаписывать `blisstemplate.qcow2` можно только тогда, когда от него нет других активных тонких клонов. Перед сохранением удалите Google-аккаунт и данные Play Store/Play Services.

```bash
# 1. Мягко выключить настроенный клон
adb -s 127.0.0.1:15551 shell reboot -p
sudo virsh list --all   # убедиться, что state = shut off

# 2. Склеить базу и оверлей в цельный образ
sudo qemu-img convert -p -O qcow2 \
  /var/lib/libvirt/images/bliss-01.qcow2 \
  /var/lib/libvirt/images/blisstemplate-new.qcow2

# 3. Удалить временный клон и заменить эталон
sudo virsh undefine bliss-01 --remove-all-storage
sudo mv -f /var/lib/libvirt/images/blisstemplate-new.qcow2 /var/lib/libvirt/images/blisstemplate.qcow2
sudo chmod 444 /var/lib/libvirt/images/blisstemplate.qcow2
```

---

## 3. Создание и удаление тонких клонов (`/usr/local/bin/new_bliss.sh`)
- Создаёт qcow2-оверлей, клонирует XML (`virt-clone --preserve-data`), ставит автовыбор порта VNC (`port=-1`) и случайный **8-символьный** пароль VNC, запускает ВМ.
- Создать клон:
  ```bash
  sudo new_bliss.sh bliss-01
  ```
- Удалить отработанный клон (после удаления имя снова свободно, можно создавать с `01`):
  ```bash
  sudo virsh destroy bliss-01
  sudo virsh undefine bliss-01 --remove-all-storage
  ```

---

## 4. Автообновление DNS (`update_dns.py`) и сторож KVM (`vm_watch.py`)

Оба скрипта запущены в `crontab` пользователя `vmuser` каждые 5 минут (симлинки в `/home/vmuser/bin/`):

```cron
*/5 * * * * /home/vmuser/bin/update_dns.py >> /home/vmuser/frida/update_dns.log 2>&1
*/5 * * * * /home/vmuser/bin/vm_watch.py >> /home/vmuser/frida/vm_watch.log 2>&1
```

### Что делает `update_dns.py`
1. Определяет внешний IP (`metadata.google.internal` → `api.ipify.org` → `ifconfig.me`).
2. Сравнивает с `state/dns_last_ip.txt`. Если IP прежний — выходит, не дёргая API.
3. Если IP сменился — обновляет обе A-записи (`adb.example.com` и `vm-host.example.com`, `proxied: false`), сохраняет state и отправляет уведомление в Telegram.

### Что делает `vm_watch.py`
1. Опрашивает системный libvirt (`virsh -c qemu:///system`) и аренды DHCP (`/var/lib/libvirt/dnsmasq/virbr0.status`), собирает состояние всех ВМ, их внутренние IP и реальные порты VNC/SPICE.
2. Отдельно хранит последний успешный опрос, закреплённые слоты портов и последний доставленный в Telegram снимок в `state/vm_state.json`.
3. В режиме `--inventory` отдаёт JSON (включая `port_slots`) для `tunnel.py`.

### Конфигурация на сервере (`/home/vmuser/frida/config.py`, права `600`, в `.gitignore`)
- Cloudflare: `CF_API_TOKEN`, `CF_ZONE_ID`, `CF_DNS_RECORD_ID`, `CF_RECORD_NAME`, `CF_DNS_RECORD_ID_SSH`, `CF_RECORD_NAME_SSH`.
- Telegram: `TELEGRAM_BOT_TOKEN` (от `@BotFather`, не забудьте нажать `/start` в чате с ботом), `TELEGRAM_CHAT_ID`.
- Пароль VNC никогда не хранится в `config.py` и не пересылается в Telegram или логи.
