# -*- coding: utf-8 -*-
"""
config.example.py — шаблон конфига для frida-скриптов.

Скопируйте этот файл как config.py и подставьте свои значения:
    cp config.example.py config.py

ВАЖНО: настоящий config.py добавлен в .gitignore и НИКОГДА не коммитится.
Токен Cloudflare лучше задавать переменной окружения CF_API_TOKEN,
а не хранить в файле.
"""

# Serial устройства для adb: домен:5555 (домен обновляется update_dns.py)
# или IP:5555. Когда скрипты запускаются прямо на debian-nested,
# можно указать внутренний IP VM: 10.166.0.129:5555
ADB_SERIAL = "adb.example.com:5555"

# Cloudflare API (для update_dns.py).
# Токен: переменная окружения CF_API_TOKEN имеет приоритет над этим значением.
# Токен должен иметь право редактировать DNS в зоне. Настоящий токен сюда не пишем.
CF_API_TOKEN = ""
CF_ZONE_ID = ""
CF_DNS_RECORD_ID = ""
CF_RECORD_NAME = "adb.example.com"

# Ссылки на APK для setup.py (если APK нет локально).
# Подставьте прямые ссылки на скачивание, например с APKMirror.
# Пустая строка = setup.py пропустит установку этого приложения
# (можно передать локальный файл через --chrome-apk / --google-one-apk).
CHROME_APK_URL = ""
GOOGLE_ONE_APK_URL = ""

# Папка кеша скачанных APK (относительно папки скриптов).
DOWNLOADS_DIR = "downloads"
