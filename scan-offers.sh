#!/usr/bin/env bash
# scan-offers.sh — прогнать все офферы из offers.txt по одному, только для анализа.
#
# Что делает: для каждой строки (ключ, sku, offer) из offers.txt подставляет
# sku/offer в probe-single.js и цепляется Frida к Google One. Скрипт внутри
# приложения делает ТОЛЬКО queryProductDetailsAsync — читает, какие офферы
# Play вернул для этого аккаунта. launchBillingFlow здесь НЕТ: экран
# оформления не открывается, ничего не покупается, триал не тратится.
#
# НЕ путать с main.py --plan: тот как раз открывает экран оформления
# (launchBillingFlow), и гонять его в цикле по 109 офферам нельзя —
# каждый вызов может сжечь право на триал, даже без нажатия «Подписаться».
#
# Прогресс — в терминал: [i/N] (процент) ключ sku offer -> live/missing/error.
# Итог — в scan-results-YYYYMMDD-HHMMSS.log рядом со скриптом, по строке
# на оффер: ключ, sku, offer, статус, цена первого периода, период.
#
# Требования: эмулятор/телефон по adb, frida-server запущен от root
# (см. README, раздел про su), Google One установлен, на устройстве
# выполнен вход в аккаунт Google. frida CLI — на компьютере.
#
# Запуск:
#   ./scan-offers.sh                          # всё, задержка 5 секунд
#   ./scan-offers.sh --serial emulator-5554   # явно выбрать устройство
#   ./scan-offers.sh --delay 10               # другая задержка между офферами
#   ./scan-offers.sh --start 40               # продолжить с 40-го оффера
#   ./scan-offers.sh --dry-run                # только показать, что будет сделано
#
set -u
cd "$(dirname "$0")"

PKG="com.google.android.apps.subscriptions.red"
OFFERS_FILE="offers.txt"
TEMPLATE="probe-single.js"
DELAY=5
TIMEOUT=25
START=1
SERIAL="${ANDROID_SERIAL:-emulator-5554}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --serial)  SERIAL="$2"; shift 2 ;;
    --offers)  OFFERS_FILE="$2"; shift 2 ;;
    --delay)   DELAY="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --start)   START="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Неизвестный аргумент: $1 (см. --help)" >&2; exit 2 ;;
  esac
done

[ -f "$OFFERS_FILE" ] || { echo "Нет файла $OFFERS_FILE" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "Нет файла $TEMPLATE" >&2; exit 1; }
TOTAL=$(grep -c . "$OFFERS_FILE")
[ "$TOTAL" -gt 0 ] || { echo "Файл $OFFERS_FILE пуст" >&2; exit 1; }
echo "Офферов в списке: $TOTAL, задержка ${DELAY}с, устройство $SERIAL"

if [ "$DRY_RUN" -eq 1 ]; then
  i=0
  while IFS="$(printf '\t')" read -r key sku offer || [ -n "$key" ]; do
    i=$((i + 1))
    [ "$i" -lt "$START" ] && continue
    printf '[%s/%s] %s  sku=%s offer=%s\n' "$i" "$TOTAL" "$key" "$sku" "${offer:-<базовый>}"
  done < "$OFFERS_FILE"
  echo "Dry-run: ничего не запускалось."
  exit 0
fi

# --- проверки окружения (для dry-run не нужны) ---
command -v adb >/dev/null || { echo "Нет adb в PATH" >&2; exit 1; }
command -v frida >/dev/null || { echo "Нет frida CLI в PATH (pip install frida-tools)" >&2; exit 1; }
adb -s "$SERIAL" shell echo ok >/dev/null 2>&1 || { echo "Устройство $SERIAL не отвечает по adb" >&2; exit 1; }

G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
if [ -z "$G1_PID" ]; then
  echo "Google One не запущен, запускаю..."
  adb -s "$SERIAL" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  sleep 3
  G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
  [ -n "$G1_PID" ] || { echo "Не удалось запустить Google One" >&2; exit 1; }
fi
echo "Google One pid=$G1_PID"

if [ -z "$(adb -s "$SERIAL" shell pidof frida-server 2>/dev/null | tr -d '\r')" ]; then
  echo "ВНИМАНИЕ: frida-server не запущен. Запусти его от root (см. README, раздел про su), иначе attach не пройдёт." >&2
fi

TS=$(date +%Y%m%d-%H%M%S)
RESULTS="scan-results-$TS.log"
TMPDIR_SCAN=$(mktemp -d)
FRIDA_PID=""
cleanup() {
  [ -n "$FRIDA_PID" ] && kill "$FRIDA_PID" 2>/dev/null
  rm -rf "$TMPDIR_SCAN"
}
trap cleanup EXIT INT TERM

echo "# scan $TS serial=$SERIAL delay=${DELAY}s total=$TOTAL" > "$RESULTS"
echo "Результаты пишутся в $RESULTS"
echo

LIVE=0; MISSING=0; ERRORS=0
i=0
while IFS="$(printf '\t')" read -r key sku offer || [ -n "$key" ]; do
  i=$((i + 1))
  [ "$i" -lt "$START" ] && continue
  pct=$((i * 100 / TOTAL))
  offer_disp="${offer:-<базовый>}"

  # Google One мог перезапуститься — pid перепроверяем каждый раз.
  G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
  if [ -z "$G1_PID" ]; then
    echo "[$i/$TOTAL] ($pct%) $key — Google One упал, перезапускаю..."
    adb -s "$SERIAL" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    sleep 3
    G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
    [ -n "$G1_PID" ] || { echo "[$i/$TOTAL] $key -> error (приложение не запустилось)"; ERRORS=$((ERRORS + 1)); continue; }
  fi

  # Подстановка sku/offer в шаблон probe-single.js.
  probe_js="$TMPDIR_SCAN/probe.js"
  sed -e "s/__SKU__/$sku/g" -e "s/__OFFER__/$offer/g" "$TEMPLATE" > "$probe_js"
  out_log="$TMPDIR_SCAN/out.log"
  : > "$out_log"

  frida -U -p "$G1_PID" -l "$probe_js" --no-pause > "$out_log" 2>&1 &
  FRIDA_PID=$!
  # Ждём строку RESULT (до TIMEOUT секунд), потом убиваем frida.
  waited=0
  while ! grep -q '\[probe\] RESULT' "$out_log" 2>/dev/null; do
    kill -0 "$FRIDA_PID" 2>/dev/null || break
    [ "$waited" -ge $((TIMEOUT * 2)) ] && break
    sleep 0.5
    waited=$((waited + 1))
  done
  kill "$FRIDA_PID" 2>/dev/null
  wait "$FRIDA_PID" 2>/dev/null
  FRIDA_PID=""

  result=$(grep '\[probe\] RESULT' "$out_log" 2>/dev/null | tail -1)
  if [ -z "$result" ]; then
    status="error"; price=""; period=""
    echo "[$i/$TOTAL] ($pct%) $key  sku=$sku offer=$offer_disp -> error (нет ответа от probe, смотри $out_log)"
  else
    status=$(echo "$result" | sed -n 's/.*status=\([^ ]*\).*/\1/p')
    price=$(echo "$result" | sed -n 's/.*priceMicros=\([^ ]*\).*/\1/p')
    period=$(echo "$result" | sed -n 's/.*period=\([^ ]*\).*/\1/p')
    case "$status" in
      live)    LIVE=$((LIVE + 1)) ;;
      missing) MISSING=$((MISSING + 1)) ;;
      *)       ERRORS=$((ERRORS + 1)) ;;
    esac
    echo "[$i/$TOTAL] ($pct%) $key  sku=$sku offer=$offer_disp -> $status${price:+ price=${price}micros}${period:+ period=$period}"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$sku" "$offer" "$status" "$price" "$period" >> "$RESULTS"

  # Задержка 5 секунд между офферами, после последнего — не нужна.
  if [ "$i" -lt "$TOTAL" ]; then
    sleep "$DELAY"
  fi
done < "$OFFERS_FILE"

echo
echo "Готово: $TOTAL офферов. live=$LIVE missing=$MISSING error=$ERRORS"
echo "Итог в $RESULTS"
echo "Живые офферы:"
grep $'\tlive\t' "$RESULTS" || true
