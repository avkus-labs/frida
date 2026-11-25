# Ежедневный запуск (Windows и macOS)

## 1. Запуск одной или нескольких ВМ

### Шаг 1. Создать и запустить нужный клон на сервере
```bash
ssh -p 2222 avkuska@debian-nested.avkus.bond "sudo new_bliss.sh bliss-01"
```
Сохраните **8-символьный пароль VNC** из вывода. Подождите ~15–20 секунд, пока загрузится Android.

### Шаг 2. Поднять автоматический туннель (`tunnel.py`) — Окно 1
Скрипт сам спросит `vm_watch.py --inventory` на `debian-nested`, найдёт все запущенные ВМ и поднимет пробросы:
- для 1-й ВМ: `ADB 127.0.0.1:15551` и `VNC 127.0.0.1:15901`
- для 2-й ВМ: `ADB 127.0.0.1:15552` и `VNC 127.0.0.1:15902` и т.д.

```bash
# На Windows (в E:\frida) или на macOS (в ~/frida):
python tunnel.py --dry-run   # посмотреть, какие порты назначены каким ВМ
python tunnel.py             # поднять туннели (окно не закрывать, выход Ctrl+C)
```
*(Порты `15551+` выбраны специально, чтобы `adb` не путал туннель с `emulator-5554`.)*

### Шаг 3. Открыть экран (VNC через туннель)
- **Windows (TightVNC Viewer):** подключиться к `127.0.0.1::15901` (для 2-й ВМ — `127.0.0.1::15902`).
- **macOS (встроенный Screen Sharing):**
  ```bash
  open vnc://127.0.0.1:15901
  ```

### Шаг 4. Подключить ADB и запустить `main.py` / `interactive.py` — Окно 2
На **Windows**:
```powershell
cd E:\frida
adb connect 127.0.0.1:15551
python main.py --serial 127.0.0.1:15551
# или python interactive.py --serial 127.0.0.1:15551
```
На **macOS**:
```bash
cd ~/frida && source .venv/bin/activate
adb connect 127.0.0.1:15551
python main.py --serial 127.0.0.1:15551
```

---

## 2. Если одновременно запущено 2+ клона
Перед запуском `main.py` на втором клоне обязательно смените ему `android_id`, иначе `_dedupe()` в `main.py` посчитает два клона одним устройством:
```bash
adb connect 127.0.0.1:15552
adb -s 127.0.0.1:15552 shell 'settings put secure android_id $(cat /proc/sys/kernel/random/uuid | tr -d - | cut -c1-16)'
python main.py --serial 127.0.0.1:15552
```

---

## 3. Завершение и удаление отработанного клона
1. Закройте `tunnel.py` (`Ctrl + C`).
2. Удалите клон на сервере:
   ```bash
   ssh -p 2222 avkuska@debian-nested.avkus.bond "sudo virsh destroy bliss-01; sudo virsh undefine bliss-01 --remove-all-storage"
   ```

---

## 4. Быстрый траблшутинг

| Проблема | Причина | Решение |
|---|---|---|
| `device '127.0.0.1:15551' not found` | Не выполнен `adb connect` | Выполнить `adb connect 127.0.0.1:15551` (и подождать 10 сек, если ВМ только стартовала) |
| `script has been destroyed` в `main.py` | Процесс Google One закрылся/перезапустился | В меню `main.py` ввести `g` (перезапуск и переаттач) |
| Окно оплаты открывается и сразу закрывается | Уход фокуса / `Add payment method` внутри шторки сбрасывает сессию / ошибка Play (`code=1/4/5`) | 1) Заранее добавить карту в **Google Play → Payments & subscriptions → Payment methods**; 2) Перед тарифом нажать `g` в `main.py`; 3) Смотреть `[g1] purchase_cb code=...` |
| Промо «Want to pay with cash?» | Информационное окно Play для региона US | Нажать `OK` |
| `Telegram 401 Unauthorized` в логах `update_dns` / `vm_watch` | Неверный `TELEGRAM_BOT_TOKEN` в `config.py` на сервере | Получить/перевыпустить токен у `@BotFather`, прописать в `config.py` на `debian-nested` и нажать `/start` в чате с ботом |
| Ошибка GitHub `GH001: Large files detected` при `git push` | В коммит попал распакованный `assets/frida-server-*` | `git reset --soft origin/main && git reset HEAD -- assets/` и перекоммитить без `assets/` |
| Проверить состояние всех ВМ, IP и VNC | — | `python tunnel.py --dry-run` или `ssh -p 2222 avkuska@debian-nested.avkus.bond "python3 /home/avkuska/frida/vm_watch.py --inventory"` |
