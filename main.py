# -*- coding: utf-8 -*-
"""
Тарифы Google One

  python main.py

Обнаруживает ADB, подключается к эмулятору или телефону и копирует недостающие компоненты
с обязательной проверкой целостности (SHA-256) до первого запуска.
Требуются root-доступ, вход в аккаунт Google и приложение Google One на устройстве.
После выбора тарифа открывается экран оформления. Подписку подтверждает пользователь.

Режим продления в меню соответствует STACK=true в frida.js.
В этом режиме сначала используется штатный BillingClient.queryPurchasesAsync,
а при пустом ответе — резервный поиск по всем основным тарифам g1.* со стороны ПК.
"""
from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import json
import lzma
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BIN = REPO / "bin"
JS_PATH = HERE / "frida.js"

PKG = "com.google.android.apps.subscriptions.red"
ACT = PKG + "/com.google.android.apps.subscriptions.red.main.MainActivity"
DEX_REMOTE = "/data/local/tmp/module_521.apk"
FRIDA_REMOTE = "/data/local/tmp/frida-server"
PLAY_DB_REMOTE = "/data/data/com.android.vending/databases/library.db"

# Эталонные SHA-256 проверенных артефактов.
EXPECTED_MODULE_SHA256 = "38a1cd132f10b31c3f4ec85d341764c702148175e2db7e480a288468b39b7b74"
KNOWN_FRIDA_XZ_SHA256 = {
    ("17.9.1", "android-x86_64"): "f5f1205ffb3cb145de9264a8c6aa7aa8724a2e33df319d476f2ef67cac453c5f",
    ("17.27.4", "android-x86_64"): "e30e8d8dcefa6d8b78b5b6a613b42c102d5dfa0e0e47ac7ce27590dc8f05a4db",
}
KNOWN_FRIDA_BIN_SHA256 = {
    ("17.9.1", "android-x86_64"): "fd677533f1215654308e06db3c34905ed6a456a39343696b2f38ead09415884d",
    ("17.27.4", "android-x86_64"): "69846bb6e0a554bc776f9e71a57bc03a9af983f8eeec232d5875989e5199a977",
}

ABI_ASSET = {
    "arm64-v8a": "android-arm64",
    "armeabi-v7a": "android-arm",
    "x86_64": "android-x86_64",
    "x86": "android-x86",
}

GROUPS = [
    ("Plus", [
        "helium_12m", "helium_6m", "helium_3m", "helium_1m", "helium_3m_75",
        "plus_6m", "plus_3m", "plus_2tb_6m", "plus_2tb_85",
        "yt_1m", "yt_family", "yt_lite",
    ]),
    ("Pro", [
        "pro_12m", "pro_6m", "pro_6m_2", "pro_6m_ss", "pro_play_3m",
        "pro_3m_75",
        "pro10_1m_90", "pro10_3m_85",
    ]),
    ("Ultra 5x", [
        "ultra5x_12m", "ultra5x_6m", "ultra5x_3m", "ultra5x_1m",
        "ultra20_3m_90", "ultra20_3m_80", "ultra20_3m_75",
    ]),
    ("Ultra 20x", [
        "ultra20x_12m", "ultra20x_6m", "ultra20x_3m", "ultra20x_1m",
        "ultra_1m_90", "ultra_3m_90", "ultra_3m_80", "ultra_1m_75", "ultra_3m_75",
    ]),
]

SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")
SAFE_REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")


def _fix_stdio():
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def info(msg):
    print(f"[*] {msg}", flush=True)


def ok(msg):
    print(f"[+] {msg}", flush=True)


def warn(msg):
    print(f"[!] {msg}", flush=True)


def fail(msg):
    print(f"[x] {msg}", flush=True)


EMU_PORTS = (
    7555, 7556, 16384, 16416, 16448, 16480, 16385,
    5555, 5554, 5556, 5560, 62001, 21503,
)


def find_adb_exe():
    found = shutil.which("adb")
    if found:
        return found
    extras = []
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SDK"):
        root = os.environ.get(key)
        if root:
            extras.append(str(Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")))
    extras += [
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\platform-tools\adb.exe",
        r"C:\Android\sdk\platform-tools\adb.exe",
        r"D:\SDK\platform-tools\adb.exe",
        r"E:\SDK\platform-tools\adb.exe",
    ]
    extras += glob.glob(r"C:\Program Files\Netease\*\*\adb.exe")
    extras += glob.glob(r"D:\Program Files\Netease\*\*\adb.exe")
    extras += glob.glob(r"C:\Program Files\MuMu*\**\adb.exe", recursive=True)
    extras += glob.glob(r"D:\Program Files\MuMu*\**\adb.exe", recursive=True)
    for p in extras:
        if p and os.path.isfile(p):
            return p
    return "adb"


class Adb:
    def __init__(self, serial="", explicit=False):
        self._exe = None
        env_serial = os.environ.get("ANDROID_SERIAL") or ""
        self.serial = serial or env_serial
        self.explicit = bool(explicit or self.serial)

    @property
    def exe(self):
        if not self._exe:
            self._exe = find_adb_exe()
        return self._exe

    @exe.setter
    def exe(self, value):
        self._exe = value

    def _cmd(self, args, serial=None, timeout=None):
        cmd = [self.exe]
        s = self.serial if serial is None else serial
        if s:
            cmd += ["-s", s]
        return subprocess.run(
            cmd + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )

    def run(self, args, serial=None, timeout=None):
        return self._cmd(args, serial=serial, timeout=timeout)

    def shell(self, *parts):
        r = self._cmd(["shell", *parts])
        return ((r.stdout or "") + (r.stderr or "")).strip()

    def devices(self):
        rows = []
        out = self._cmd(["devices"], serial="").stdout or ""
        for ln in out.splitlines()[1:]:
            bits = ln.split()
            if len(bits) >= 2 and bits[-1] == "device":
                rows.append(bits[0])
        return rows

    def _restart_server(self):
        info("Перезапуск сервера ADB")
        self._cmd(["kill-server"], serial="")
        time.sleep(0.8)
        self._cmd(["start-server"], serial="")
        time.sleep(1.0)

    def _connect_emulators(self):
        for port in EMU_PORTS:
            r = self._cmd(["connect", f"127.0.0.1:{port}"], serial="")
            text = ((r.stdout or "") + (r.stderr or "")).strip()
            if "connected" in text.lower() or "already" in text.lower():
                ok(f"adb connect 127.0.0.1:{port}")

    def _fingerprint(self, serial):
        r = self._cmd(["shell", "settings", "get", "secure", "android_id"], serial=serial)
        aid = (r.stdout or "").strip()
        if aid and aid not in ("null", "error"):
            return aid
        r = self._cmd(["shell", "getprop", "ro.serialno"], serial=serial)
        return (r.stdout or "").strip() or serial

    def _dedupe(self, serials):
        best = {}
        order = []
        for s in serials:
            key = self._fingerprint(s)
            if key not in best:
                best[key] = s
                order.append(key)
                continue
            cur = best[key]
            prefer = (s.startswith("emulator-") and not cur.startswith("emulator-")) or (
                cur.startswith("127.0.0.1:") and not s.startswith("127.0.0.1:")
            )
            if prefer:
                best[key] = s
        return [best[k] for k in order]

    def _score(self, serial):
        score = 0
        old = self.serial
        self.serial = serial
        try:
            if "uid=0" in (self.shell("id") + self.shell("su", "-c", "id") + self.shell("su", "0", "id")):
                score += 10
            if "package:" in self.shell("pm", "path", PKG):
                score += 5
            if google_accounts():
                score += 3
        finally:
            self.serial = old
        return score

    def discover(self):
        info(f"adb: {self.exe}")
        rows = self.devices()
        if not rows:
            self._restart_server()
            rows = self.devices()
        if not rows:
            info("Нет подключённых устройств. Поиск локальных эмуляторов MuMu, LDPlayer и Nox")
            self._connect_emulators()
            time.sleep(0.6)
            rows = self.devices()
        if not rows:
            info("Ожидание подключения устройства…")
            try:
                self._cmd(["wait-for-device"], serial="", timeout=15)
            except subprocess.TimeoutExpired:
                pass
            time.sleep(1.0)
            self._connect_emulators()
            rows = self.devices()
        rows = self._dedupe(rows)
        if not rows:
            fail("ADB не видит устройств. Запустите эмулятор или подключите телефон с включённой отладкой по USB.")
            sys.exit(1)
        return rows

    def pick(self):
        # Если устройство задано явно (через --serial, ANDROID_SERIAL или атрибут serial),
        # НИКОГДА не переключаемся на другое устройство при его недоступности.
        if self.serial:
            info(f"adb: {self.exe}")
            rows = self.devices()
            if self.serial not in rows and ":" in self.serial:
                self._cmd(["connect", self.serial], serial="")
                rows = self.devices()
            if self.serial not in rows:
                fail(
                    f"Явно выбранное устройство {self.serial} недоступно в `adb devices`. "
                    "Автоматическая подмена устройства запрещена — операция остановлена."
                )
                sys.exit(1)
            os.environ["ANDROID_SERIAL"] = self.serial
            ok(f"Устройство: {self.serial}")
            return self.serial

        rows = self.discover()
        if len(rows) == 1:
            self.serial = rows[0]
        else:
            scores = {s: self._score(s) for s in rows}
            ranked = sorted(rows, key=lambda s: scores[s], reverse=True)
            self.serial = ranked[0]
            info("Найдено несколько устройств. Выбрано устройство с наибольшей оценкой:")
            for s in ranked:
                info(f"  {s}  score={scores[s]}")
        os.environ["ANDROID_SERIAL"] = self.serial
        ok(f"Устройство: {self.serial}")
        return self.serial


adb = Adb()


def parse_plans(js_text):
    """Parse PLANS from frida.js (including base plans with empty offer)."""
    block = re.search(r"var PLANS = \{([\s\S]*?)\n\};", js_text)
    if not block:
        return {}
    plans = {}
    for m in re.finditer(
        r"(\w+)\s*:\s*\{\s*sku:\s*\"([^\"]+)\"\s*,\s*offer:\s*\"([^\"]*)\"\s*,\s*note:\s*\"([^\"]*)\"",
        block.group(1),
    ):
        plans[m.group(1)] = {"sku": m.group(2), "offer": m.group(3), "note": m.group(4)}
    return plans


def grouped_plans(plans):
    used = set()
    groups = []
    for title, ids in GROUPS:
        items = [(pid, plans[pid]) for pid in ids if pid in plans]
        if items:
            groups.append((title, items))
            used.update(pid for pid, _ in items)
    extra = [(pid, plans[pid]) for pid in plans if pid not in used]
    if extra:
        groups.append(("Другие", extra))
    return groups


def flatten_menu(groups):
    rows = []
    for title, items in groups:
        for pid, spec in items:
            rows.append((title, pid, spec))
    return rows


def print_menu(plans, stack, addon):
    groups = grouped_plans(plans)
    rows = flatten_menu(groups)
    mode = "Продление действующей подписки (STACK=true)" if stack else "Новая подписка (STACK=false)"
    print()
    print("=" * 64)
    print("  Тарифы Google One")
    print(f"  Режим: {mode}")
    print(f"  Дополнение: {addon or 'нет'}")
    print("=" * 64)
    n = 1
    index = {}
    for title, items in groups:
        print(f"\n  [{title}]")
        for pid, spec in items:
            print(f"  {n:3d}. {pid:<20} {spec['note']}")
            index[str(n)] = pid
            index[pid] = pid
            n += 1
    print()
    print("  Введите номер или название тарифа")
    print("  s  Переключить режим продления (требуется действующая подписка Google One)")
    print("  a  Выбрать дополнительный тариф YouTube")
    print("  e  Проверить и подготовить окружение")
    print("  g  Перезапустить Google One и загрузить скрипт повторно")
    print("  l  Показать тарифы ещё раз")
    print("  q  Выход")
    print()
    return index, rows


# ── хеши и проверка целостности ──────────────────────────────────────────────

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest().lower()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def is_elf_binary(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def remote_sha256(remote_path):
    """Возвращает SHA-256 файла на устройстве БЕЗ его запуска (или '')."""
    if not SAFE_REMOTE_PATH_RE.match(remote_path):
        raise ValueError(f"Небезопасный удалённый путь: {remote_path!r}")
    for args in (["sha256sum", "-b", remote_path], ["toybox", "sha256sum", "-b", remote_path]):
        out = adb.shell(*args)
        if "No such" in out or "not found" in out.lower() or "permission denied" in out.lower():
            continue
        m = SHA256_RE.search(out)
        if m:
            return m.group(1).lower()
    out = su_sh(f"sha256sum -b {remote_path}")
    if "No such" not in out:
        m = SHA256_RE.search(out)
        if m:
            return m.group(1).lower()
    return ""


# ── environment ──────────────────────────────────────────────────────────────

def host_frida_version():
    try:
        import frida
        return getattr(frida, "__version__", "") or ""
    except Exception:
        pass
    exe = shutil.which("frida")
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return ((r.stdout or r.stderr or "").strip().split() or [""])[0]
    except OSError:
        return ""


def ensure_host_frida():
    ver = host_frida_version()
    if ver:
        ok(f"Версия Frida на компьютере: {ver}")
        return ver
    warn("Frida не найдена на компьютере. Установка frida-tools через pip…")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "frida-tools"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        fail((r.stderr or r.stdout or "Ошибка pip").strip()[:400])
        sys.exit(1)
    ver = host_frida_version()
    if not ver:
        fail("Пакет frida-tools установлен, но команда frida недоступна. Проверьте PATH.")
        sys.exit(1)
    ok(f"Версия Frida на компьютере: {ver}")
    return ver


def device_abi():
    abi = adb.shell("getprop", "ro.product.cpu.abi") or ""
    return abi.splitlines()[0].strip() if abi else ""


def shell_is_root():
    return "uid=0" in adb.shell("id")


def has_root():
    if shell_is_root():
        return True
    out = adb.shell("su", "-c", "id")
    if "uid=0" in out:
        return True
    out = adb.shell("su", "0", "id")
    return "uid=0" in out


def google_accounts():
    out = adb.shell("dumpsys", "account")
    names = re.findall(r"Account \{name=([^,}]+),\s*type=com\.google", out or "")
    if names:
        return [n.strip() for n in names]
    names = re.findall(r"type=com\.google[^\n]*name=([^\s,\}]+)", out or "")
    return [n.strip() for n in names]


def su_sh(cmd):
    if shell_is_root():
        r = adb.run(["shell", "sh", "-c", cmd])
        return ((r.stdout or "") + (r.stderr or "")).strip()
    r = adb.run(["shell", "su", "-c", cmd])
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    bad = r.returncode != 0 or "inaccessible" in text or "not found" in text.lower()
    if bad:
        r = adb.run(["shell", "su", "0", "sh", "-c", cmd])
        text = ((r.stdout or "") + (r.stderr or "")).strip()
    return text


def remote_exists(path):
    out = adb.shell("ls", path)
    return "No such" not in out and path.split("/")[-1] in out


def ensure_module():
    """Гарантирует, что на устройстве лежит module_521.apk с эталонным SHA-256."""
    dev_hash = remote_sha256(DEX_REMOTE)
    if dev_hash == EXPECTED_MODULE_SHA256:
        ok(f"Модуль проверен по SHA-256: {DEX_REMOTE}")
        return
    if dev_hash:
        warn("SHA-256 module_521.apk на устройстве не совпал с эталоном — заменяю файл")
    else:
        info("Модуль module_521.apk отсутствует. Распаковка встроенного DEX и копирование на устройство…")
    try:
        from module_b64 import MODULE_B64
    except Exception as e:
        fail(f"Не удалось прочитать module_b64.py: {e}")
        sys.exit(1)
    raw = base64.b64decode(MODULE_B64)
    actual_local = sha256_bytes(raw)
    if actual_local != EXPECTED_MODULE_SHA256:
        fail(
            f"Нарушена целостность module_b64.py: SHA-256={actual_local}, "
            f"ожидался {EXPECTED_MODULE_SHA256}"
        )
        sys.exit(1)
    tmp = Path(tempfile.gettempdir()) / f"module_521_{os.getpid()}.apk"
    try:
        tmp.write_bytes(raw)
        r = adb.run(["push", str(tmp), DEX_REMOTE])
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if out:
            print(out, flush=True)
        if r.returncode != 0:
            fail(f"adb push для module_521.apk завершился с ошибкой (код {r.returncode})")
            sys.exit(1)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    adb.shell("chmod", "644", DEX_REMOTE)
    if remote_sha256(DEX_REMOTE) != EXPECTED_MODULE_SHA256:
        fail("Проверка SHA-256 module_521.apk на устройстве после копирования не прошла")
        sys.exit(1)
    ok("Модуль module_521.apk скопирован и проверен по SHA-256")


def _xz_to_file(xz_path, dest):
    data = lzma.open(xz_path).read()
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def fetch_github_asset_sha256(ver, asset_name):
    """Запрашивает официальный SHA-256 релиза Frida через GitHub Releases API."""
    pinned = KNOWN_FRIDA_XZ_SHA256.get((ver, asset_name.replace(f"frida-server-{ver}-", "").replace(".xz", "")))
    if pinned:
        return pinned
    url = f"https://api.github.com/repos/frida/frida/releases/tags/{ver}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "frida-verifier",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            release = json.loads(resp.read().decode("utf-8", "replace"))
        for asset in release.get("assets") or []:
            if asset.get("name") != asset_name:
                continue
            digest = str(asset.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                cand = digest.split(":", 1)[1].strip().lower()
                if len(cand) == 64:
                    return cand
    except Exception as e:
        warn(f"Не удалось получить SHA-256 релиза из GitHub API: {e}")
    return ""


def verify_local_frida_binary(path, ver, abi_tag):
    """Проверяет локальный распакованный frida-server (ELF + известный SHA-256)."""
    if not path or not path.is_file() or path.stat().st_size <= 1024 * 1024:
        return False
    if not is_elf_binary(path):
        warn(f"Файл {path} не является ELF-бинарником")
        return False
    pinned_bin = KNOWN_FRIDA_BIN_SHA256.get((ver, abi_tag))
    if pinned_bin and sha256_file(path) != pinned_bin:
        warn(f"SHA-256 локального {path.name} не совпал с эталоном для {ver}/{abi_tag}")
        return False
    return True


def local_frida_server(abi_tag, ver=""):
    """Ищет локальный frida-server в assets/ или ../bin/ (включая версионированные имена)."""
    cache = HERE / "assets"
    cache.mkdir(exist_ok=True)
    candidates = []
    if ver:
        candidates += [
            cache / f"frida-server-{ver}-{abi_tag}",
            BIN / f"frida-server-{ver}-{abi_tag}",
        ]
    else:
        candidates += sorted(cache.glob(f"frida-server-*-{abi_tag}"), reverse=True)
    candidates += [
        cache / f"frida-server-{abi_tag}",
        BIN / f"frida-server-{abi_tag}",
    ]
    if abi_tag == "android-x86_64":
        candidates.append(BIN / "frida-server")
    for p in candidates:
        if verify_local_frida_binary(p, ver, abi_tag):
            return p

    xz_candidates = []
    if ver:
        xz_candidates += [
            cache / f"frida-server-{ver}-{abi_tag}.xz",
            BIN / f"frida-server-{ver}-{abi_tag}.xz",
        ]
    else:
        xz_candidates += sorted(cache.glob(f"frida-server-*-{abi_tag}.xz"), reverse=True)
    xz_candidates += [
        cache / f"frida-server-{abi_tag}.xz",
        BIN / f"frida-server-{abi_tag}.xz",
    ]
    if abi_tag == "android-x86_64":
        xz_candidates.append(BIN / "frida-server-x86_64.xz")

    for xz in xz_candidates:
        if not xz.is_file():
            continue
        pinned_xz = KNOWN_FRIDA_XZ_SHA256.get((ver, abi_tag))
        if pinned_xz and sha256_file(xz) != pinned_xz:
            warn(f"SHA-256 архива {xz.name} не совпал с эталоном — пропускаю")
            continue
        dest_name = f"frida-server-{ver}-{abi_tag}" if ver else f"frida-server-{abi_tag}"
        unpacked = cache / dest_name
        info(f"Распаковка {xz.name}…")
        _xz_to_file(xz, unpacked)
        if verify_local_frida_binary(unpacked, ver, abi_tag):
            return unpacked
        unpacked.unlink(missing_ok=True)
    return None


def download_frida_server(ver, abi_tag):
    cache = HERE / "assets"
    cache.mkdir(exist_ok=True)
    name = f"frida-server-{ver}-{abi_tag}.xz"
    expected_xz_sha = KNOWN_FRIDA_XZ_SHA256.get((ver, abi_tag)) or fetch_github_asset_sha256(ver, name)
    if not expected_xz_sha:
        fail(
            f"Не удалось подтвердить эталонный SHA-256 для {name}. "
            "Автозагрузка непроверенного бинарника заблокирована."
        )
        return None
    url = f"https://github.com/frida/frida/releases/download/{ver}/{name}"
    xz = cache / name
    part = cache / (name + ".part")
    info(f"Загрузка {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "frida-verifier"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(part, "wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
        got_sha = sha256_file(part)
        if got_sha != expected_xz_sha:
            fail(f"SHA-256 скачанного {name} ({got_sha}) != ожидаемому ({expected_xz_sha})")
            part.unlink(missing_ok=True)
            return None
        part.replace(xz)
    except Exception as e:
        part.unlink(missing_ok=True)
        fail(f"Ошибка загрузки: {e}")
        return None
    dest = cache / f"frida-server-{ver}-{abi_tag}"
    _xz_to_file(xz, dest)
    if not verify_local_frida_binary(dest, ver, abi_tag):
        dest.unlink(missing_ok=True)
        return None
    return dest


def remote_frida_is_root():
    out = adb.shell("ps", "-A") or adb.shell("ps") or ""
    for line in out.splitlines():
        if "frida-server" in line:
            parts = line.split()
            if parts and parts[0] == "root":
                return True
    return False


def start_remote_frida():
    su_sh(f"chmod 755 {FRIDA_REMOTE}")
    su_sh("killall -9 frida-server")
    time.sleep(0.5)
    if shell_is_root():
        try:
            adb._cmd(
                ["shell", f"chmod 755 {FRIDA_REMOTE} && {FRIDA_REMOTE} -D </dev/null >/dev/null 2>&1 &"],
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1.5)
        return (adb.shell("pidof", "frida-server") or "").strip()

    try:
        adb._cmd(
            ["shell", "su", "-c", f"chmod 755 {FRIDA_REMOTE}; {FRIDA_REMOTE} -D </dev/null >/dev/null 2>&1 &"],
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pass
    time.sleep(1.5)
    running = (adb.shell("pidof", "frida-server") or "").strip()
    if not running:
        try:
            adb._cmd(
                ["shell", "su", "0", "sh", "-c", f"{FRIDA_REMOTE} -D </dev/null >/dev/null 2>&1 &"],
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1.5)
        running = (adb.shell("pidof", "frida-server") or "").strip()
    return running


def ensure_frida_server(ver):
    """Проверяет SHA-256 frida-server ДО любого исполнения (даже --version не запускается до сверки)."""
    abi = device_abi()
    abi_tag = ABI_ASSET.get(abi, "")
    if not abi_tag:
        fail(f"Неизвестная архитектура устройства: {abi!r}")
        sys.exit(1)
    info(f"Архитектура устройства: {abi} -> {abi_tag}")

    # 1. Сначала находим и верифицируем эталонный локальный бинарник для нужной версии.
    local = local_frida_server(abi_tag, ver=ver)
    if local is None:
        local = download_frida_server(ver, abi_tag)
    if local is None:
        fail(
            f"Не удалось подготовить проверенный frida-server {ver} ({abi_tag}). "
            "Запуск непроверенного файла на устройстве запрещён."
        )
        sys.exit(1)

    expected_sha = sha256_file(local)
    dev_sha = remote_sha256(FRIDA_REMOTE)
    running = (adb.shell("pidof", "frida-server") or "").strip()

    # 2. Только если SHA-256 на устройстве уже совпадает с проверенным локальным образом
    #    и процесс работает от root — переиспользуем его без перезаписи.
    if dev_sha == expected_sha and running and remote_frida_is_root():
        ok(f"frida-server {ver} проверен по SHA-256 и уже запущен от root, PID={running.split()[0]}")
        return

    if running:
        su_sh("killall -9 frida-server")
        time.sleep(0.5)

    if dev_sha != expected_sha:
        if dev_sha:
            warn("SHA-256 frida-server на устройстве отличается от эталона — заменяю бинарник")
        info(f"push {local.name} ({ver}) -> {FRIDA_REMOTE}")
        r = adb.run(["push", str(local), FRIDA_REMOTE])
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if out:
            print(out, flush=True)
        if r.returncode != 0:
            fail(f"Ошибка копирования frida-server (код {r.returncode}). Запуск с root отменён.")
            sys.exit(1)
        if remote_sha256(FRIDA_REMOTE) != expected_sha:
            fail("SHA-256 скопированного frida-server на устройстве не совпал с ожидаемым! Запуск отменён.")
            sys.exit(1)

    running = start_remote_frida()
    if not running:
        fail("Не удалось запустить проверенный frida-server. Устройству требуется root-доступ.")
        sys.exit(1)
    ok(f"frida-server {ver} проверен по SHA-256 и запущен, PID={running.split()[0]}")


def ensure_google_one():
    path = adb.shell("pm", "path", PKG)
    if "package:" in path:
        ok("Google One установлен")
        return
    fail("На устройстве отсутствует Google One (com.google.android.apps.subscriptions.red)")
    fail("Приложение Google One доступно в Google Play.")
    sys.exit(1)


def ensure_google_account():
    accts = google_accounts()
    if accts:
        ok("Аккаунты Google: " + ", ".join(accts))
        return accts
    fail("На устройстве не выполнен вход в аккаунт Google. Войдите через настройки Android или Google Play.")
    sys.exit(1)


def ensure_root():
    if has_root():
        ok("На устройстве доступен root")
        return
    info("Пробую включить root (adb root)…")
    r = adb.run(["root"])
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        info(f"adb root: {out}")
    time.sleep(1.5)
    if adb.serial and ":" in adb.serial and adb.serial not in adb.devices():
        adb.run(["connect", adb.serial], serial="")
        time.sleep(0.8)
    if has_root():
        ok("На устройстве доступен root (adb root)")
        return
    fail("На устройстве нет root-доступа: ни adb root, ни su не дали uid=0.")
    sys.exit(1)


def print_env(ver):
    accts = google_accounts()
    print()
    print("-" * 64)
    print("  Окружение")
    print("-" * 64)
    print(f"  Устройство    {adb.serial}")
    print(f"  ABI           {device_abi() or '?'}")
    print(f"  root          {'да' if has_root() else 'нет'}")
    print(f"  Аккаунты Google   {', '.join(accts) if accts else 'нет'}")
    print(f"  Frida на ПК    {ver or 'нет'}")
    print(f"  frida-server  {(adb.shell('pidof', 'frida-server') or 'остановлен').split()[0]}")
    print(f"  module_521    {'проверен' if remote_sha256(DEX_REMOTE) == EXPECTED_MODULE_SHA256 else 'нет'}")
    g1 = "есть" if "package:" in adb.shell("pm", "path", PKG) else "нет"
    print(f"  Google One    {g1}")
    print("-" * 64)


def ensure_env():
    adb.pick()
    ensure_root()
    ensure_google_account()
    ensure_google_one()
    ver = ensure_host_frida()
    ensure_module()
    ensure_frida_server(ver)
    print_env(ver)
    return ver


# ── резервный поиск токена подписки по всем g1.* со стороны ПК ───────────────

def _is_main_g1_sku(sku_or_doc):
    s = str(sku_or_doc or "")
    if "g1." not in s:
        return False
    for excl in ("_add_on", "youtube_premium", "home_premium", "health_premium"):
        if excl in s:
            return False
    return True


def read_play_db_token():
    """Резервное чтение токена действующей подписки g1.* через adb root (вне процесса Google One).

    Возвращает (token, sku) без вывода самого токена в журнал/консоль.
    """
    sql = (
        "select doc_id, inapp_purchase_data from ownership "
        "where doc_id like '%g1.%' "
        "and doc_id not like '%_add_on%' "
        "and doc_id not like '%youtube_premium%' "
        "and doc_id not like '%home_premium%' "
        "and doc_id not like '%health_premium%' "
        "order by subs_valid_until_time desc limit 10;"
    )
    cmd = f"sqlite3 -separator $'\\t' {PLAY_DB_REMOTE} \"{sql}\""
    out = su_sh(cmd)
    if not out or "not found" in out.lower() or "no such table" in out.lower():
        return "", ""
    for line in out.splitlines():
        line = line.strip()
        if not line or "purchaseToken" not in line:
            continue
        doc_id, _, raw_json = line.partition("\t")
        if not raw_json:
            raw_json = line
        try:
            start = raw_json.find("{")
            end = raw_json.rfind("}")
            if start < 0 or end <= start:
                continue
            data = json.loads(raw_json[start : end + 1])
        except Exception:
            continue
        tok = str(data.get("purchaseToken") or "")
        prod = str(data.get("productId") or doc_id or "")
        if tok and _is_main_g1_sku(prod):
            ok(f"Резервный поиск: найдена подписка {prod}")
            return tok, prod
    info("Резервный поиск: подходящих основных подписок g1.* не найдено")
    return "", ""


# ── Google One + Frida session ───────────────────────────────────────────────

def g1_pid():
    return (adb.shell("pidof", PKG) or "").split()[:1]


def wake():
    adb.shell("input", "keyevent", "224")
    adb.shell("wm", "dismiss-keyguard")


def start_google_one():
    wake()
    adb.shell("am", "force-stop", PKG)
    time.sleep(1.2)
    adb.shell("am", "start", "-n", ACT)
    adb.shell("monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    pid = ""
    for _ in range(40):
        time.sleep(0.35)
        got = g1_pid()
        if got:
            pid = got[0]
            break
    if not pid:
        fail("Не удалось запустить Google One")
        sys.exit(1)
    time.sleep(2.5)
    pid = (g1_pid() or [pid])[0]
    ok(f"Google One pid={pid}")
    return int(pid)


def post_frida_bridge(script, name):
    """В Frida 17 мост Java поставляется отдельно. Для Java.perform скрипт запрашивает его исходный код."""
    try:
        import frida_tools
        root = Path(frida_tools.__file__).resolve().parent / "bridges"
    except Exception as e:
        fail(f"Не найден каталог frida_tools/bridges: {e}")
        return False
    stem = (name or "java").lower()
    for p in root.glob("*.js"):
        if p.stem.lower() == stem:
            script.post({
                "type": "frida:bridge-loaded",
                "filename": p.name,
                "source": p.read_text(encoding="utf-8"),
            })
            return True
    fail(f"Не найден мост Frida с именем {stem}")
    return False


class Session:
    def __init__(self):
        self.device = None
        self.session = None
        self.script = None
        self.ready = threading.Event()
        self.last_ev = ""
        self.lock = threading.Lock()

    def _supply_db_token(self):
        tok, sku = read_play_db_token()
        if self.script:
            try:
                self.script.post({"type": "db_token", "payload": {"token": tok, "sku": sku}})
            except Exception as e:
                warn(f"Не удалось передать резервный результат в скрипт: {e}")

    def _on_message(self, message, _data):
        if message.get("type") == "error":
            fail(message.get("stack") or message.get("description") or str(message))
            return
        if message.get("type") != "send":
            return
        payload = message.get("payload") or {}
        if isinstance(payload, dict) and payload.get("type") == "frida:load-bridge":
            info(f"Загрузка моста Frida: {payload.get('name')}")
            post_frida_bridge(self.script, payload.get("name") or "java")
            return
        if not isinstance(payload, dict):
            print(payload, flush=True)
            return
        ev = payload.get("ev") or ""
        with self.lock:
            self.last_ev = ev
        if ev == "need_db_token":
            threading.Thread(target=self._supply_db_token, daemon=True).start()
            return
        bits = [ev] if ev else []
        for k, v in payload.items():
            if k in ("ev", "token", "old", "head") or v in ("", None):
                continue
            bits.append(f"{k}={v}")
        print("[g1] " + "  ".join(str(x) for x in bits), flush=True)
        if ev == "ready":
            self.ready.set()
        if ev == "launched":
            code = str(payload.get("code", ""))
            if code == "0":
                ok("Экран оформления открыт. Для подписки требуется подтверждение на устройстве.")
            else:
                warn(f"Код ответа launchBillingFlow: {code} {payload.get('msg', '')}")

    def attach(self, pid):
        import frida
        self.ready.clear()
        mgr = frida.get_device_manager()
        dev = None
        for _ in range(6):
            for d in mgr.enumerate_devices():
                if d.id == adb.serial:
                    dev = d
                    break
            if dev is not None:
                break
            time.sleep(0.5)
        if dev is None:
            fail(
                f"Frida не обнаружила выбранное устройство {adb.serial!r}. "
                "Резервное переключение на случайное USB-устройство отключено."
            )
            sys.exit(1)
        self.device = dev
        info(f"attach pid={pid}")
        self.session = dev.attach(pid)
        js = JS_PATH.read_text(encoding="utf-8")
        try:
            import frida_tools
            java_js = Path(frida_tools.__file__).resolve().parent / "bridges" / "java.js"
            if java_js.is_file():
                js = java_js.read_text(encoding="utf-8") + "\n;var Java = bridge;\n" + js
                info("Встроен frida-java-bridge")
        except Exception as e:
            warn(f"Не удалось встроить мост Java: {e}")
        self.script = self.session.create_script(js)
        self.script.on("message", self._on_message)
        self.script.load()
        if not self.ready.wait(timeout=20):
            warn("BillingClient не сообщил о готовности за 20 секунд. Оформление всё ещё доступно.")
        else:
            ok("BillingClient готов")

    def _exports(self):
        sc = self.script
        if hasattr(sc, "exports_sync"):
            return sc.exports_sync
        return sc.exports

    def buy(self, plan_id, stack=False, addon=""):
        exp = self._exports()

        def rpc(names, arg=None, required=True):
            last = None
            for n in names:
                fn = getattr(exp, n, None)
                if not callable(fn):
                    continue
                try:
                    return fn() if arg is None else fn(arg)
                except Exception as e:
                    last = e
            if required:
                raise last or AttributeError(names[0])
            return None

        try:
            rpc(("set_addon", "setAddon"), addon or "", required=False)
            ret = rpc(("stack",) if stack else ("buy",), plan_id)
            info(ret)
        except Exception as e:
            warn(f"Ошибка вызова RPC, переход на post: {e}")
            self.script.post({
                "type": "cfg",
                "payload": {"target": plan_id, "stack": stack, "addon": addon},
            })

    def close(self):
        try:
            if self.script:
                self.script.unload()
        except Exception:
            pass
        try:
            if self.session:
                self.session.detach()
        except Exception:
            pass
        self.script = None
        self.session = None


def pick_addon(plans):
    yt = [pid for pid in ("yt_1m", "yt_family", "yt_lite") if pid in plans]
    print("Дополнительный тариф будет отправлен вместе с основным:")
    print("  0. нет")
    for i, pid in enumerate(yt, 1):
        print(f"  {i}. {pid}  {plans[pid]['note']}")
    raw = input("Выбор: ").strip() or "0"
    if raw in ("0", "n", "none", ""):
        return ""
    if raw in plans:
        return raw
    try:
        return yt[int(raw) - 1]
    except Exception:
        return ""


def parse_args():
    p = argparse.ArgumentParser(description="Тарифы Google One")
    p.add_argument("-s", "--serial", default=os.environ.get("ANDROID_SERIAL") or "")
    p.add_argument("--plan", default="", help="Название или номер тарифа для оформления без меню")
    p.add_argument("--stack", "--renew", action="store_true",
                   help="Режим продления действующей подписки Google One (STACK=true в frida.js)")
    p.add_argument("--addon", default="", help="Идентификатор дополнительного тарифа, например yt_1m")
    p.add_argument("--wait", type=float, default=8.0, help="Время ожидания после запроса в секундах")
    return p.parse_args()


def resolve_plan(raw, plans, index=None):
    if not raw:
        return ""
    if raw in plans:
        return raw
    if index and raw in index:
        return index[raw]
    return ""


def main():
    _fix_stdio()
    args = parse_args()
    if args.serial:
        adb.serial = args.serial
        adb.explicit = True
        os.environ["ANDROID_SERIAL"] = args.serial

    if not JS_PATH.is_file():
        fail(f"Файл не найден: {JS_PATH}")
        sys.exit(1)
    plans = parse_plans(JS_PATH.read_text(encoding="utf-8"))
    if not plans:
        fail("Не удалось прочитать PLANS из frida.js")
        sys.exit(1)

    ensure_env()
    sess = Session()
    pid = start_google_one()
    sess.attach(pid)

    stack = bool(args.stack)
    addon = args.addon
    groups = grouped_plans(plans)
    index = {str(i): pid for i, (_t, pid, _s) in enumerate(flatten_menu(groups), 1)}
    index.update({pid: pid for pid in plans})

    if args.plan:
        plan_id = resolve_plan(args.plan, plans, index)
        if not plan_id:
            fail(f"Неизвестный тариф {args.plan!r}")
            sess.close()
            sys.exit(1)
        spec = plans[plan_id]
        info(f"{'Продление' if stack else 'Новая подписка'} {plan_id}  sku={spec['sku']}  offer={spec['offer']}")
        info(spec["note"])
        sess.buy(plan_id, stack=stack, addon=addon)
        time.sleep(max(args.wait, 1.0))
        sess.close()
        return

    try:
        while True:
            index, _rows = print_menu(plans, stack, addon)
            try:
                raw = input("> ").strip()
            except EOFError:
                break
            if not raw:
                continue
            low = raw.lower()
            if low in ("q", "quit", "exit"):
                break
            if low == "l":
                continue
            if low == "s":
                stack = not stack
                ok("Продление действующей подписки включено" if stack else "Продление выключено (новая подписка)")
                continue
            if low == "a":
                addon = pick_addon(plans)
                ok(f"Дополнительный тариф: {addon or 'нет'}")
                continue
            if low == "e":
                ensure_env()
                continue
            if low == "g":
                sess.close()
                pid = start_google_one()
                sess.attach(pid)
                continue
            plan_id = index.get(raw) or index.get(low)
            if not plan_id:
                warn("Команда не распознана. Введите номер, название тарифа или q для выхода.")
                continue
            spec = plans[plan_id]
            info(f"{'Продление' if stack else 'Новая подписка'} {plan_id}  sku={spec['sku']}  offer={spec['offer']}")
            info(spec["note"])
            sess.buy(plan_id, stack=stack, addon=addon)
            time.sleep(1.2)
    except KeyboardInterrupt:
        print()
        warn("Прервано")
    finally:
        sess.close()
        info("Работа завершена")


if __name__ == "__main__":
    main()
