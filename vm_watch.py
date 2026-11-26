#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vm_watch.py — сторож KVM-машин на KVM-хосте (libvirt).

Что делает:
  1. Спрашивает у libvirt (virsh -c qemu:///system), какие VM есть,
     какие запущены, какие у них внутренние IP (domifaddr + DHCP-аренды
     dnsmasq) и VNC/SPICE-порты (vncdisplay / dumpxml).
  2. Отдельно хранит в state-файле (по умолчанию state/vm_state.json):
     - last_polled: последний успешный снимок libvirt;
     - last_notified: последний снимок, успешно доставленный в Telegram;
     - port_slots: постоянные индексы портов за именами VM (для tunnel.py).
  3. При ошибке `virsh list` НЕ затирает state-файл и возвращает код 1.
  4. При сбое Telegram сохраняет last_polled/port_slots, но НЕ обновляет
     last_notified — повторная отправка произойдёт на следующем цикле.
  5. Пароли VNC никогда не читаются, не хранятся и не включаются в сообщения.

Только стандартная библиотека. Для запуска по cron (раз в 5 минут).
"""

from __future__ import annotations

import argparse
import ipaddress
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

def is_valid_ipv4(value):
    try:
        ipaddress.IPv4Address((value or "").strip())
        return True
    except ValueError:
        return False


def fetch_text(url, headers=None, timeout=5):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace").strip()


def get_external_ip():
    """Возвращает внешний IPv4 хоста или '' если узнать не удалось."""
    try:
        ip = fetch_text(
            GCP_METADATA_URL, headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        if is_valid_ipv4(ip):
            return ip
    except Exception:
        pass
    for url in (IPIFY_URL, IFCONFIG_URL):
        try:
            ip = fetch_text(url, timeout=10)
            if is_valid_ipv4(ip):
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
    """Возвращает {имя: состояние} из `virsh list --all` или None при ошибке."""
    rc, out, err = virsh("list", "--all")
    if rc != 0:
        warn(f"virsh list не сработал: {(err or out or '').strip()}")
        return None
    vms = {}
    for line in (out or "").splitlines():
        m = re.match(r"^\s*(\S+)\s+(\S+)\s+(.+?)\s*$", line)
        if not m:
            continue
        if m.group(1) in ("Id", "---", "--"):
            continue
        if m.group(2) == "Name":
            continue
        vms[m.group(2)] = m.group(3).strip()
    return vms


def get_dumpxml(name, xml_cache=None):
    if xml_cache is not None and name in xml_cache:
        return xml_cache[name]
    rc, out, _ = virsh("dumpxml", name)
    xml = out if rc == 0 else ""
    if xml_cache is not None:
        xml_cache[name] = xml
    return xml


def vm_mac(name, xml_cache=None):
    """MAC-адрес первого интерфейса VM из dumpxml (или '')."""
    out = get_dumpxml(name, xml_cache)
    if not out:
        return ""
    m = re.search(r"<mac address='([0-9a-fA-F:]+)'", out)
    return m.group(1).lower() if m else ""


def dnsmasq_leases():
    """DHCP-аренды из virbr0.status: {mac: ip}."""
    leases = {}
    p = Path(DNSMASQ_STATUS)
    if not p.exists():
        return leases
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for entry in data:
            mac = (entry.get("mac-address") or "").lower()
            ip = entry.get("ip-address") or ""
            if mac and is_valid_ipv4(ip):
                leases[mac] = ip
    except Exception as e:
        warn(f"Не удалось прочитать {DNSMASQ_STATUS}: {e}")
    return leases


def vm_ips(name, leases, xml_cache=None):
    """Внутренние IPv4 VM: сначала domifaddr, потом DHCP-аренды по MAC."""
    ips = []
    rc, out, _ = virsh("domifaddr", name)
    if rc == 0:
        for line in (out or "").splitlines():
            m = re.search(r"\bipv4\s+(\d+\.\d+\.\d+\.\d+)(?:/\d+)?\b", line)
            if m and is_valid_ipv4(m.group(1)) and m.group(1) not in ips:
                ips.append(m.group(1))
    if not ips:
        mac = vm_mac(name, xml_cache)
        if mac and mac in leases:
            ips.append(leases[mac])
    return ips


def vm_graphics(name, running, xml_cache=None):
    """Графика VM: {'type': 'vnc'/'spice'/None, 'port': int/None}."""
    if running:
        rc, out, _ = virsh("vncdisplay", name)
        if rc == 0:
            m = re.search(r":(\d+)", (out or "").strip())
            if m:
                return {"type": "vnc", "port": 5900 + int(m.group(1))}
    out = get_dumpxml(name, xml_cache)
    if not out:
        return {"type": None, "port": None}
    m = re.search(r"<graphics type='(vnc|spice)' port='(-?\d+)'", out)
    if not m:
        return {"type": None, "port": None}
    port = int(m.group(2))
    return {"type": m.group(1), "port": port if port >= 0 else None}


def assign_port_slots(vms, existing_slots=None):
    """Закрепляет постоянные индексы портов за именами VM."""
    slots = {}
    for k, v in (existing_slots or {}).items():
        if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            slots[k] = v
    next_idx = (max(slots.values()) + 1) if slots else 0
    for name in sorted(vms or {}):
        if name not in slots:
            slots[name] = next_idx
            next_idx += 1
    return slots


# ── снимок состояния ─────────────────────────────────────────────────────────

def take_snapshot(existing_slots=None):
    """Собирает снимок состояния VM или возвращает None при сбое libvirt."""
    vms = list_vms()
    if vms is None:
        return None
    leases = dnsmasq_leases()
    xml_cache = {}
    slots = assign_port_slots(vms, existing_slots)
    snap = {
        "external_ip": get_external_ip(),
        "vms": {},
        "port_slots": slots,
    }
    for name, state in sorted(vms.items()):
        running = state == "running"
        snap["vms"][name] = {
            "state": state,
            "ips": vm_ips(name, leases, xml_cache) if running else [],
            "graphics": vm_graphics(name, running, xml_cache),
        }
    return snap


def read_state(state_file):
    """Читает {last_polled, last_notified, port_slots} с миграцией старого формата."""
    empty = {"last_polled": None, "last_notified": None, "port_slots": {}}
    try:
        raw = json.loads(Path(state_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty
    except Exception as e:
        warn(f"Не удалось прочитать state-файл {state_file}: {e}")
        return empty
    if not isinstance(raw, dict):
        return empty
    if "last_polled" in raw or "last_notified" in raw:
        polled = raw.get("last_polled")
        notified = raw.get("last_notified")
        slots = dict(raw.get("port_slots") or {})
        if not slots and isinstance(polled, dict):
            slots = dict(polled.get("port_slots") or {})
        return {
            "last_polled": polled if isinstance(polled, dict) else None,
            "last_notified": notified if isinstance(notified, dict) else None,
            "port_slots": slots,
        }
    if "vms" in raw:
        return {
            "last_polled": raw,
            "last_notified": raw,
            "port_slots": assign_port_slots(raw.get("vms") or {}, raw.get("port_slots")),
        }
    return empty


def write_state(state_file, state):
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


# Совместимость по именам функций для внешних вызовов/тестов.
def read_snapshot(state_file):
    return read_state(state_file)["last_notified"]


def write_snapshot(state_file, snap, notified=True):
    st = read_state(state_file)
    st["last_polled"] = snap
    if isinstance(snap, dict) and snap.get("port_slots"):
        st["port_slots"] = dict(snap["port_slots"])
    if notified:
        st["last_notified"] = snap
    write_state(state_file, st)


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


def format_message(snap, changes, first_run):
    """Форматирует сводку состояния без паролей и секретов."""
    lines = []
    lines.append(
        "KVM-хост — начальное состояние"
        if first_run
        else "KVM-хост — состояние изменилось"
    )
    lines.append("")
    for name, vm in sorted((snap.get("vms") or {}).items()):
        if vm["state"] != "running":
            lines.append(f"• {name}: {vm['state']}")
            continue
        ips = ", ".join(vm["ips"]) if vm["ips"] else "IP не виден"
        lines.append(f"• {name}: running, {ips}, {fmt_graphics(vm['graphics'])}")
    lines.append("")
    lines.append(f"Внешний IP: {snap.get('external_ip') or 'неизвестен'}")
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
    p.add_argument("--inventory", action="store_true", help="Напечатать снимок состояния как JSON и выйти (для tunnel.py)")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("TELEGRAM_BOT_TOKEN") or ""
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("TELEGRAM_CHAT_ID") or ""

    state_file = args.state_file or str(HERE / "state" / "vm_state.json")
    state = read_state(state_file)

    snap = take_snapshot(existing_slots=state["port_slots"])
    if snap is None:
        fail("Опрос libvirt завершился ошибкой — state-файл не изменён")
        return 1

    if args.inventory:
        if not args.dry_run and snap["port_slots"] != state["port_slots"]:
            state["port_slots"] = dict(snap["port_slots"])
            try:
                write_state(state_file, state)
            except Exception:
                pass
        print(json.dumps(snap, sort_keys=True))
        return 0

    parts = [f"{n}={v['state']}" for n, v in sorted(snap["vms"].items())]
    info(f"VM: {', '.join(parts) or 'нет'}")
    if snap["external_ip"]:
        info(f"Внешний IP: {snap['external_ip']}")

    old_notified = state["last_notified"]
    first_run = old_notified is None
    changes = diff_snapshots(old_notified, snap)

    if args.dry_run:
        if not changes and not args.force:
            print("[dry-run] Без изменений, сообщение не требуется")
            return 0
        print("[dry-run] Сообщение было бы таким:")
        print(format_message(snap, changes, first_run))
        print("[dry-run] Telegram не вызывался, state-файл не менялся")
        return 0

    state["last_polled"] = snap
    state["port_slots"] = dict(snap["port_slots"])

    if not changes and not args.force:
        write_state(state_file, state)
        print("Без изменений, Telegram не трогаем")
        return 0
    if not changes and args.force:
        info("--force: отправляю сообщение, хотя ничего не изменилось")

    if not tg_token or not tg_chat:
        warn("Telegram не настроен (нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — уведомление отложено")
        write_state(state_file, state)
        return 0

    text = format_message(snap, changes, first_run)
    if tg_notify(tg_token, tg_chat, text):
        state["last_notified"] = snap
        write_state(state_file, state)
        ok(f"Telegram: уведомление отправлено, state обновлён: {state_file}")
        return 0

    warn("Telegram: уведомление НЕ доставлено — изменение сохранено для повторной отправки")
    write_state(state_file, state)
    return 1


if __name__ == "__main__":
    sys.exit(main())
