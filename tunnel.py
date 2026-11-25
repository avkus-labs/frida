#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tunnel.py — динамический SSH-туннель к KVM-машинам на debian-nested.

Что делает:
  1. По SSH спрашивает у хоста, какие VM запущены и какие у них
     внутренние IP и VNC-порты (vm_watch.py --inventory).
  2. Строит SSH-туннель: на каждую запущенную VM — свой локальный порт
     для ADB и свой для VNC. Сколько VM работает, столько пар портов:
     одна — одна пара, две — две, три — три.
  3. Держит туннель открытым (ssh работает на переднем плане),
     пока окно терминала не закроют или не нажмут Ctrl+C.

Порты (локальные, на твоём компьютере):
  - ADB: 15551, 15552, 15553, ... (по порядку имён VM)
  - VNC: 15901, 15902, 15903, ... (тот же порядок)
  Пример: bliss-01 → ADB 127.0.0.1:15551, VNC 127.0.0.1:15901.

Использование (Windows / macOS / Linux, нужен ssh в PATH):
  python3 tunnel.py
  python3 tunnel.py --dry-run        # только показать, что было бы запущено
  python3 tunnel.py --user gru_avkus # другой SSH-пользователь

После запуска в другой вкладке:
  adb connect 127.0.0.1:15551   # bliss-01 (порт из сводки)
  VNC-клиент → 127.0.0.1:15901  # экран bliss-01

Только стандартная библиотека. Живёт во frida рядом с vm_watch.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

DEFAULT_HOST = "debian-nested.avkus.bond"
DEFAULT_PORT = 2222
DEFAULT_USER = "avkuska"
DEFAULT_ADB_BASE = 15551
DEFAULT_VNC_BASE = 15901
INVENTORY_CMD = "python3 /home/avkuska/frida/vm_watch.py --inventory"


def info(msg):
    print(f"[*] {msg}", flush=True)


def ok(msg):
    print(f"[+] {msg}", flush=True)


def warn(msg):
    print(f"[!] {msg}", flush=True)


def fail(msg):
    print(f"[x] {msg}", flush=True)


def run_ssh_query(ssh_bin, ssh_opts, host, port, user, remote_cmd):
    """Выполняет команду на хосте по SSH. Возвращает (rc, stdout, stderr)."""
    cmd = [ssh_bin] + ssh_opts + [
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


def get_inventory(ssh_bin, ssh_opts, host, port, user):
    """Спрашивает у хоста снимок VM. Возвращает dict или None при ошибке."""
    rc, out, err = run_ssh_query(ssh_bin, ssh_opts, host, port, user, INVENTORY_CMD)
    if rc != 0:
        fail(f"Не удалось опросить хост {host} (ssh rc={rc})")
        if err.strip():
            print(err.strip(), flush=True)
        return None
    try:
        return json.loads(out.strip())
    except Exception as e:
        fail(f"Хост вернул не JSON ({e}): {out.strip()[:300]}")
        return None


def build_forwards(inventory, adb_base, vnc_base):
    """Строит список пробросов. Возвращает (forwards, mapping).

    forwards: список (local_port, target_host, target_port, service, vm_name)
    mapping: список строк для сводки.
    """
    vms = (inventory or {}).get("vms") or {}
    forwards = []
    mapping = []
    index = 0
    for name in sorted(vms):
        vm = vms[name]
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
        adb_local = adb_base + index
        vnc_local = vnc_base + index
        index += 1
        if has_adb:
            forwards.append((adb_local, ips[0], 5555, "ADB", name))
            mapping.append(
                f"  {name}: ADB  127.0.0.1:{adb_local}  →  {ips[0]}:5555"
            )
        if has_vnc:
            forwards.append((vnc_local, "127.0.0.1", gport, "VNC", name))
            mapping.append(
                f"  {name}: VNC  127.0.0.1:{vnc_local}  →  хост:{gport}"
            )
    return forwards, mapping


def parse_args():
    p = argparse.ArgumentParser(
        description="Динамический SSH-туннель к запущенным KVM-машинам (ADB+VNC)."
    )
    p.add_argument("--host", default=DEFAULT_HOST, help=f"SSH-хост (по умолчанию {DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"SSH-порт (по умолчанию {DEFAULT_PORT})")
    p.add_argument("--user", default=DEFAULT_USER, help=f"SSH-пользователь (по умолчанию {DEFAULT_USER})")
    p.add_argument("--ssh", default="ssh", help="Путь к ssh (по умолчанию ssh из PATH)")
    p.add_argument("--ssh-opts", default="", help="Доп. опции ssh одной строкой, например: -F C:/Users/andre/.ssh/config -o StrictHostKeyChecking=accept-new")
    p.add_argument("--adb-base", type=int, default=DEFAULT_ADB_BASE, help=f"Первый локальный порт ADB (по умолчанию {DEFAULT_ADB_BASE})")
    p.add_argument("--vnc-base", type=int, default=DEFAULT_VNC_BASE, help=f"Первый локальный порт VNC (по умолчанию {DEFAULT_VNC_BASE})")
    p.add_argument("--no-adb", action="store_true", help="Не пробрасывать ADB, только VNC")
    p.add_argument("--no-vnc", action="store_true", help="Не пробрасывать VNC, только ADB")
    p.add_argument("--dry-run", action="store_true", help="Только показать команду ssh и сводку, не запускать туннель")
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 64)
    print("  tunnel.py — SSH-туннель к debian-nested")
    print("=" * 64)

    inventory = get_inventory(args.ssh, args.ssh_opts.split(), args.host, args.port, args.user)
    if inventory is None:
        return 1
    info(f"Внешний IP хоста: {inventory.get('external_ip') or 'неизвестен'}")

    forwards, mapping = build_forwards(inventory, args.adb_base, args.vnc_base)
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
    print("  Пробросы:")
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

    ssh_cmd = [args.ssh] + args.ssh_opts.split() + ["-p", str(args.port)]
    for local, t_host, t_port, _service, _vm in forwards:
        ssh_cmd += ["-L", f"{local}:{t_host}:{t_port}"]
    ssh_cmd += [f"{args.user}@{args.host}"]

    print()
    print("  Команда:")
    print("  " + " ".join(ssh_cmd))
    print()

    if args.dry_run:
        print("[dry-run] Туннель не запускался")
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
