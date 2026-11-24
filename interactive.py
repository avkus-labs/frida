#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
interactive.py — интерактивный вход в Google-аккаунт и выбор тарифа Google One.

Что делает:
  1. Подключается к устройству по serial (домен:5555 или IP:5555), проверяет root.
  2. Проверяет Google-аккаунты на устройстве. Если аккаунт уже есть — предлагает
     использовать его или добавить новый. Если нет — проводит через вход:
     email → пароль → 2FA (если нужна).
  3. Открывает Google One.
  4. Показывает нумерованный список тарифов (из GROUPS в main.py или из offers.txt)
     и вызывает `python main.py --serial <serial> --plan <id>`.
  5. После отработки main.py спрашивает, сработал ли план; если нет — предлагает
     выбрать другой тариф или выйти; если да — напоминает, что ввод карты вручную.

Пароль и код 2FA никогда не берутся из аргументов командной строки —
только через getpass/input. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

GOOGLE_ONE_PKG = "com.google.android.apps.subscriptions.red"
GOOGLE_ONE_ACT = (
    GOOGLE_ONE_PKG + "/com.google.android.apps.subscriptions.red.main.MainActivity"
)

DEFAULT_CONFIG = {
    "ADB_SERIAL": "",
    "DOWNLOADS_DIR": "downloads",
}

# Регулярка для поиска Google-аккаунтов в `dumpsys account` (как в main.py).
ACCOUNT_RE = re.compile(r"Account \{name=([^,}]+),\s*type=com\.google")
ACCOUNT_RE_ALT = re.compile(r"type=com\.google[^\n]*name=([^\s,\}]+)")


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
        info(f"Конфиг загружен: {cfg_path}")
    except Exception as e:
        warn(f"Не удалось прочитать config.py ({e}), используются значения по умолчанию")
    return cfg


# ── adb ──────────────────────────────────────────────────────────────────────

def find_adb(explicit=None):
    if explicit:
        return explicit
    p = shutil.which("adb")
    if p:
        return p
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        base = os.environ.get(var)
        if base:
            cand = Path(base) / "platform-tools" / exe
            if cand.exists():
                return str(cand)
    home = Path.home()
    for cand in (
        Path(r"C:\platform-tools") / exe,
        home / "Android" / "Sdk" / "platform-tools" / exe,
        home / "Library" / "Android" / "sdk" / "platform-tools" / exe,
        Path("/usr/bin") / exe,
        Path("/usr/local/bin") / exe,
    ):
        if cand.exists():
            return str(cand)
    return ""


class Adb:
    def __init__(self, adb_bin, serial):
        self.adb = adb_bin
        self.serial = serial

    def run(self, *args, timeout=120):
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def out(self, *args, timeout=120):
        r = self.run(*args, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")

    def shell(self, *args, timeout=120):
        return self.out("shell", *args, timeout=timeout)

    def connect(self):
        r = self.run("connect", self.serial, timeout=60)
        text = ((r.stdout or "") + (r.stderr or "")).strip()
        info(f"adb connect: {text}")
        out = subprocess.run(
            [self.adb, "devices"], capture_output=True, text=True, timeout=60
        ).stdout or ""
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                ok(f"Устройство подключено: {self.serial}")
                return True
        fail(f"Устройство {self.serial} не появилось в списке adb devices")
        print(out, flush=True)
        return False


# ── ввод текста через adb ────────────────────────────────────────────────────

def adb_input_text(adb, text):
    """Отправляет текст в активное поле: пробелы → %s, экранирование для shell устройства."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
        .replace(" ", "%s")
    )
    adb.shell("input", "text", f'"{escaped}"')


def press_enter(adb):
    adb.shell("input", "keyevent", "66")


def wait_user(msg="Нажмите Enter, чтобы продолжить…"):
    input(msg)


# ── Google-аккаунты ──────────────────────────────────────────────────────────

def google_accounts(adb):
    out = adb.shell("dumpsys", "account")
    names = ACCOUNT_RE.findall(out or "")
    if names:
        return [n.strip() for n in names]
    return [n.strip() for n in ACCOUNT_RE_ALT.findall(out or "")]


def add_account_flow(adb, prefill_email=""):
    """Интерактивный вход в Google-аккаунт через экран добавления аккаунта."""
    print()
    print("  Открою экран добавления Google-аккаунта.")
    print("  Если поле ввода не в фокусе — ткните в него мышкой в окне VNC,")
    print("  и только потом нажимайте Enter здесь.")
    adb.shell("am", "start", "-a", "android.settings.ADD_ACCOUNT_SETTINGS")
    wait_user("  Экран добавления аккаунта открыт. Нажмите Enter, когда будете готовы ввести email…")

    email = prefill_email or input("  Email (логин Google): ").strip()
    while not email:
        email = input("  Email не может быть пустым, введите ещё раз: ").strip()
    adb_input_text(adb, email)
    press_enter(adb)
    ok("Email отправлен, нажат Enter")
    wait_user("  Нажмите Enter, когда появится поле пароля…")

    password = getpass.getpass("  Пароль (не отображается при вводе): ")
    while not password:
        password = getpass.getpass("  Пароль не может быть пустым, введите ещё раз: ")
    adb_input_text(adb, password)
    press_enter(adb)
    ok("Пароль отправлен, нажат Enter")
    wait_user("  Нажмите Enter, когда экран после пароля загрузится…")

    answer = input("  Нужна двухфакторная аутентификация? (да/нет): ").strip().lower()
    if answer in ("да", "д", "y", "yes"):
        code = input("  Код 2FA: ").strip()
        while not code:
            code = input("  Код не может быть пустым, введите ещё раз: ").strip()
        adb_input_text(adb, code)
        press_enter(adb)
        ok("Код 2FA отправлен, нажат Enter")
    else:
        info("2FA пропущена")
    wait_user("  Нажмите Enter, когда вход завершится (или появится следующий экран)…")

    accounts = google_accounts(adb)
    if accounts:
        ok(f"На устройстве теперь есть Google-аккаунт(ы): {', '.join(accounts)}")
        return True
    warn(
        "Аккаунт в dumpsys пока не виден. Возможно, вход ещё не завершён "
        "(подтверждение на телефоне, капча и т.п.). Проверьте экран в VNC."
    )
    again = input("  Попробовать вход ещё раз? (да/нет): ").strip().lower()
    if again in ("да", "д", "y", "yes"):
        return add_account_flow(adb, prefill_email=email)
    return False


def choose_account(adb, prefill_email=""):
    """Выбирает существующий аккаунт или запускает вход в новый. Возвращает True/False."""
    accounts = google_accounts(adb)
    if not accounts:
        info("Google-аккаунтов на устройстве нет — переходим к входу")
        return add_account_flow(adb, prefill_email=prefill_email)
    print()
    print("  Google-аккаунты на устройстве:")
    for i, acc in enumerate(accounts, 1):
        print(f"  {i}. {acc}")
    print(f"  {len(accounts) + 1}. Добавить новый аккаунт")
    choice = input("  Выберите номер (или Enter — использовать первый): ").strip()
    if not choice:
        ok(f"Используем аккаунт: {accounts[0]}")
        return True
    try:
        n = int(choice)
    except ValueError:
        warn("Не номер — считаем, что нужен новый аккаунт")
        return add_account_flow(adb, prefill_email=prefill_email)
    if 1 <= n <= len(accounts):
        ok(f"Используем аккаунт: {accounts[n - 1]}")
        return True
    return add_account_flow(adb, prefill_email=prefill_email)


# ── тарифы ───────────────────────────────────────────────────────────────────

def load_plans():
    """Возвращает список (plan_id, группа/примечание).

    Сначала пробует взять GROUPS из main.py (import main), если не вышло —
    парсит offers.txt (табы: key, sku, offer) рядом со скриптом.
    """
    try:
        sys.path.insert(0, str(HERE))
        from main import GROUPS  # noqa: F401
        rows = []
        for title, items in GROUPS:
            for pid in items:
                rows.append((pid, title))
        if rows:
            return rows
    except BaseException as e:
        warn(f"Не удалось взять тарифы из main.py ({e}), читаю offers.txt")
    offers = HERE / "offers.txt"
    rows = []
    if offers.exists():
        for line in offers.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append((parts[0].strip(), parts[2].strip()))
            elif len(parts) >= 1:
                rows.append((parts[0].strip(), ""))
    return rows


def show_plans(rows):
    print()
    print("=" * 64)
    print("  Тарифы Google One")
    print("=" * 64)
    for i, (pid, note) in enumerate(rows, 1):
        print(f"  {i:3d}. {pid:<16} {note}")
    print()
    print("  Введите номер или id тарифа, q — выход")
    print()


def pick_plan(rows, prefilled=None):
    """Возвращает plan_id или '' (выход)."""
    if prefilled:
        for pid, _ in rows:
            if pid == prefilled:
                return pid
        warn(f"Тариф {prefilled} не найден в списке, покажу меню")
    while True:
        show_plans(rows)
        choice = input("  Тариф: ").strip()
        if choice.lower() in ("q", "выход", "exit"):
            return ""
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(rows):
                return rows[n - 1][0]
            warn("Нет такого номера")
            continue
        for pid, _ in rows:
            if pid == choice:
                return pid
        warn("Такого тарифа нет в списке, попробуйте ещё раз")


# ── запуск main.py ───────────────────────────────────────────────────────────

def frida_version(interp):
    try:
        r = subprocess.run(
            [interp, "-c", "import frida; print(frida.__version__)"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return ""
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def pick_python_for_main():
    """Выбирает интерпретатор для main.py: тот, где импортируется frida."""
    candidates = []
    if sys.executable:
        candidates.append(sys.executable)
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and p not in candidates:
            candidates.append(p)
    for interp in candidates:
        if frida_version(interp):
            return interp
    warn("frida не импортируется ни в одном интерпретаторе — запустите setup.py")
    return candidates[0] if candidates else sys.executable


def run_main(serial, plan_id, renew=False):
    """Запускает main.py с выводом в терминал. Возвращает код возврата."""
    main_py = HERE / "main.py"
    if not main_py.exists():
        fail(f"main.py не найден рядом со скриптом: {main_py}")
        return 1
    interp = pick_python_for_main()
    cmd = [interp, str(main_py), "--serial", serial, "--plan", plan_id]
    if renew:
        cmd.append("--renew")
    info(f"Запускаю: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd)
        return r.returncode
    except FileNotFoundError:
        fail(f"Не удалось запустить интерпретатор: {interp}")
        return 1


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Интерактивный вход в Google-аккаунт и выбор тарифа Google One."
    )
    p.add_argument("--serial", default="", help="Serial устройства, например adb.example.com:5555")
    p.add_argument("--adb", default="", help="Путь к adb (если не в PATH)")
    p.add_argument("--plan", default="", help="ID тарифа, чтобы пропустить меню (например pro_12m)")
    p.add_argument("--renew", action="store_true", help="Режим продления действующей подписки")
    p.add_argument("--email", default="", help="Email для предзаполнения при входе")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    print("=" * 64)
    print("  interactive.py — Google-аккаунт и тариф Google One")
    print("=" * 64)

    adb_bin = find_adb(args.adb)
    if not adb_bin:
        fail("adb не найден. Укажите --adb или добавьте platform-tools в PATH")
        return 1
    ok(f"adb: {adb_bin}")

    serial = args.serial or cfg.get("ADB_SERIAL") or ""
    if not serial:
        serial = input("Serial устройства (домен:5555 или IP:5555): ").strip()
    if not serial:
        fail("Serial не задан")
        return 1
    adb = Adb(adb_bin, serial)
    if not adb.connect():
        return 1

    # Root: main.py требует su, поэтому предупреждаем заранее.
    if "uid=0" not in adb.shell("su", "-c", "id"):
        warn("На устройстве нет root (su -c id не даёт uid=0). Запустите setup.py — иначе main.py не сработает.")
        cont = input("Продолжить без root? (да/нет): ").strip().lower()
        if cont not in ("да", "д", "y", "yes"):
            return 1
    else:
        ok("Root доступен (su -c id → uid=0)")

    # Аккаунт.
    if not choose_account(adb, prefill_email=args.email):
        warn("Вход в аккаунт не подтверждён. Продолжаю на свой страх и риск.")
    else:
        ok("Аккаунт готов")

    # Google One.
    info("Открываю Google One…")
    adb.shell("am", "start", "-n", GOOGLE_ONE_ACT)

    # Тарифы.
    rows = load_plans()
    if not rows:
        fail("Список тарифов пуст: нет ни GROUPS в main.py, ни offers.txt рядом со скриптом")
        return 1
    ok(f"Загружено тарифов: {len(rows)}")

    plan_id = pick_plan(rows, prefilled=args.plan)
    while plan_id:
        rc = run_main(serial, plan_id, renew=args.renew)
        if rc != 0:
            warn(f"main.py завершился с кодом {rc}")
        print()
        answer = input("  Экран оформления тарифа открылся / план сработал? (да/нет): ").strip().lower()
        if answer in ("да", "д", "y", "yes"):
            print()
            print("  План сработал. Дальше — ручная работа: ввод карты на экране оформления.")
            print("  Скрипт дальше ничего не делает, карту вводите сами.")
        else:
            print()
            print("  План не сработал (экран оформления не открылся).")
        choice = input("  Выбрать другой тариф или выйти? (номер/план или q): ").strip()
        if choice.lower() in ("q", "выход", "exit", ""):
            break
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(rows):
                plan_id = rows[n - 1][0]
                continue
            warn("Нет такого номера")
            plan_id = pick_plan(rows)
            continue
        found = [pid for pid, _ in rows if pid == choice]
        if found:
            plan_id = found[0]
            continue
        warn("Такого тарифа нет в списке")
        plan_id = pick_plan(rows)

    print()
    print("  Готово. Выход.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
