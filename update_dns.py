#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_dns.py — динамический DNS для доменов debian-nested через Cloudflare API.

Что делает:
  1. Узнаёт текущий внешний IP хоста: сначала GCP metadata server,
     затем https://api.ipify.org, затем https://ifconfig.me.
  2. Читает последний отправленный IP из state-файла (по умолчанию
     state/dns_last_ip.txt рядом со скриптом).
  3. Если IP не изменился — ничего не делает и НЕ дергает API Cloudflare.
  4. Если изменился — обновляет A-записи через Cloudflare API
     (PUT /zones/{zone_id}/dns_records/{record_id}) и только при успехе
     записывает новый IP в state-файл.

Обновляет две записи (обе DNS-only, без прокси):
  - ADB:  CF_RECORD_NAME (например adb.example.com)
  - SSH:  CF_RECORD_NAME_SSH (например vm-host.example.com)
Вторая запись необязательна: если CF_DNS_RECORD_ID_SSH / CF_RECORD_NAME_SSH
не заданы, обновляется только первая.

Telegram-хук: после успешной смены IP отправляет одно сообщение
в Telegram (Bot API sendMessage). Токен и chat_id берутся из
переменных окружения TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID или из
config.py. Если Telegram не настроен — просто пропускается.
Неудача отправки НЕ отменяет обновление DNS.

Токен берётся из переменной окружения CF_API_TOKEN (или из config.py).
Настоящий токен никогда не кладётся в репозиторий.
Только стандартная библиотека. Для запуска по cron на debian-nested.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

GCP_METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "network-interfaces/0/access-configs/0/external-ip"
)
IPIFY_URL = "https://api.ipify.org"
IFCONFIG_URL = "https://ifconfig.me"

DEFAULT_CONFIG = {
    "CF_API_TOKEN": "",
    "CF_ZONE_ID": "",
    "CF_DNS_RECORD_ID": "",
    "CF_RECORD_NAME": "adb.example.com",
    # Вторая запись (SSH, та же зона). Необязательно.
    "CF_DNS_RECORD_ID_SSH": "",
    "CF_RECORD_NAME_SSH": "",
    # Telegram (уведомление при смене IP). Необязательно.
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
}


def info(msg):
    print(f"[*] {msg}", flush=True)


def ok(msg):
    print(f"[+] {msg}", flush=True)


def warn(msg):
    print(f"[!] {msg}", flush=True)


def fail(msg):
    print(f"[x] {msg}", flush=True)


# ── конфиг ───────────────────────────────────────────────────────────────────

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg_path = HERE / "config.py"
    if not cfg_path.exists():
        return cfg
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("frida_config", cfg_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for key in cfg:
            if hasattr(mod, key):
                cfg[key] = getattr(mod, key)
    except Exception as e:
        warn(f"Не удалось прочитать config.py ({e}), используются значения по умолчанию")
    return cfg


# ── внешний IP ───────────────────────────────────────────────────────────────

def fetch_text(url, headers=None, timeout=5):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace").strip()


def is_valid_ipv4(value):
    try:
        ipaddress.IPv4Address((value or "").strip())
        return True
    except ValueError:
        return False


def get_external_ip():
    """Возвращает внешний IPv4 или '' если узнать не удалось."""
    # 1. GCP metadata server (работает только на VM в Google Cloud).
    try:
        ip = fetch_text(
            GCP_METADATA_URL, headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        if is_valid_ipv4(ip):
            info(f"Внешний IP из GCP metadata: {ip}")
            return ip
    except Exception as e:
        info(f"GCP metadata недоступен ({e}), пробую публичные сервисы")
    # 2. Публичные сервисы.
    for url in (IPIFY_URL, IFCONFIG_URL):
        try:
            ip = fetch_text(url, timeout=10)
            if is_valid_ipv4(ip):
                info(f"Внешний IP из {url}: {ip}")
                return ip
        except Exception as e:
            warn(f"Не удалось узнать IP через {url}: {e}")
    return ""


# ── state-файл ───────────────────────────────────────────────────────────────

def read_last_ip(state_file):
    try:
        text = Path(state_file).read_text(encoding="utf-8").strip()
        return text
    except FileNotFoundError:
        return ""
    except Exception as e:
        warn(f"Не удалось прочитать state-файл {state_file}: {e}")
        return ""


def write_last_ip(state_file, ip):
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ip + "\n", encoding="utf-8")


# ── Cloudflare API ───────────────────────────────────────────────────────────

def cf_update_record(token, zone_id, record_id, record_name, ip):
    """Обновляет A-запись. Возвращает (ok, сообщение)."""
    url = (
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    )
    body = json.dumps(
        {
            "type": "A",
            "name": record_name,
            "content": ip,
            "ttl": 120,
            "proxied": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            fail(f"Cloudflare API: HTTP {e.code}")
            return False, f"HTTP {e.code}"
        errors = data.get("errors") or []
        detail = "; ".join(
            str(err.get("message", err)) for err in errors
        ) or f"HTTP {e.code}"
        fail(f"Cloudflare API отклонил обновление: {detail}")
        return False, detail
    except Exception as e:
        fail(f"Ошибка обращения к Cloudflare API: {e}")
        return False, str(e)
    if data.get("success"):
        return True, "Запись обновлена"
    errors = data.get("errors") or []
    detail = "; ".join(str(err.get("message", err)) for err in errors) or "unknown error"
    fail(f"Cloudflare API вернул success=false: {detail}")
    return False, detail


# ── Telegram ─────────────────────────────────────────────────────────────────

def tg_notify(token, chat_id, text):
    """Отправляет одно сообщение в Telegram. Возвращает True при успехе."""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            warn(f"Telegram: HTTP {e.code}")
            return False
        warn(f"Telegram не принял сообщение: {data.get('description') or f'HTTP {e.code}'}")
        return False
    except Exception as e:
        warn(f"Telegram недоступен: {e}")
        return False
    if data.get("ok"):
        return True
    warn(f"Telegram вернул ok=false: {data.get('description') or data}")
    return False


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Обновляет A-запись в Cloudflare, только если внешний IP изменился."
    )
    p.add_argument("--ip", default="", help="Внешний IP вручную (вместо автоопределения)")
    p.add_argument("--state-file", default="", help="Путь к state-файлу (по умолчанию state/dns_last_ip.txt)")
    p.add_argument("--zone-id", default="", help="Cloudflare Zone ID")
    p.add_argument("--record-id", default="", help="Cloudflare DNS Record ID")
    p.add_argument("--record-name", default="", help="Имя DNS-записи, например adb.example.com")
    p.add_argument("--force", action="store_true", help="Обновить запись, даже если IP не изменился")
    p.add_argument("--dry-run", action="store_true", help="Только показать, что было бы сделано, без API и без записи state")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    token = os.environ.get("CF_API_TOKEN") or cfg.get("CF_API_TOKEN") or ""
    zone_id = args.zone_id or os.environ.get("CF_ZONE_ID") or cfg.get("CF_ZONE_ID") or ""
    record_id = args.record_id or os.environ.get("CF_DNS_RECORD_ID") or cfg.get("CF_DNS_RECORD_ID") or ""
    record_name = args.record_name or os.environ.get("CF_RECORD_NAME") or cfg.get("CF_RECORD_NAME") or ""
    # Вторая запись (SSH). Только из env/config, без CLI-аргументов.
    ssh_record_id = os.environ.get("CF_DNS_RECORD_ID_SSH") or cfg.get("CF_DNS_RECORD_ID_SSH") or ""
    ssh_record_name = os.environ.get("CF_RECORD_NAME_SSH") or cfg.get("CF_RECORD_NAME_SSH") or ""
    records = [(zone_id, record_id, record_name)]
    if ssh_record_id and ssh_record_name:
        records.append((zone_id, ssh_record_id, ssh_record_name))

    state_file = args.state_file or str(HERE / "state" / "dns_last_ip.txt")

    # 1. Текущий IP.
    ip = args.ip.strip() if args.ip else get_external_ip()
    if not ip:
        fail("Не удалось узнать внешний IP")
        return 1
    info(f"Текущий внешний IP: {ip}")

    # 2. Сравнение с последним отправленным.
    last_ip = read_last_ip(state_file)
    if last_ip:
        info(f"Последний отправленный IP: {last_ip}")
    if last_ip == ip and not args.force:
        print("IP не изменился, API не трогаем")
        return 0
    if last_ip == ip and args.force:
        info("--force: обновляю запись, хотя IP тот же")

    # 3. Проверка конфига для API.
    if not token:
        fail("Нет токена Cloudflare: задайте переменную окружения CF_API_TOKEN или CF_API_TOKEN в config.py")
        return 1
    for z, r, n in records:
        if not z or not r:
            fail("Нужны Zone ID и Record ID: аргументы --zone-id/--record-id или значения в config.py")
            return 1
        if not n:
            fail("Нужно имя записи: --record-name или CF_RECORD_NAME в config.py")
            return 1

    if args.dry_run:
        for z, r, n in records:
            print(f"[dry-run] Обновил бы A-запись {n} → {ip} (zone {z}, record {r})")
        print("[dry-run] API не вызывался, state-файл не менялся")
        return 0

    # 4. Обновление в Cloudflare (все записи).
    for z, r, n in records:
        info(f"Обновляю A-запись {n} → {ip}…")
        ok_api, msg = cf_update_record(token, z, r, n, ip)
        if not ok_api:
            fail(f"Запись {n} не обновлена: {msg}. State-файл не менялся.")
            return 1
        ok(f"Cloudflare: {n} → {ip}")

    # 5. Только при успехе пишем новый IP в state-файл.
    write_last_ip(state_file, ip)
    ok(f"Новый IP записан в state-файл: {state_file}")

    # 6. Telegram-хук: одно сообщение при смене IP.
    # Неудача отправки НЕ отменяет обновление DNS.
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("TELEGRAM_BOT_TOKEN") or ""
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("TELEGRAM_CHAT_ID") or ""
    if tg_token and tg_chat:
        names = ", ".join(n for _, _, n in records)
        text = f"IP debian-nested обновлён на {ip}\n{names}"
        if tg_notify(tg_token, tg_chat, text):
            ok("Telegram: уведомление отправлено")
        else:
            warn("Telegram: уведомление НЕ отправлено (DNS уже обновлён)")
    else:
        info("Telegram не настроен, уведомление пропущено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
