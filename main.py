# -*- coding: utf-8 -*-
"""
Тарифы Google One

  python main.py

Обнаруживает ADB, подключается к эмулятору или телефону и копирует недостающие компоненты.
Требуются root-доступ, вход в аккаунт Google и приложение Google One на устройстве.
После выбора тарифа открывается экран оформления. Подписку подтверждает пользователь.

Режим продления в меню соответствует STACK=true в frida.js.
В этом режиме используется действующая подписка Google One.
"""
from __future__ import annotations

import argparse
import glob
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
        "ultra20_3m_90", "ultra20_3m_80", "ultra20_3m_75",
    ]),
    ("Ultra 20x", [
        "ultra_1m_90", "ultra_3m_90", "ultra_3m_80", "ultra_1m_75", "ultra_3m_75",
    ]),
]


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
    def __init__(self, serial=""):
        self.exe = find_adb_exe()
        self.serial = serial or os.environ.get("ANDROID_SERIAL") or ""

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

    def run(self, args, serial=None):
        return self._cmd(args, serial=serial)

    def shell(self, *parts):
        r = self._cmd(["shell", *parts])
        return ((r.stdout or "") + (r.stderr or "")).strip()

    def devices(self):
        rows = []
        out = self._cmd(["devices"], serial="").stdout
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
            if "uid=0" in (self.shell("su", "-c", "id") + self.shell("su", "0", "id")):
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
        rows = self.discover()
        if self.serial and self.serial in rows:
            ok(f"Устройство: {self.serial}")
            return self.serial
        if self.serial and self.serial not in rows:
            warn(f"Устройство {self.serial} недоступно. Включён автоматический выбор")
        if len(rows) == 1:
            self.serial = rows[0]
        else:
            ranked = sorted(rows, key=self._score, reverse=True)
            self.serial = ranked[0]
            info("Найдено несколько устройств. Выбрано устройство с наибольшей оценкой:")
            for s in ranked:
                info(f"  {s}  score={self._score(s)}")
        os.environ["ANDROID_SERIAL"] = self.serial
        ok(f"Устройство: {self.serial}")
        return self.serial


adb = Adb()


def parse_plans(js_text):
    """Parse PLANS from frida.js so the menu stays in sync with the hook."""
    block = re.search(r"var PLANS = \{([\s\S]*?)\n\};", js_text)
    if not block:
        return {}
    plans = {}
    for m in re.finditer(
        r"(\w+)\s*:\s*\{\s*sku:\s*\"([^\"]+)\"\s*,\s*offer:\s*\"([^\"]+)\"\s*,\s*note:\s*\"([^\"]*)\"",
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
            print(f"  {n:2d}. {pid:<16} {spec['note']}")
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
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or r.stderr or "").strip().split()[0]


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


def has_root():
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
    if remote_exists(DEX_REMOTE):
        ok(f"Модуль уже есть на устройстве: {DEX_REMOTE}")
        return
    info("Модуль module_521.apk отсутствует. Распаковка встроенного DEX и копирование на устройство…")
    try:
        from module_b64 import MODULE_B64
    except Exception as e:
        fail(f"Не удалось прочитать module_b64.py: {e}")
        sys.exit(1)
    import base64
    tmp = Path(tempfile.gettempdir()) / "module_521.apk"
    tmp.write_bytes(base64.b64decode(MODULE_B64))
    r = adb.run(["push", str(tmp), DEX_REMOTE])
    print((r.stdout or r.stderr or "").strip(), flush=True)
    adb.shell("chmod", "644", DEX_REMOTE)
    if not remote_exists(DEX_REMOTE):
        fail("Не удалось скопировать module_521.apk на устройство")
        sys.exit(1)
    ok("Модуль module_521.apk скопирован")


def _xz_to_file(xz_path, dest):
    data = lzma.open(xz_path).read()
    dest.write_bytes(data)
    return dest


def local_frida_server(abi_tag):
    """Find a host-side frida-server binary matching the device ABI."""
    named = [
        HERE / "assets" / f"frida-server-{abi_tag}",
        BIN / f"frida-server-{abi_tag}",
    ]
    for p in named:
        if p.is_file() and p.stat().st_size > 1024 * 1024:
            return p
    generic = BIN / "frida-server"
    if abi_tag == "android-x86_64" and generic.is_file() and generic.stat().st_size > 1024 * 1024:
        return generic
    cache = HERE / "assets"
    cache.mkdir(exist_ok=True)
    unpacked = cache / f"frida-server-{abi_tag}"
    if unpacked.is_file() and unpacked.stat().st_size > 1024 * 1024:
        return unpacked
    xz_candidates = [
        HERE / "assets" / f"frida-server-{abi_tag}.xz",
        BIN / f"frida-server-{abi_tag}.xz",
    ]
    if abi_tag == "android-x86_64":
        xz_candidates.append(BIN / "frida-server-x86_64.xz")
    for xz in xz_candidates:
        if not xz.is_file():
            continue
        info(f"Распаковка {xz.name}…")
        return _xz_to_file(xz, unpacked)
    return None


def download_frida_server(ver, abi_tag):
    cache = HERE / "assets"
    cache.mkdir(exist_ok=True)
    name = f"frida-server-{ver}-{abi_tag}.xz"
    url = f"https://github.com/frida/frida/releases/download/{ver}/{name}"
    xz = cache / name
    info(f"Загрузка {url}")
    try:
        urllib.request.urlretrieve(url, xz)
    except Exception as e:
        fail(f"Ошибка загрузки: {e}")
        return None
    dest = cache / f"frida-server-{ver}-{abi_tag}"
    return _xz_to_file(xz, dest)


def remote_frida_version():
    if not remote_exists(FRIDA_REMOTE):
        return ""
    out = adb.shell(FRIDA_REMOTE, "--version") or su_sh(f"{FRIDA_REMOTE} --version")
    m = re.search(r"(\d+\.\d+\.\d+)", out or "")
    return m.group(1) if m else ""


def start_remote_frida():
    su_sh(f"chmod 755 {FRIDA_REMOTE}")
    adb.run(["shell", "su", "-c", "killall -9 frida-server"])
    time.sleep(0.5)
    adb.run(["shell", "su", "-c", f"chmod 755 {FRIDA_REMOTE}; {FRIDA_REMOTE} -D &"])
    time.sleep(1.5)
    running = (adb.shell("pidof", "frida-server") or "").strip()
    if not running:
        adb.run(["shell", "su", "0", "sh", "-c", f"{FRIDA_REMOTE} -D &"])
        time.sleep(1.5)
        running = (adb.shell("pidof", "frida-server") or "").strip()
    return running


def ensure_frida_server(ver):
    abi = device_abi()
    abi_tag = ABI_ASSET.get(abi, "")
    if not abi_tag:
        fail(f"Неизвестная архитектура устройства: {abi!r}")
        sys.exit(1)
    info(f"Архитектура устройства: {abi} -> {abi_tag}")

    remote_ver = remote_frida_version()
    running = (adb.shell("pidof", "frida-server") or "").strip()
    if running and remote_ver == ver:
        ok(f"frida-server {remote_ver} уже запущен, PID={running.split()[0]}")
        return

    if remote_ver and remote_ver != ver:
        warn(f"Версия сервера на устройстве ({remote_ver}) отличается от локальной ({ver}). Сервер будет заменён")

    local = None
    cache = HERE / "assets" / f"frida-server-{ver}-{abi_tag}"
    if cache.is_file() and cache.stat().st_size > 1024 * 1024:
        local = cache
    if local is None:
        local = download_frida_server(ver, abi_tag)
    if local is None:
        local = local_frida_server(abi_tag)
    if local is None:
        fail("Не удалось подготовить frida-server. Ожидался файл для архитектуры устройства в assets/ или ../bin/")
        sys.exit(1)

    if running:
        adb.run(["shell", "su", "-c", "killall -9 frida-server"])
        time.sleep(0.5)

    info(f"push {local.name} ({ver}) -> {FRIDA_REMOTE}")
    r = adb.run(["push", str(local), FRIDA_REMOTE])
    print((r.stdout or r.stderr or "").strip(), flush=True)

    running = start_remote_frida()
    if not running:
        fail("Не удалось запустить frida-server. Устройству требуется root-доступ.")
        sys.exit(1)
    ok(f"frida-server {ver} запущен, PID={running.split()[0]}")


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
    fail("На устройстве нет root-доступа: проверка su не прошла.")
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
    print(f"  module_521    {'есть' if remote_exists(DEX_REMOTE) else 'нет'}")
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
        bits = [ev] if ev else []
        for k, v in payload.items():
            if k == "ev" or v in ("", None):
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
        for d in mgr.enumerate_devices():
            if d.id == adb.serial:
                dev = d
                break
        if dev is None:
            dev = frida.get_usb_device(timeout=8)
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
