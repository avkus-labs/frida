#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приёмочные регрессионные тесты по результатам аудита безопасности и корректности.
Выполняются полностью на моках (без живых Android-устройств, libvirt, SSH, Telegram и Cloudflare).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import interactive
import main as g1_main
import setup as g1_setup
import sync_offers
import tunnel
import update_dns
import vm_watch


def proc_res(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["mock"], returncode=rc, stdout=stdout, stderr=stderr)


class TestSecretsAndPrivacy(unittest.TestCase):
    """Критерий 1: секреты не попадают ни в вывод/сообщения, ни в argv дочерних процессов."""

    def test_vm_watch_never_outputs_vnc_password(self):
        secret = "SuperSecretVncPass42!"
        snap = {
            "external_ip": "203.0.113.10",
            "vms": {
                "bliss-01": {
                    "state": "running",
                    "ips": ["10.166.0.10"],
                    "graphics": {"type": "vnc", "port": 5901},
                }
            },
            "port_slots": {"bliss-01": 0},
        }
        msg = vm_watch.format_message(snap, ["начальный снимок"], first_run=True)
        self.assertNotIn(secret, msg)
        self.assertNotIn("VNC пароль", msg)

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "vm_state.json"
            sent_messages = []

            def fake_tg(tok, chat, text):
                sent_messages.append(text)
                return True

            buf = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "VNC_PASSWORD": secret,
                    "TELEGRAM_BOT_TOKEN": "bot-token",
                    "TELEGRAM_CHAT_ID": "12345",
                },
                clear=False,
            ), mock.patch.object(vm_watch, "take_snapshot", return_value=snap), mock.patch.object(
                vm_watch, "tg_notify", side_effect=fake_tg
            ), mock.patch.object(
                sys, "argv", ["vm_watch.py", "--state-file", str(state_path), "--dry-run"]
            ), contextlib.redirect_stdout(buf):
                rc = vm_watch.main()
            self.assertEqual(rc, 0)
            self.assertNotIn(secret, buf.getvalue())

            buf2 = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "VNC_PASSWORD": secret,
                    "TELEGRAM_BOT_TOKEN": "bot-token",
                    "TELEGRAM_CHAT_ID": "12345",
                },
                clear=False,
            ), mock.patch.object(vm_watch, "take_snapshot", return_value=snap), mock.patch.object(
                vm_watch, "tg_notify", side_effect=fake_tg
            ), mock.patch.object(
                sys, "argv", ["vm_watch.py", "--state-file", str(state_path)]
            ), contextlib.redirect_stdout(buf2):
                rc2 = vm_watch.main()
            self.assertEqual(rc2, 0)
            self.assertEqual(len(sent_messages), 1)
            self.assertNotIn(secret, sent_messages[0])
            self.assertNotIn(secret, buf2.getvalue())

    def test_interactive_never_collects_password_or_calls_input_text(self):
        self.assertFalse(hasattr(interactive, "adb_input_text"))
        self.assertNotIn("getpass", interactive.__dict__)

        recorded_cmds = []

        class FakeAdb:
            def shell(self, *args, **_kwargs):
                recorded_cmds.append(args)
                if args[:2] == ("dumpsys", "account"):
                    return "Account {name=user1@gmail.com, type=com.google}\n"
                return ""

        fake_adb = FakeAdb()
        buf = io.StringIO()
        with mock.patch("builtins.input", return_value=""), contextlib.redirect_stdout(buf):
            ok_acc = interactive. add_account_flow(fake_adb)
        self.assertTrue(ok_acc)
        for cmd in recorded_cmds:
            self.assertNotIn("text", cmd, "ADB не должен печатать учётные данные через input text")

    def test_interactive_multi_account_does_not_claim_fake_selection(self):
        class FakeAdb:
            def shell(self, *args, **_kwargs):
                if args[:2] == ("dumpsys", "account"):
                    return (
                        "Account {name=first@gmail.com, type=com.google}\n"
                        "Account {name=second@gmail.com, type=com.google}\n"
                    )
                raise AssertionError(f"Неожиданный вызов adb: {args}")

        buf = io.StringIO()
        with mock.patch("builtins.input", return_value=""), contextlib.redirect_stdout(buf):
            res = interactive.choose_account(FakeAdb())
        self.assertTrue(res)
        out = buf.getvalue()
        self.assertNotIn("Используем аккаунт: second@gmail.com", out)
        self.assertIn("НЕ переключает", out)

    def test_play_db_fallback_supports_all_g1_tiers_and_hides_token(self):
        secret_tok = "VERY_SECRET_PURCHASE_TOKEN_1234567890"
        db_output = "\n".join(
            [
                # Аддон YouTube должен игнорироваться в пользу основного тарифа:
                'subs:g1.youtube_premium_individual_add_on\t{"productId":"g1.youtube_premium_individual_add_on","purchaseToken":"YT_ADDON_TOKEN"}',
                # Основной тариф Ultra 20x (раньше игнорировался хардкодом 2tb.ai!):
                f'subs:g1.play.ai.pro\t{{"productId":"g1.play.ai.pro","purchaseToken":"{secret_tok}"}}',
            ]
        )
        buf = io.StringIO()
        with mock.patch.object(g1_main, "su_sh", return_value=db_output), contextlib.redirect_stdout(buf):
            tok, sku = g1_main.read_play_db_token()
        self.assertEqual(tok, secret_tok)
        self.assertEqual(sku, "g1.play.ai.pro")
        self.assertNotIn(secret_tok, buf.getvalue())
        self.assertNotIn(secret_tok[:8], buf.getvalue())
        self.assertNotIn("YT_ADDON_TOKEN", buf.getvalue())

    def test_js_sources_have_no_su_or_token_slicing_or_billing_apk_fallback(self):
        for name in ("frida.js", "probe-one.js", "probe-single.js"):
            src = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("/data/local/tmp/billing.apk", src, name)
            self.assertNotIn(".slice(0, 16)", src, name)
            self.assertNotIn(".slice(0, 12)", src, name)
            self.assertNotIn("ProcessBuilder", src, name)
            self.assertNotIn("library.db", src, name)


class TestDeviceAndPortIsolation(unittest.TestCase):
    """Критерий 2: недоступность устройства или остановка ВМ не ведёт на чужую машину."""

    def test_explicit_serial_never_falls_back_to_other_adb_device(self):
        adb = g1_main.Adb(serial="127.0.0.1:15551", explicit=True)
        adb.exe = "adb"
        calls = []

        def fake_cmd(args, serial=None, timeout=None):
            calls.append((args, serial))
            if args == ["devices"]:
                # Доступно ДРУГОЕ устройство 127.0.0.1:15552, а запрошенного 15551 нет!
                return proc_res(0, "List of devices attached\n127.0.0.1:15552\tdevice\n")
            if args[:1] == ["connect"]:
                return proc_res(1, "failed to connect")
            raise AssertionError(f"Неожиданная команда на чужом устройстве: {args}")

        buf = io.StringIO()
        with mock.patch.object(adb, "_cmd", side_effect=fake_cmd), contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                adb.pick()
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(adb.serial, "127.0.0.1:15551")

    def test_frida_attach_never_falls_back_to_usb_device(self):
        sess = g1_main.Session()
        fake_frida = types.SimpleNamespace()
        other_dev = types.SimpleNamespace(id="usb-other-phone", attach=mock.Mock())
        mgr = types.SimpleNamespace(enumerate_devices=mock.Mock(return_value=[other_dev]))
        fake_frida.get_device_manager = mock.Mock(return_value=mgr)
        fake_frida.get_usb_device = mock.Mock(side_effect=AssertionError("get_usb_device вызван!"))

        buf = io.StringIO()
        with mock.patch.dict(sys.modules, {"frida": fake_frida}), mock.patch.object(
            g1_main.adb, "serial", "127.0.0.1:15551"
        ), mock.patch.object(g1_main.time, "sleep"), contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                sess.attach(1234)
        self.assertEqual(ctx.exception.code, 1)
        fake_frida.get_usb_device.assert_not_called()
        other_dev.attach.assert_not_called()

    def test_auto_pick_scores_each_device_only_once(self):
        adb = g1_main.Adb(serial="", explicit=False)
        adb.serial = ""
        adb.exe = "adb"
        score_calls = []

        def fake_score(s):
            score_calls.append(s)
            return 20 if s == "dev-b" else 5

        buf = io.StringIO()
        with mock.patch.object(adb, "discover", return_value=["dev-a", "dev-b"]), mock.patch.object(
            adb, "_score", side_effect=fake_score
        ), contextlib.redirect_stdout(buf):
            picked = adb.pick()
        self.assertEqual(picked, "dev-b")
        self.assertEqual(score_calls, ["dev-a", "dev-b"])

    def test_tunnel_ports_stay_pinned_after_neighbor_vm_stops_or_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ports_file = Path(tmp) / "tunnel_ports.json"
            inv_both = {
                "vms": {
                    "vm-a": {"state": "running", "ips": ["10.0.0.1"], "graphics": {"type": "vnc", "port": 5900}},
                    "vm-b": {"state": "running", "ips": ["10.0.0.2"], "graphics": {"type": "vnc", "port": 5901}},
                }
            }
            fw1, _ = tunnel.build_forwards(inv_both, 5000, 5900, state_file=ports_file)
            adb_ports_1 = {vm: port for port, _h, _p, svc, vm in fw1 if svc == "ADB"}
            self.assertEqual(adb_ports_1, {"vm-a": 5000, "vm-b": 5001})

            # Сценарий 1: vm-a остановлена (shut off) — порт vm-b обязан остаться 5001 (даже без state_file!).
            inv_a_stopped = {
                "vms": {
                    "vm-a": {"state": "shut off", "ips": [], "graphics": {"type": "vnc", "port": None}},
                    "vm-b": {"state": "running", "ips": ["10.0.0.2"], "graphics": {"type": "vnc", "port": 5901}},
                }
            }
            fw2_stateless, _ = tunnel.build_forwards(inv_a_stopped, 5000, 5900)
            adb_ports_2 = {vm: port for port, _h, _p, svc, vm in fw2_stateless if svc == "ADB"}
            self.assertEqual(adb_ports_2, {"vm-b": 5001})

            # Сценарий 2: vm-a вообще удалена (undefine) — state-файл всё равно удерживает vm-b на 5001!
            inv_a_deleted = {
                "vms": {
                    "vm-b": {"state": "running", "ips": ["10.0.0.2"], "graphics": {"type": "vnc", "port": 5901}},
                }
            }
            fw3, _ = tunnel.build_forwards(inv_a_deleted, 5000, 5900, state_file=ports_file)
            adb_ports_3 = {vm: port for port, _h, _p, svc, vm in fw3 if svc == "ADB"}
            self.assertEqual(adb_ports_3, {"vm-b": 5001})


class TestIntegrityAndErrorHandling(unittest.TestCase):
    """Критерий 3: проверка файлов до запуска и честная обработка ошибок без ложного успеха."""

    def test_frida_server_never_executes_before_sha256_and_aborts_on_push_failure(self):
        executed_shell_cmds = []
        fake_local = Path(tempfile.gettempdir()) / f"fake_frida_{os.getpid()}"
        fake_local.write_bytes(b"\x7fELF" + b"\x00" * (1024 * 1024 + 64))
        expected_sha = g1_main.sha256_file(fake_local)

        def fake_shell(*parts):
            executed_shell_cmds.append(parts)
            if parts == ("getprop", "ro.product.cpu.abi"):
                return "x86_64"
            if parts[:2] == ("sha256sum", "-b"):
                # На устройстве лежит чужой/подменённый файл с другим хешем!
                return "0" * 64 + "  /data/local/tmp/frida-server"
            if parts == ("pidof", "frida-server"):
                return ""
            return ""

        try:
            buf = io.StringIO()
            with mock.patch.object(g1_main.adb, "shell", side_effect=fake_shell), mock.patch.object(
                g1_main.adb, "run", return_value=proc_res(1, "", "adb: error: failed to copy")
            ), mock.patch.object(
                g1_main, "local_frida_server", return_value=fake_local
            ), mock.patch.object(
                g1_main, "start_remote_frida", side_effect=AssertionError("Запуск при ошибке push!")
            ), contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:
                    g1_main.ensure_frida_server("17.9.1")
            self.assertEqual(ctx.exception.code, 1)
            # Убеждаемся, что --version НИКОГДА не вызывался на непроверенном файле:
            for cmd in executed_shell_cmds:
                self.assertNotIn("--version", cmd)
                self.assertNotIn(g1_main.FRIDA_REMOTE, cmd[:1])
        finally:
            fake_local.unlink(missing_ok=True)
            self.assertTrue(len(expected_sha) == 64)

    def test_setup_is_installed_requires_exact_package_match(self):
        fake_adb = types.SimpleNamespace(
            shell=lambda *_a, **_kw: "package:example.expected.extra\npackage:other.pkg\n"
        )
        self.assertFalse(g1_setup.is_installed(fake_adb, "example.expected"))

        fake_adb_exact = types.SimpleNamespace(
            shell=lambda *_a, **_kw: "package:example.expected.extra\npackage:example.expected\n"
        )
        self.assertTrue(g1_setup.is_installed(fake_adb_exact, "example.expected"))

    def test_setup_force_reinstall_failure_returns_false_even_if_old_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / "app.apk"
            apk.write_bytes(b"PK\x03\x04" + b"x" * 1024)

            class FakeAdb:
                def shell(self, *args, **_kwargs):
                    if args[:3] == ("pm", "list", "packages"):
                        return "package:example.expected\n"
                    return ""

                def run(self, *args, **_kwargs):
                    return proc_res(0, "Performing Streamed Install\nFailure [INSTALL_FAILED_VERSION_DOWNGRADE]\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                res = g1_setup.ensure_app(
                    FakeAdb(), "example.expected", "TestApp", "", str(apk), Path(tmp), force=True
                )
            self.assertFalse(res)

    def test_setup_failed_download_leaves_no_cached_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "broken.apk"
            buf = io.StringIO()
            # Слишком маленький ответ (100 байт < 1 МБ) не должен оставлять dest!
            fake_resp = io.BytesIO(b"tiny-error-page")
            with mock.patch("urllib.request.urlopen", return_value=contextlib.nullcontext(fake_resp)), contextlib.redirect_stdout(buf):
                ok_dl = g1_setup.download_apk("https://example.com/app.apk", dest)
            self.assertFalse(ok_dl)
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_suffix(".apk.part").exists())

    def test_setup_adb_wait_checks_returncode(self):
        adb = g1_setup.Adb("adb", "127.0.0.1:15551")
        buf = io.StringIO()
        with mock.patch.object(adb, "run", return_value=proc_res(1, "", "device offline")), contextlib.redirect_stdout(buf):
            self.assertFalse(adb.wait())

    def test_vm_watch_distinguishes_virsh_error_and_retries_failed_telegram(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "vm_state.json"
            good_snap = {
                "external_ip": "203.0.113.5",
                "vms": {"bliss-01": {"state": "running", "ips": ["10.0.0.2"], "graphics": {"type": "vnc", "port": 5900}}},
                "port_slots": {"bliss-01": 0},
            }

            # 1. При сбое Telegram возвращается rc=1, а изменение НЕ помечается как доставленное!
            buf = io.StringIO()
            with mock.patch.dict(
                os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "1"}, clear=False
            ), mock.patch.object(vm_watch, "take_snapshot", return_value=good_snap), mock.patch.object(
                vm_watch, "tg_notify", return_value=False
            ), mock.patch.object(
                sys, "argv", ["vm_watch.py", "--state-file", str(state_file)]
            ), contextlib.redirect_stdout(buf):
                rc1 = vm_watch.main()
            self.assertEqual(rc1, 1)
            st1 = vm_watch.read_state(state_file)
            self.assertIsNotNone(st1["last_polled"])
            self.assertIsNone(st1["last_notified"])

            # 2. На следующем цикле состояние VM то же самое, но т.к. прошлое уведомление не дошло — отправляет снова!
            tg_calls = []
            with mock.patch.dict(
                os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "1"}, clear=False
            ), mock.patch.object(vm_watch, "take_snapshot", return_value=good_snap), mock.patch.object(
                vm_watch, "tg_notify", side_effect=lambda *_a: (tg_calls.append(True) or True)
            ), mock.patch.object(
                sys, "argv", ["vm_watch.py", "--state-file", str(state_file)]
            ), contextlib.redirect_stdout(buf):
                rc2 = vm_watch.main()
            self.assertEqual(rc2, 0)
            self.assertEqual(len(tg_calls), 1)
            st2 = vm_watch.read_state(state_file)
            self.assertEqual(st2["last_notified"], good_snap)

            # 3. Теперь падает `virsh list` (rc=1) — list_vms() обязан вернуть None, а сохранённый state не затирается!
            with mock.patch.object(vm_watch, "virsh", return_value=(1, "", "libvirtd down")), mock.patch.object(
                sys, "argv", ["vm_watch.py", "--state-file", str(state_file)]
            ), contextlib.redirect_stdout(buf):
                rc3 = vm_watch.main()
            self.assertEqual(rc3, 1)
            st3 = vm_watch.read_state(state_file)
            self.assertEqual(st3["last_notified"], good_snap)


class TestCatalogAndOfferSync(unittest.TestCase):
    """Проверка парсера всех 109 планов, interactive.py и sync_offers.py."""

    def test_all_109_plans_parsed_and_consistent(self):
        js_text = (ROOT / "frida.js").read_text(encoding="utf-8")
        plans = g1_main.parse_plans(js_text)
        self.assertEqual(len(plans), 109)
        self.assertIn("lite_base", plans)
        self.assertEqual(plans["lite_base"]["offer"], "")

        inter_rows = interactive.load_plans()
        self.assertEqual(len(inter_rows), 109)

        total, only_js, only_txt, diff_vals = sync_offers.check_sync(
            ROOT / "frida.js", ROOT / "offers.txt"
        )
        self.assertEqual(total, 109)
        self.assertEqual((only_js, only_txt, diff_vals), ([], [], []))

    def test_sync_offers_imports_only_live_entries_from_scan(self):
        js_text = (ROOT / "frida.js").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            scan_log = Path(tmp) / "scan-results.log"
            scan_log.write_text(
                "# scan header\n"
                "new_promo_6m\tg1.play.helium\teft-6mo-2027\tlive\t0\tP6M\n"
                "dead_promo\tg1.dead.sku\tfreetrial\tmissing\t\t\n"
                "cand_2tb_12m\tg1.2tb.12months_eft\tfreetrial\tlive\t0\tP1Y\n",
                encoding="utf-8",
            )
            entries = sync_offers.read_scan_log(scan_log, only_live=True)
            self.assertEqual([e["id"] for e in entries], ["new_promo_6m", "cand_2tb_12m"])
            updated_js, added, updated = sync_offers.update_js_plans(js_text, entries)
            self.assertEqual(added, ["new_promo_6m"])
            self.assertIn("cand_2tb_12m", updated)
            parsed = g1_main.parse_plans(updated_js)
            self.assertEqual(len(parsed), 110)
            self.assertEqual(parsed["new_promo_6m"]["offer"], "eft-6mo-2027")
            self.assertFalse(parsed["cand_2tb_12m"]["note"].startswith("[кандидат]"))

    def test_ip_validation_rejects_malformed_strings(self):
        self.assertFalse(update_dns.is_valid_ipv4("..."))
        self.assertFalse(update_dns.is_valid_ipv4("999.999.999.999"))
        self.assertTrue(update_dns.is_valid_ipv4("203.0.113.42"))
        self.assertFalse(vm_watch.is_valid_ipv4("1.2.3"))


if __name__ == "__main__":
    unittest.main()
