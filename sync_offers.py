#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_offers.py — синхронизация живых тарифов между scan-results / offers.txt и frida.js.

Примеры:
  1. Проверить согласованность frida.js и offers.txt:
     python sync_offers.py --check

  2. Добавить живые офферы (status=live) из лога scan-offers.sh в frida.js и offers.txt:
     python sync_offers.py --from-scan scan-results-20261126-120000.log

  3. Перенести новые строки, вручную добавленные в offers.txt, в frida.js:
     python sync_offers.py --from-offers offers.txt

  4. Пересобрать offers.txt из таблицы PLANS в frida.js:
     python sync_offers.py --export-offers
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_JS = HERE / "frida.js"
DEFAULT_OFFERS = HERE / "offers.txt"

PLAN_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SKU_RE = re.compile(r"^[A-Za-z0-9._-]+$")
OFFER_RE = re.compile(r"^[A-Za-z0-9._-]*$")
PLANS_BLOCK_RE = re.compile(r"(var PLANS = \{)([\s\S]*?)(\n\};)")
ENTRY_RE = re.compile(
    r"^\s*(\w+)\s*:\s*\{\s*sku:\s*\"([^\"]+)\"\s*,\s*offer:\s*\"([^\"]*)\"\s*,\s*note:\s*\"((?:\\.|[^\"])*)\"\s*\}\s*,?\s*$"
)

PERIOD_LABELS = {
    "P1Y": "12 месяцев",
    "P6M": "6 месяцев",
    "P3M": "3 месяца",
    "P1M": "1 месяц",
    "P1W": "1 неделя",
}


def format_auto_note(sku, offer, price_micros="", period=""):
    """Генерирует понятное описание для нового оффера по цене и периоду."""
    per = PERIOD_LABELS.get(period, period)
    price_txt = ""
    if price_micros != "":
        try:
            micros = int(price_micros)
            if micros == 0:
                price_txt = "бесплатно"
            else:
                price_txt = f"${micros / 1_000_000:.2f}"
        except ValueError:
            price_txt = ""
    parts = [sku]
    if offer:
        parts.append(f"({offer})")
    if per:
        parts.append(per)
    if price_txt:
        parts.append(price_txt)
    return " ".join(parts)


def parse_js_plans(js_text):
    """Возвращает Ordered-словарь {id: {sku, offer, note}} из var PLANS."""
    m = PLANS_BLOCK_RE.search(js_text)
    if not m:
        raise ValueError("Не найден блок `var PLANS = { ... };` в frida.js")
    plans = {}
    for line in m.group(2).splitlines():
        em = ENTRY_RE.match(line)
        if em:
            plans[em.group(1)] = {
                "sku": em.group(2),
                "offer": em.group(3),
                "note": em.group(4).replace('\\"', '"'),
            }
    return plans


def escape_js_str(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def update_js_plans(js_text, new_entries):
    """Обновляет существующие или дописывает новые записи в блок var PLANS в frida.js.

    Сохраняет существующие комментарии и порядок строк, а новые планы добавляет
    в конец блока PLANS. Возвращает (новый_текст, added_ids, updated_ids).
    """
    m = PLANS_BLOCK_RE.search(js_text)
    if not m:
        raise ValueError("Не найден блок `var PLANS = { ... };` в frida.js")

    existing = parse_js_plans(js_text)
    body_lines = m.group(2).splitlines()
    updated_ids = []
    added_ids = []

    # 1. Обновляем существующие строки, если поменялся sku/offer/note (не затирая ручной note пустым).
    new_map = {e["id"]: e for e in new_entries}
    rebuilt = []
    for line in body_lines:
        em = ENTRY_RE.match(line)
        if not em:
            rebuilt.append(line)
            continue
        pid = em.group(1)
        if pid not in new_map:
            rebuilt.append(line)
            continue
        item = new_map[pid]
        cur = existing[pid]
        note = cur["note"] or item.get("note") or ""
        # Убираем пометку [кандидат], если оффер подтверждён живым сканом!
        if item.get("confirmed_live") and "[кандидат]" in note:
            note = note.replace("[кандидат]", "").strip()
        if (item["sku"], item["offer"], note) != (cur["sku"], cur["offer"], cur["note"]):
            comma = "," if line.rstrip().endswith(",") else ""
            rebuilt.append(
                f'  {pid}: {{ sku: "{escape_js_str(item["sku"])}", '
                f'offer: "{escape_js_str(item["offer"])}", '
                f'note: "{escape_js_str(note)}" }}{comma}'
            )
            updated_ids.append(pid)
        else:
            rebuilt.append(line)

    # 2. Добавляем новые записи в конец блока.
    to_append = [e for e in new_entries if e["id"] not in existing]
    if to_append:
        # Гарантируем запятую у последней существующей записи PLANS.
        for idx in range(len(rebuilt) - 1, -1, -1):
            if ENTRY_RE.match(rebuilt[idx]):
                if not rebuilt[idx].rstrip().endswith(","):
                    rebuilt[idx] = rebuilt[idx].rstrip() + ","
                break
        rebuilt.append("  // ---- Добавлено через sync_offers.py ----")
        for pos, item in enumerate(to_append):
            comma = "," if pos < len(to_append) - 1 else ""
            note = item.get("note") or format_auto_note(item["sku"], item["offer"])
            rebuilt.append(
                f'  {item["id"]}: {{ sku: "{escape_js_str(item["sku"])}", '
                f'offer: "{escape_js_str(item["offer"])}", '
                f'note: "{escape_js_str(note)}" }}{comma}'
            )
            added_ids.append(item["id"])

    new_body = "\n".join(rebuilt)
    updated_js = js_text[: m.start(2)] + new_body + js_text[m.end(2) :]
    return updated_js, added_ids, updated_ids


def validate_entry(plan_id, sku, offer):
    if not PLAN_ID_RE.match(plan_id):
        raise ValueError(f"Некорректный идентификатор плана: {plan_id!r}")
    if not SKU_RE.match(sku):
        raise ValueError(f"Некорректный SKU для {plan_id}: {sku!r}")
    if not OFFER_RE.match(offer):
        raise ValueError(f"Некорректный offer для {plan_id}: {offer!r}")


def read_offers_tsv(path):
    """Читает offers.txt (key\\tsku\\toffer[\\tnote])."""
    entries = []
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 2:
            raise ValueError(f"{path}:{lineno}: ожидалось минимум 2 колонки через TAB")
        pid = parts[0].strip()
        sku = parts[1].strip()
        offer = parts[2].strip() if len(parts) >= 3 else ""
        note = parts[3].strip() if len(parts) >= 4 else ""
        validate_entry(pid, sku, offer)
        entries.append({"id": pid, "sku": sku, "offer": offer, "note": note, "confirmed_live": False})
    return entries


def read_scan_log(path, only_live=True):
    """Читает лог scan-offers.sh (key\\tsku\\toffer\\tstatus\\tpriceMicros\\tperiod)."""
    entries = []
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 4:
            continue
        pid, sku, offer, status = (p.strip() for p in parts[:4])
        price = parts[4].strip() if len(parts) >= 5 else ""
        period = parts[5].strip() if len(parts) >= 6 else ""
        if only_live and status != "live":
            continue
        validate_entry(pid, sku, offer)
        entries.append({
            "id": pid,
            "sku": sku,
            "offer": offer,
            "note": format_auto_note(sku, offer, price, period) if (price or period) else "",
            "confirmed_live": (status == "live"),
        })
    return entries


def export_offers_tsv(plans):
    lines = [f"{pid}\t{spec['sku']}\t{spec['offer']}" for pid, spec in plans.items()]
    return "\n".join(lines) + "\n"


def check_sync(js_path, offers_path):
    plans = parse_js_plans(Path(js_path).read_text(encoding="utf-8"))
    offers = read_offers_tsv(offers_path)
    offer_map = {e["id"]: (e["sku"], e["offer"]) for e in offers}
    plan_map = {pid: (spec["sku"], spec["offer"]) for pid, spec in plans.items()}
    only_js = [k for k in plan_map if k not in offer_map]
    only_txt = [k for k in offer_map if k not in plan_map]
    diff_vals = [
        k for k in plan_map
        if k in offer_map and plan_map[k] != offer_map[k]
    ]
    return len(plans), only_js, only_txt, diff_vals


def parse_args():
    p = argparse.ArgumentParser(
        description="Синхронизация каталога тарифов между scan-results / offers.txt и frida.js."
    )
    p.add_argument("--js", default=str(DEFAULT_JS), help="Путь к frida.js")
    p.add_argument("--offers", default=str(DEFAULT_OFFERS), help="Путь к offers.txt")
    p.add_argument("--from-scan", default="", help="Импортировать живые офферы (status=live) из scan-results-*.log в frida.js и offers.txt")
    p.add_argument("--from-offers", default="", help="Импортировать записи из offers.txt (или другого TSV) в frida.js")
    p.add_argument("--include-missing", action="store_true", help="При --from-scan переносить не только live, но и все валидные строки")
    p.add_argument("--export-offers", action="store_true", help="Перезаписать offers.txt из таблицы PLANS в frida.js")
    p.add_argument("--check", action="store_true", help="Проверить синхронность frida.js и offers.txt (код 1 при расхождении)")
    p.add_argument("--dry-run", action="store_true", help="Показать изменения без записи файлов")
    return p.parse_args()


def main():
    args = parse_args()
    js_path = Path(args.js)
    offers_path = Path(args.offers)

    if args.check:
        total, only_js, only_txt, diff_vals = check_sync(js_path, offers_path)
        if not (only_js or only_txt or diff_vals):
            print(f"[+] Каталоги синхронны: {total} тарифов в frida.js и offers.txt")
            return 0
        print(f"[x] Обнаружены расхождения: только в frida.js={only_js}, только в offers.txt={only_txt}, отличаются={diff_vals}")
        return 1

    js_text = js_path.read_text(encoding="utf-8")

    if args.from_scan or args.from_offers:
        entries = (
            read_scan_log(args.from_scan, only_live=(not args.include_missing))
            if args.from_scan
            else read_offers_tsv(args.from_offers)
        )
        updated_js, added, updated = update_js_plans(js_text, entries)
        merged_plans = parse_js_plans(updated_js)
        new_offers_txt = export_offers_tsv(merged_plans)
        if args.dry_run:
            print(f"[dry-run] Добавлено бы в frida.js: {len(added)} ({', '.join(added) or 'нет'})")
            print(f"[dry-run] Обновлено бы в frida.js: {len(updated)} ({', '.join(updated) or 'нет'})")
            return 0
        js_path.write_text(updated_js, encoding="utf-8")
        offers_path.write_text(new_offers_txt, encoding="utf-8")
        print(f"[+] Синхронизировано: добавлено={len(added)}, обновлено={len(updated)}, всего планов={len(merged_plans)}")
        return 0

    if args.export_offers:
        plans = parse_js_plans(js_text)
        out = export_offers_tsv(plans)
        if args.dry_run:
            print(f"[dry-run] Выгружено бы {len(plans)} записей в {offers_path}")
            return 0
        offers_path.write_text(out, encoding="utf-8")
        print(f"[+] Выгружено {len(plans)} записей в {offers_path}")
        return 0

    print("Укажите действие: --check, --from-scan <файл>, --from-offers <файл> или --export-offers (см. --help)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
