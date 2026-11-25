#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vm_watch.py — сторож KVM-машин на debian-nested (libvirt).

Что делает:
  1. Спрашивает у libvirt (virsh -c qemu:///system), какие VM есть,
     какие запущены, какие у них внутренние IP (domifaddr + DHCP-аренды
     dnsmasq) и VNC/SPICE-порты (vncdisplay / dumpxml).
  2. Сравнивает с прошлым снимком в state-файле (по умолчанию
     state/vm_state.json рядом со скриптом).
  3. Если ничего не изменилось — ничего не делает и НЕ шлёт в Telegram.
  4. Если изменилось (VM включилась/выключилась, IP переназначился,
     VNC-порт поменялся, внешний IP хоста сменился) — присылает в
     Telegram одно сообщение с текущим состоянием всех машин и списком
     изменений, и записывает новый снимок в state-файл.

VNC-пароль: virsh его НЕ отдаёт (в XML его нет — пароль задаётся
через QMP и только записывается, не читается). Если пароль нужен
в сообщении, задайте VNC_PASSWORD в config.py.

Только стандартная библиотека. Для запуска по cron на debian-nested
(раз в 5 минут). Работает от пользователя avkuska (в группе libvirt,
подключение к системному libvirt: virsh -c qemu:///system).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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

# DHCP-аренды libvirt (читается всеми, root:root 644).
DNSMASQ_STATUS = "/var/lib/libvirt/dnsmasq/virbr0.status"

DEFAULT_CONFIG = {
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    # VNC-пароль для сообщения (virsh его не отдаёт). Необязательно.
    "VNC_PASSWORD": "",
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


def get_external_ip():
    """Возвращает внешний IP хоста или '' если узнать не удалось."""
    try:
        ip = fetch_text(
            GCP_METADATA_URL, headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        if ip:
            return ip
    except Exception:
        pass
    for url in (IPIFY_URL, IFCONFIG_URL):
        try:
            ip = fetch_text(url, timeout=10)
            if ip and all(c.isdigit() or c == "." for c in ip):
                return ip
        except Exception:
            pass
    return ""


# ── virsh ────────────────────────────────────────────────────────────────────

def virsh(*args):
    """Запускает virsh -c qemu:///system. Возвращает (rc, stdout, stderr)."""
    cmd = ["virsh", "-c", "qemu:///system", *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)


def list_vms():
    """Возвращает {имя: состояние} из `virsh list --all`."""
    rc, out, err = virsh("list", "--all")
    vms = {}
    if rc != 0:
        warn(f"virsh list не сработал: {err.strip() or out.strip()}")
        return vms
    for line in out.splitlines():
        # " 1    win11           running" / " -    bliss-02        shut off"
        m = re.match(r"^\s*(\S+)\s+(\S+)\s+(.+?)\s*$", line)
        if not m:
            continue
        if m.group(1) in ("Id", "---", "--"):
            continue
        if m.group(2) == "Name":
            continue
        vms[m.group(2)] = m.group(3).strip()
    return vms


def vm_mac(name):
    """MAC-адрес первого интерфейса VM из dumpxml (или '')."""
    rc, out, _ = virsh("dumpxml", name)
    if rc != 0:
        return ""
    m = re.search(r"<mac address='([0-9a-fA-F:]+)'", out)
    return m.group(1).lower() if m else ""


def dnsmasq_leases():
    """DHCP-аренды из virbr0.status: {mac: ip}."""
    leases = {}
    try:
        data = json.loads(Path(DNSMASQ_STATUS).read_text(encoding="utf-8"))
        for entry in data:
            mac = (entry.get("mac-address") or "").lower()
            ip = entry.get("ip-address") or ""
            if mac and ip:
                leases[mac] = ip
    except Exception as e:
        warn(f"Не удалось прочитать {DNSMASQ_STATUS}: {e}")
    return leases


def vm_ips(name, leases):
    """Внутренние IPv4 VM: сначала domifaddr, потом DHCP-аренды по MAC."""
    ips = []
    rc, out, _ = virsh("domifaddr", name)
    if rc == 0:
        for line in out.splitlines():
            # " vnet1  52:54:00:14:c5:d8  ipv4  10.166.0.128/24"
            m = re.search(r"\bipv4\s+(\d+\.\d+\.\d+\.\d+)(?:/\d+)?\b", line)
            if m and m.group(1) not in ips:
                ips.append(m.group(1))
    if not ips:
        mac = vm_mac(name)
        if mac and mac in leases:
            ips.append(leases[mac])
    return ips


def vm_graphics(name, running):
    """Графика VM: {'type': 'vnc'/'spice'/None, 'port': int/None}.

    У запущенной VM реальный VNC-порт берём из vncdisplay (:N = 5900+N),
    у выключенной — из dumpxml (port='-1' = autoport, порт назначится при старте).
    """
    if running:
        rc, out, _ = virsh("vncdisplay", name)
        if rc == 0:
            m = re.search(r":(\d+)", out.strip())
            if m:
                return {"type": "vnc", "port": 5900 + int(m.group(1))}
    rc, out, _ = virsh("dumpxml", name)
    if rc != 0:
        return {"type": None, "port": None}
    m = re.search(r"<graphics type='(vnc|spice)' port='(-?\d+)'", out)
    if not m:
        return {"type": None, "port": None}
    port = int(m.group(2))
    return {"type": m.group(1), "port": port if port >= 0 else None}


# ── снимок состояния ─────────────────────────────────────────────────────────

def take_snapshot():
    snap = {"external_ip": get_external_ip(), "vms": {}}
    leases = dnsmasq_leases()
    vms = list_vms()
    for name, state in sorted(vms.items()):
        running = state == "running"
        snap["vms"][name] = {
            "state": state,
            "ips": vm_ips(name, leases) if running else [],
            "graphics": vm_graphics(name, running),
        }
    return snap


def read_snapshot(state_file):
    try:
        return json.loads(Path(state_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        warn(f"Не удалось прочитать state-файл {state_file}: {e}")
        return None


def write_snapshot(state_file, snap):
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def diff_snapshots(old, new):
    """Список человекочитаемых изменений между снимками."""
    changes = []
    if old is None:
        return ["начальный снимок"]
    if old.get("external_ip") != new.get("external_ip"):
        changes.append(
            f"Внешний IP: {old.get('external_ip') or '—'} → {new.get('external_ip') or '—'}"
        )
    old_vms = old.get("vms") or {}
    new_vms = new.get("vms") or {}
    for name in sorted(set(old_vms) | set(new_vms)):
        o = old_vms.get(name)
        n = new_vms.get(name)
        if o is None:
            changes.append(f"{name}: появилась в libvirt ({n['state']})")
            continue
        if n is None:
            changes.append(f"{name}: пропала из libvirt (была {o['state']})")
            continue
        if o.get("state") != n.get("state"):
            changes.append(f"{name}: {o.get('state')} → {n.get('state')}")
        if o.get("ips") != n.get("ips"):
            o_ips = ", ".join(o.get("ips") or []) or "—"
            n_ips = ", ".join(n.get("ips") or []) or "—"
            changes.append(f"{name} IP: {o_ips} → {n_ips}")
        og = o.get("graphics") or {}
        ng = n.get("graphics") or {}
        if (og.get("type"), og.get("port")) != (ng.get("type"), ng.get("port")):
            changes.append(
                f"{name} графика: {fmt_graphics(og)} → {fmt_graphics(ng)}"
            )
    return changes


def fmt_graphics(g):
    t = (g or {}).get("type")
    port = (g or {}).get("port")
    if not t:
        return "—"
    if port is None:
        return f"{t} (порт назначится при старте)"
    return f"{t} {port}"


def format_message(snap, changes, first_run, vnc_password):
    lines = []
    lines.append(
        "KVM debian-nested — начальное состояние"
        if first_run
        else "KVM debian-nested — состояние изменилось"
    )
    lines.append("")
    for name, vm in sorted(snap["vms"].items()):
        if vm["state"] != "running":
            lines.append(f"• {name}: {vm['state']}")
            continue
        ips = ", ".join(vm["ips"]) if vm["ips"] else "IP не виден"
        lines.append(f"• {name}: running, {ips}, {fmt_graphics(vm['graphics'])}")
    lines.append("")
    lines.append(f"Внешний IP: {snap['external_ip'] or 'неизвестен'}")
    if vnc_password:
        lines.append(f"VNC пароль: {vnc_password}")
    else:
        lines.append("VNC пароль: virsh не отдаёт (VNC_PASSWORD в config.py)")
    if changes:
        lines.append("")
        lines.append("Изменения:")
        for c in changes:
            lines.append(f"• {c}")
    return "\n".join(lines)


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
        description="Сторож KVM-машин: Telegram только при изменении состояния."
    )
    p.add_argument("--state-file", default="", help="Путь к state-файлу (по умолчанию state/vm_state.json)")
    p.add_argument("--force", action="store_true", help="Отправить сообщение, даже если ничего не изменилось")
    p.add_argument("--dry-run", action="store_true", help="Только показать, что было бы сделано, без Telegram и без записи state")
    p.add_argument("--inventory", action="store_true", help="Напечатать снимок состояния как JSON и выйти (без Telegram и без записи state). Для tunnel.py.")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("TELEGRAM_BOT_TOKEN") or ""
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("TELEGRAM_CHAT_ID") or ""
    vnc_password = os.environ.get("VNC_PASSWORD") or cfg.get("VNC_PASSWORD") or ""

    state_file = args.state_file or str(HERE / "state" / "vm_state.json")

    snap = take_snapshot()

    if args.inventory:
        print(json.dumps(snap, sort_keys=True))
        return 0
    parts = [f"{n}={v['state']}" for n, v in sorted(snap["vms"].items())]
    info(f"VM: {', '.join(parts) or 'нет'}")
    if snap["external_ip"]:
        info(f"Внешний IP: {snap['external_ip']}")

    old = read_snapshot(state_file)
    first_run = old is None
    changes = diff_snapshots(old, snap)

    if not changes and not args.force:
        print("Без изменений, Telegram не трогаем")
        return 0
    if not changes and args.force:
        info("--force: отправляю сообщение, хотя ничего не изменилось")

    if args.dry_run:
        print("[dry-run] Сообщение было бы таким:")
        print(format_message(snap, changes, first_run, vnc_password))
        print("[dry-run] Telegram не вызывался, state-файл не менялся")
        return 0

    if not tg_token or not tg_chat:
        warn("Telegram не настроен (нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — сообщение не отправлено")
        write_snapshot(state_file, snap)
        ok(f"Снимок записан в state-файл: {state_file}")
        return 0

    text = format_message(snap, changes, first_run, vnc_password)
    if tg_notify(tg_token, tg_chat, text):
        ok("Telegram: уведомление отправлено")
    else:
        warn("Telegram: уведомление НЕ отправлено (снимок всё равно записан)")
    write_snapshot(state_file, snap)
    ok(f"Снимок записан в state-файл: {state_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
