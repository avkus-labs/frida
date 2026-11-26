#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tunnel.py — SSH-туннель к KVM-машинам со стабильной привязкой портов.

Что делает:
  1. По SSH спрашивает у хоста снимок всех VM (`vm_watch.py --inventory`).
  2. Закрепляет за каждой VM постоянный индекс слота в state-файле
     (`state/tunnel_ports.json` + `port_slots` из инвентаря хоста):
     выключение или удаление соседней VM НЕ сдвигает порты остальных машин.
  3. Строит пробросы `-L` только для запущенных VM с доступным ADB/VNC
     и держит ssh-сессию на переднем плане до Ctrl+C.

Локальные порты (по постоянному слоту VM):
  - ADB: 15551 + slot
  - VNC: 15901 + slot

Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_HOST = "vm-host.example.com"
DEFAULT_PORT = 2222
DEFAULT_USER = "vmuser"
DEFAULT_ADB_BASE = 15551
DEFAULT_VNC_BASE = 15901
DEFAULT_INVENTORY_CMD = "python3 ~/frida/vm_watch.py --inventory"

DEFAULT_CONFIG = {
    "SSH_HOST": DEFAULT_HOST,
    "SSH_PORT": DEFAULT_PORT,
    "SSH_USER": DEFAULT_USER,
    "SSH_INVENTORY_CMD": DEFAULT_INVENTORY_CMD,
}


def info(msg):
    print(f"[*] {msg}", flush=True)


def ok(msg):
    print(f"[+] {msg}", flush=True)


def warn(msg):
    print(f"[!] {msg}", flush=True)


def fail(msg):
    print(f"[x] {msg}", flush=True)


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


def parse_ssh_opts(raw_opts):
    """Разбирает строку опций SSH с учётом кавычек."""
    if not raw_opts:
        return []
    return shlex.split(raw_opts, posix=(os.name != "nt"))


def run_ssh_query(ssh_bin, ssh_opts, host, port, user, remote_cmd):
    """Выполняет команду на хосте по SSH. Возвращает (rc, stdout, stderr)."""
    cmd = [ssh_bin] + list(ssh_opts) + [
        "-p", str(port),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=30",
        f"{user}@{host}",
        remote_cmd,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)


def get_inventory(ssh_bin, ssh_opts, host, port, user, inventory_cmd=DEFAULT_INVENTORY_CMD):
    """Спрашивает у хоста снимок VM. Возвращает dict или None при ошибке."""
    rc, out, err = run_ssh_query(ssh_bin, ssh_opts, host, port, user, inventory_cmd)
    if rc != 0:
        fail(f"Не удалось опросить хост {host} (ssh rc={rc})")
        if err.strip():
            print(err.strip(), flush=True)
        return None
    try:
        data = json.loads(out.strip())
    except Exception as e:
        fail(f"Хост вернул не JSON ({e}): {out.strip()[:300]}")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("vms"), dict):
        fail("Ответ хоста не содержит корректного словаря 'vms'")
        return None
    return data


def read_port_slots(state_file):
    if not state_file:
        return {}
    try:
        raw = json.loads(Path(state_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        warn(f"Не удалось прочитать таблицу портов {state_file}: {e}")
        return {}
    slots = raw.get("port_slots") if isinstance(raw, dict) and "port_slots" in raw else raw
    if not isinstance(slots, dict):
        return {}
    clean = {}
    for k, v in slots.items():
        if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            clean[k] = v
    return clean


def write_port_slots(state_file, slots):
    if not state_file:
        return
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"port_slots": slots}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def resolve_port_slots(vms, remote_slots=None, saved_slots=None):
    """Объединяет сохранённые и серверные слоты без переназначения занятых индексов."""
    slots = {}
    used_indices = set()

    for name, idx in (saved_slots or {}).items():
        if isinstance(name, str) and isinstance(idx, int) and not isinstance(idx, bool) and idx >= 0:
            if idx not in used_indices:
                slots[name] = idx
                used_indices.add(idx)

    for name, idx in sorted((remote_slots or {}).items()):
        if name in slots:
            continue
        if isinstance(name, str) and isinstance(idx, int) and not isinstance(idx, bool) and idx >= 0:
            if idx not in used_indices:
                slots[name] = idx
                used_indices.add(idx)

    next_idx = 0
    for name in sorted(vms or {}):
        if name in slots:
            continue
        while next_idx in used_indices:
            next_idx += 1
        slots[name] = next_idx
        used_indices.add(next_idx)
        next_idx += 1

    return slots


def build_forwards(inventory, adb_base, vnc_base, state_file=None, persist=True):
    """Строит список пробросов со стабильными портами за каждой VM.

    forwards: список (local_port, target_host, target_port, service, vm_name)
    mapping: список строк для сводки.
    """
    vms = (inventory or {}).get("vms") or {}
    remote_slots = (inventory or {}).get("port_slots") or {}
    saved_slots = read_port_slots(state_file)
    slots = resolve_port_slots(vms, remote_slots=remote_slots, saved_slots=saved_slots)

    if state_file and persist and slots != saved_slots:
        write_port_slots(state_file, slots)

    forwards = []
    mapping = []
    for name in sorted(vms, key=lambda n: (slots[n], n)):
        vm = vms[name]
        slot = slots[name]
        if vm.get("state") != "running":
            continue
        ips = vm.get("ips") or []
        graphics = vm.get("graphics") or {}
        gtype = graphics.get("type")
        gport = graphics.get("port")
        has_adb = bool(ips)
        has_vnc = bool(gtype == "vnc" and gport)
        if not has_adb and not has_vnc:
            continue
        adb_local = adb_base + slot
        vnc_local = vnc_base + slot
        if has_adb:
            forwards.append((adb_local, ips[0], 5555, "ADB", name))
            mapping.append(
                f"  {name} (слот {slot}): ADB  127.0.0.1:{adb_local}  →  {ips[0]}:5555"
            )
        if has_vnc:
            forwards.append((vnc_local, "127.0.0.1", gport, "VNC", name))
            mapping.append(
                f"  {name} (слот {slot}): VNC  127.0.0.1:{vnc_local}  →  хост:{gport}"
            )
    return forwards, mapping


def parse_args(cfg=None):
    cfg = cfg or DEFAULT_CONFIG
    def_host = os.environ.get("SSH_HOST") or cfg.get("SSH_HOST") or DEFAULT_HOST
    def_port = int(os.environ.get("SSH_PORT") or cfg.get("SSH_PORT") or DEFAULT_PORT)
    def_user = os.environ.get("SSH_USER") or cfg.get("SSH_USER") or DEFAULT_USER
    def_cmd = os.environ.get("SSH_INVENTORY_CMD") or cfg.get("SSH_INVENTORY_CMD") or DEFAULT_INVENTORY_CMD

    p = argparse.ArgumentParser(
        description="SSH-туннель к запущенным KVM-машинам со стабильными портами (ADB+VNC)."
    )
    p.add_argument("--host", default=def_host, help=f"SSH-хост (по умолчанию {def_host})")
    p.add_argument("--port", type=int, default=def_port, help=f"SSH-порт (по умолчанию {def_port})")
    p.add_argument("--user", default=def_user, help=f"SSH-пользователь (по умолчанию {def_user})")
    p.add_argument("--inventory-cmd", default=def_cmd, help="Команда получения JSON-инвентаря на хосте")
    p.add_argument("--ports-file", default="", help="Файл закрепления портов за VM (по умолчанию state/tunnel_ports.json)")
    p.add_argument("--ssh", default="ssh", help="Путь к ssh (по умолчанию ssh из PATH)")
    p.add_argument("--ssh-opts", default="", help="Доп. опции ssh строкой, например: -F ~/.ssh/config -o StrictHostKeyChecking=accept-new")
    p.add_argument("--adb-base", type=int, default=DEFAULT_ADB_BASE, help=f"Первый локальный порт ADB (по умолчанию {DEFAULT_ADB_BASE})")
    p.add_argument("--vnc-base", type=int, default=DEFAULT_VNC_BASE, help=f"Первый локальный порт VNC (по умолчанию {DEFAULT_VNC_BASE})")
    p.add_argument("--no-adb", action="store_true", help="Не пробрасывать ADB, только VNC")
    p.add_argument("--no-vnc", action="store_true", help="Не пробрасывать VNC, только ADB")
    p.add_argument("--dry-run", action="store_true", help="Только показать команду ssh и сводку, не запускать туннель")
    return p.parse_args()


def main():
    cfg = load_config()
    args = parse_args(cfg)
    ssh_opts = parse_ssh_opts(args.ssh_opts)
    ports_file = args.ports_file or str(HERE / "state" / "tunnel_ports.json")

    print("=" * 64)
    print(f"  tunnel.py — SSH-туннель к {args.host}")
    print("=" * 64)

    inventory = get_inventory(
        args.ssh, ssh_opts, args.host, args.port, args.user, args.inventory_cmd
    )
    if inventory is None:
        return 1
    info(f"Внешний IP хоста: {inventory.get('external_ip') or 'неизвестен'}")

    forwards, mapping = build_forwards(
        inventory,
        args.adb_base,
        args.vnc_base,
        state_file=ports_file,
        persist=(not args.dry_run),
    )
    if args.no_adb:
        forwards = [f for f in forwards if f[3] != "ADB"]
        mapping = [m for m in mapping if ": ADB " not in m]
    if args.no_vnc:
        forwards = [f for f in forwards if f[3] != "VNC"]
        mapping = [m for m in mapping if ": VNC " not in m]
    if not forwards:
        warn("Нет запущенных VM с ADB/VNC — пробрасывать нечего, туннель не запускаю")
        return 0

    print()
    print("  Пробросы (порты закреплены за именами VM):")
    for line in mapping:
        print(line)
    print()
    print("  После запуска, в другой вкладке:")
    for local, _t_host, _t_port, service, vm in forwards:
        if service == "ADB":
            print(f"    adb connect 127.0.0.1:{local}   # {vm}")
    for local, _t_host, _t_port, service, vm in forwards:
        if service == "VNC":
            print(f"    VNC → 127.0.0.1:{local}  # {vm}")

    ssh_cmd = [args.ssh] + ssh_opts + ["-N", "-p", str(args.port)]
    for local, t_host, t_port, _service, _vm in forwards:
        ssh_cmd += ["-L", f"{local}:{t_host}:{t_port}"]
    ssh_cmd += [f"{args.user}@{args.host}"]

    print()
    print("  Команда:")
    print("  " + " ".join(shlex.quote(part) for part in ssh_cmd))
    print()

    if args.dry_run:
        print("[dry-run] Туннель не запускался, таблица портов не менялась")
        return 0

    ok("Поднимаю туннель (Ctrl+C — закрыть)…")
    try:
        proc = subprocess.run(ssh_cmd)
        rc = proc.returncode
    except KeyboardInterrupt:
        print()
        ok("Туннель закрыт (Ctrl+C)")
        return 0
    if rc != 0:
        fail(f"ssh завершился с кодом {rc}")
        return rc or 1
    ok("Туннель закрыт")
    return 0


if __name__ == "__main__":
    sys.exit(main())
