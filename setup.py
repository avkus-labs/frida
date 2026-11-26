#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup.py — подготовка свежего Android (Bliss OS) и окружения Python для frida-скриптов.

Что делает:
  1. Проверяет интерпретаторы python / python3 / py и ставит frida-tools
     в каждый, где его нет.
  2. Находит adb, подключается к устройству по serial (домен:5555 или IP:5555)
     и проверяет готовность устройства (wait-for-device).
  3. Включает root через `adb root`.
  4. Опционально ставит заглушку su в /system/bin/su (--install-su-shim).
  5. Устанавливает Google Chrome и Google One (adb install; APK скачиваются
     во временный .part-файл с проверкой размера и опционального SHA-256).
  6. Печатает итоговую сводку и возвращает ненулевой код при любой ошибке.

Только стандартная библиотека. Работает на Windows, macOS и Linux.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

CHROME_PKG = "com.android.chrome"
GOOGLE_ONE_PKG = "com.google.android.apps.subscriptions.red"

# Заглушка su: оболочка adb уже работает от root (adb root), поэтому su просто
# запускает переданную команду.
# Обрабатывает: su -c "cmd", su 0 ..., su root -c "cmd", su (интерактивно).
SU_SHIM = """#!/system/bin/sh
# su-заглушка для оболочки adb root.
case "$1" in
  -c) shift; exec /system/bin/sh -c "$*" ;;
  0|root)
    shift
    case "$1" in
      -c) shift; exec /system/bin/sh -c "$*" ;;
      "") exec /system/bin/sh ;;
      *) exec "$@" ;;
    esac
    ;;
  "") exec /system/bin/sh ;;
  *) exec /system/bin/sh -c "$*" ;;
esac
"""

DEFAULT_CONFIG = {
    "ADB_SERIAL": "",
    "CHROME_APK_URL": "",
    "GOOGLE_ONE_APK_URL": "",
    "CHROME_APK_SHA256": "",
    "GOOGLE_ONE_APK_SHA256": "",
    "DOWNLOADS_DIR": "downloads",
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
    """Читает config.py рядом со скриптом, если он есть, иначе берёт значения по умолчанию."""
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


def resolve_downloads_dir(cfg):
    d = Path(cfg.get("DOWNLOADS_DIR") or "downloads")
    if not d.is_absolute():
        d = HERE / d
    return d


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


# ── Python и frida-tools ─────────────────────────────────────────────────────

def detect_interpreters():
    """Находит интерпретаторы python / python3 / py (без дублей по реальному пути)."""
    found = {}
    for name in ("python", "python3", "py"):
        path = shutil.which(name)
        if path:
            found[os.path.realpath(path)] = path
    return list(found.values())


def frida_version(interp):
    """Возвращает версию frida для интерпретатора или '' если модуль не импортируется."""
    try:
        r = subprocess.run(
            [interp, "-c", "import frida; print(frida.__version__)"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return ""
    if r.returncode == 0:
        return (r.stdout or "").strip()
    return ""


def ensure_frida(interp):
    """Гарантирует frida-tools в интерпретаторе. Возвращает (ok, версия)."""
    ver = frida_version(interp)
    if ver:
        ok(f"frida-tools уже есть в {interp}: {ver}")
        return True, ver
    info(f"frida-tools нет в {interp}, установка через pip…")
    r = subprocess.run(
        [interp, "-m", "pip", "install", "-U", "frida-tools"],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        fail(f"Не удалось установить frida-tools в {interp}:")
        print((r.stderr or r.stdout or "").strip()[-2000:], flush=True)
        return False, ""
    ver = frida_version(interp)
    if not ver:
        fail(f"frida-tools установлен в {interp}, но модуль frida не импортируется")
        return False, ""
    ok(f"frida-tools установлен в {interp}: {ver}")
    return True, ver


# ── adb ──────────────────────────────────────────────────────────────────────

def find_adb(explicit=None):
    """Ищет adb: явный путь, PATH, ANDROID_HOME/ANDROID_SDK_ROOT, типовые места."""
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
    candidates = [
        Path(r"C:\platform-tools") / exe,
        home / "Android" / "Sdk" / "platform-tools" / exe,
        home / "Library" / "Android" / "sdk" / "platform-tools" / exe,
        Path("/usr/bin") / exe,
        Path("/usr/local/bin") / exe,
        Path("/opt/android-sdk") / "platform-tools" / exe,
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return ""


class Adb:
    def __init__(self, adb_bin, serial):
        self.adb = adb_bin
        self.serial = serial

    def run(self, *args, timeout=120):
        """adb [-s serial] <args>. Возвращает CompletedProcess."""
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

    def wait(self, timeout=120):
        try:
            r = self.run("wait-for-device", timeout=timeout)
        except Exception as e:
            fail(f"Устройство не отвечает (wait-for-device): {e}")
            return False
        if r.returncode != 0:
            msg = ((r.stderr or "") + (r.stdout or "")).strip()
            fail(f"wait-for-device завершился с ошибкой (код {r.returncode}): {msg}")
            return False
        return True


# ── root и su ────────────────────────────────────────────────────────────────

def has_su(adb):
    """Проверяет заглушку su: su -c id должен вернуть uid=0."""
    out = adb.shell("su", "-c", "id")
    return "uid=0" in out


def install_su_shim(adb):
    """Ставит заглушку su в /system/bin/su. Возвращает True при успехе."""
    if has_su(adb):
        ok("su уже работает (su -c id → uid=0), пропускаем")
        return True
    info("Ставлю заглушку su в /system/bin/su…")
    out = adb.shell("mount", "-o", "remount,rw", "/")
    if "Read-only" in out or "not in /proc/mounts" in out:
        warn(f"Не удалось перемонтировать / в rw: {out.strip()}")
    heredoc = "cat > /system/bin/su <<'SU_EOF'\n" + SU_SHIM + "SU_EOF\n"
    adb.shell(heredoc)
    adb.shell("chmod", "755", "/system/bin/su")
    if has_su(adb):
        ok("Заглушка su установлена и работает")
        return True
    warn("Heredoc не сработал, пробую через adb push…")
    tmp = Path(tempfile.gettempdir()) / f"su-shim-{os.getpid()}"
    try:
        tmp.write_text(SU_SHIM, encoding="utf-8")
        r = adb.run("push", str(tmp), "/data/local/tmp/su")
        if r.returncode != 0:
            fail(f"adb push заглушки su не удался (код {r.returncode})")
            return False
    finally:
        tmp.unlink(missing_ok=True)
    adb.shell("mount", "-o", "remount,rw", "/")
    adb.shell("cp", "/data/local/tmp/su", "/system/bin/su")
    adb.shell("chmod", "755", "/system/bin/su")
    if has_su(adb):
        ok("Заглушка su установлена и работает (через push)")
        return True
    fail("Не удалось установить заглушку su (su -c id не даёт uid=0)")
    return False


def ensure_root(adb):
    """adb root + проверка, что оболочка от root."""
    info("Включаю root (adb root)…")
    out = adb.out("root")
    info(f"adb root: {out.strip()}")
    ident = adb.shell("id")
    if "uid=0" in ident:
        ok("Оболочка adb работает от root (uid=0)")
        return True
    fail(f"После adb root оболочка всё ещё не root: {ident.strip()}")
    return False


# ── приложения ───────────────────────────────────────────────────────────────

def is_installed(adb, pkg):
    """Проверяет ТОЧНОЕ совпадение имени пакета в `pm list packages`."""
    out = adb.shell("pm", "list", "packages", pkg)
    expected = f"package:{pkg}"
    return any(line.strip() == expected for line in (out or "").splitlines())


def validate_apk_file(path, min_bytes=1_000_000, expected_sha256=""):
    """Проверяет размер и опциональный SHA-256 файла APK."""
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size < min_bytes:
        fail(f"Файл APK подозрительно мал ({size} байт): {path}")
        return False
    if expected_sha256:
        got = sha256_file(path)
        if got != expected_sha256.strip().lower():
            fail(f"SHA-256 APK не совпал ({got} != {expected_sha256.strip().lower()}): {path}")
            return False
    return True


def download_apk(url, dest, expected_sha256=""):
    """Скачивает APK во временный файл и переименовывает в dest только после проверки."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    info(f"Скачиваю {url} → {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(part, "wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        part.unlink(missing_ok=True)
        fail(f"Не удалось скачать {url}: {e}")
        return False

    if not validate_apk_file(part, min_bytes=1_000_000, expected_sha256=expected_sha256):
        part.unlink(missing_ok=True)
        return False

    part.replace(dest)
    ok(f"Скачано: {dest} ({dest.stat().st_size // 1_048_576} МБ)")
    return True


def ensure_app(
    adb, pkg, label, apk_url, local_apk, downloads_dir, force=False, expected_sha256=""
):
    """Устанавливает приложение, если его нет (или --force). Возвращает True/False."""
    if is_installed(adb, pkg) and not force:
        ok(f"{label} уже установлен ({pkg}), пропускаем")
        return True
    if local_apk:
        apk = Path(local_apk)
        if not apk.is_file() or apk.stat().st_size == 0:
            fail(f"Локальный APK не найден или пуст: {apk}")
            return False
        if expected_sha256 and not validate_apk_file(apk, min_bytes=1, expected_sha256=expected_sha256):
            return False
    else:
        if not apk_url:
            warn(
                f"Нет ни локального APK, ни ссылки для {label}. "
                "Укажите --chrome-apk/--google-one-apk или задайте ссылку в config.py"
            )
            return False
        downloads_dir = Path(downloads_dir)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        apk = downloads_dir / f"{pkg}.apk"
        if apk.exists():
            if validate_apk_file(apk, min_bytes=1_000_000, expected_sha256=expected_sha256):
                info(f"Проверенный APK уже в кеше: {apk}")
            else:
                warn(f"Удаляю повреждённый или непроверенный APK из кеша: {apk}")
                apk.unlink(missing_ok=True)
        if not apk.exists():
            if not download_apk(apk_url, apk, expected_sha256=expected_sha256):
                return False

    info(f"Устанавливаю {label} (adb install)…")
    args = ["install", "-r"] if force else ["install"]
    r = adb.run(*args, str(apk), timeout=600)
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    if text:
        print(text, flush=True)
    if r.returncode == 0 and "Success" in text and "failure" not in text.lower():
        ok(f"{label} установлен")
        return True
    fail(f"Не удалось установить {label} (код возврата adb={r.returncode})")
    return False


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Подготовка свежего Android (Bliss OS) и Python для frida-скриптов."
    )
    p.add_argument("--serial", default="", help="Serial устройства, например 127.0.0.1:15551")
    p.add_argument("--adb", default="", help="Путь к adb (если не в PATH)")
    p.add_argument("--chrome-apk", default="", help="Локальный путь к APK Google Chrome")
    p.add_argument("--google-one-apk", default="", help="Локальный путь к APK Google One")
    p.add_argument("--force", action="store_true", help="Переустановить приложения, даже если уже стоят")
    p.add_argument("--skip-frida", action="store_true", help="Не проверять и не ставить frida-tools")
    p.add_argument("--skip-apps", action="store_true", help="Не устанавливать Chrome и Google One")
    p.add_argument("--install-su-shim", action="store_true", help="Поставить заглушку /system/bin/su (для совместимости со старыми скриптами)")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()

    print("=" * 64)
    print("  setup.py — подготовка Android и Python")
    print("=" * 64)

    results = {}

    # 1. frida-tools в каждом интерпретаторе.
    if args.skip_frida:
        info("Проверка frida-tools пропущена (--skip-frida)")
    else:
        interps = detect_interpreters()
        if not interps:
            fail("Не найден ни один интерпретатор python/python3/py")
            return 1
        info(f"Найдены интерпретаторы: {', '.join(interps)}")
        for interp in interps:
            ok_frida, ver = ensure_frida(interp)
            results[f"frida:{interp}"] = f"{ver}" if ok_frida else "ОШИБКА"
        if any(v == "ОШИБКА" for v in results.values()):
            fail("frida-tools не удалось поставить хотя бы в один интерпретатор")
            return 1

    # 2. adb.
    adb_bin = find_adb(args.adb)
    if not adb_bin:
        fail("adb не найден. Укажите --adb или добавьте platform-tools в PATH")
        return 1
    ok(f"adb: {adb_bin}")

    # 3. serial.
    serial = args.serial or cfg.get("ADB_SERIAL") or ""
    if not serial:
        serial = input("Serial устройства (домен:5555 или IP:5555): ").strip()
    if not serial:
        fail("Serial не задан")
        return 1
    adb = Adb(adb_bin, serial)

    if not adb.connect():
        return 1
    if not adb.wait():
        return 1

    # 4. root.
    if not ensure_root(adb):
        return 1
    results["root"] = "uid=0"

    # 5. заглушка su (только если явно запрошена).
    if args.install_su_shim:
        if not install_su_shim(adb):
            return 1
        results["su"] = "работает (uid=0)"
    else:
        results["su"] = "не требуется (adb root)"

    # 6. приложения.
    apps_failed = False
    if args.skip_apps:
        info("Установка приложений пропущена (--skip-apps)")
    else:
        downloads_dir = resolve_downloads_dir(cfg)
        ok_chrome = ensure_app(
            adb, CHROME_PKG, "Google Chrome",
            cfg.get("CHROME_APK_URL") or "", args.chrome_apk,
            downloads_dir, force=args.force,
            expected_sha256=cfg.get("CHROME_APK_SHA256") or "",
        )
        ok_one = ensure_app(
            adb, GOOGLE_ONE_PKG, "Google One",
            cfg.get("GOOGLE_ONE_APK_URL") or "", args.google_one_apk,
            downloads_dir, force=args.force,
            expected_sha256=cfg.get("GOOGLE_ONE_APK_SHA256") or "",
        )
        results["chrome"] = "установлен" if ok_chrome else "НЕ УСТАНОВЛЕН"
        results["google_one"] = "установлен" if ok_one else "НЕ УСТАНОВЛЕН"
        if not (ok_chrome and ok_one):
            apps_failed = True
            fail("Не все приложения установлены — см. сообщения выше")

    # 7. Сводка.
    print()
    print("=" * 64)
    print("  Итог setup.py")
    print("=" * 64)
    print(f"  Устройство: {serial}")
    for key, value in results.items():
        print(f"  {key}: {value}")
    print()
    if apps_failed:
        return 1
    print("  Дальше: сделайте резервную копию рабочей VM, затем запускайте interactive.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
