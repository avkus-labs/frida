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
# Лог неудачного оффера сохраняется рядом: scan-fail-<ключ>.log.
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
#   ./scan-offers.sh --one lite_base          # один оффер, для отладки
#   ./scan-offers.sh --one lite_base --verbose  # один оффер + весь вывод frida
#   ./scan-offers.sh --dry-run                # только показать, что будет сделано
#
# Если первые офферы дают error — скрипт останавливается после 5 ошибок
# подряд и говорит, что проверить (см. --max-errors). Не надо ждать все 109.
#
set -u
cd "$(dirname "$0")"

PKG="com.google.android.apps.subscriptions.red"
OFFERS_FILE="offers.txt"
TEMPLATE="probe-single.js"
DELAY=5
TIMEOUT=25
START=1
MAX_ERRORS=5
ONLY=""
VERBOSE=0
SERIAL="${ANDROID_SERIAL:-emulator-5554}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --serial)  SERIAL="$2"; shift 2 ;;
    --offers)  OFFERS_FILE="$2"; shift 2 ;;
    --delay)   DELAY="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --start)   START="$2"; shift 2 ;;
    --max-errors) MAX_ERRORS="$2"; shift 2 ;;
    --one)     ONLY="$2"; shift 2 ;;
    --verbose) VERBOSE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,32p' "$0"; exit 0 ;;
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
    [ -n "$ONLY" ] && [ "$key" != "$ONLY" ] && continue
    printf '[%s/%s] %s  sku=%s offer=%s\n' "$i" "$TOTAL" "$key" "$sku" "${offer:-<базовый>}"
  done < "$OFFERS_FILE"
  echo "Dry-run: ничего не запускалось."
  exit 0
fi

# --- проверки окружения (для dry-run не нужны) ---
command -v adb >/dev/null || { echo "Нет adb в PATH" >&2; exit 1; }
command -v frida >/dev/null || { echo "Нет frida CLI в PATH (pip install frida-tools)" >&2; exit 1; }
adb -s "$SERIAL" shell echo ok >/dev/null 2>&1 || { echo "Устройство $SERIAL не отвечает по adb" >&2; exit 1; }

# frida-server: запущен ли и от root ли. Это главный затык: запущенный
# как shell сервер не даёт attach к Google One (PermissionDenied),
# а скрипт тогда получает error на каждом оффере без объяснения.
FRIDA_SRV_PID=$(adb -s "$SERIAL" shell pidof frida-server 2>/dev/null | tr -d '\r' | awk '{print $1}')
if [ -z "$FRIDA_SRV_PID" ]; then
  echo "ВНИМАНИЕ: frida-server не запущен. Запусти его от root (см. README, раздел про su), иначе attach не пройдёт." >&2
else
  FRIDA_SRV_USER=$(adb -s "$SERIAL" shell ps -A 2>/dev/null | grep '[f]rida-server' | awk '{print $1}' | head -1 | tr -d '\r')
  if [ "$FRIDA_SRV_USER" != "root" ]; then
    echo "ВНИМАНИЕ: frida-server запущен как '${FRIDA_SRV_USER:-?}', а не как root. Attach к Google One будет отклонён (PermissionDenied) — каждый оффер даст error." >&2
    echo "Перезапусти от root: adb -s $SERIAL shell su -c 'killall -9 frida-server'; adb -s $SERIAL shell su -c '/data/local/tmp/frida-server -D &'" >&2
  else
    echo "frida-server запущен от root, PID=$FRIDA_SRV_PID"
  fi
fi

# module_521.apk: без него probe не найдёт BillingClient (boot_err).
if ! adb -s "$SERIAL" shell ls /data/local/tmp/module_521.apk >/dev/null 2>&1; then
  echo "ВНИМАНИЕ: на устройстве нет /data/local/tmp/module_521.apk. probe не найдёт BillingClient. Запусти один раз main.py — он сам его докинет — или: adb -s $SERIAL push module_521.apk /data/local/tmp/ (файл распаковывается из module_b64.py)." >&2
fi

# Видит ли frida это устройство вообще.
if command -v frida-ls-devices >/dev/null 2>&1; then
  if ! frida-ls-devices 2>/dev/null | grep -Fq "$SERIAL"; then
    echo "ВНИМАНИЕ: frida-ls-devices не показывает $SERIAL. frida -D \"$SERIAL\" может не найти устройство." >&2
  fi
fi

# Версии frida CLI и frida-server должны совпадать. main.py сам следит
# за этим и заменяет сервер при несовпадении, а этот скрипт — нет:
# старый сервер + новый CLI дают молчаливый отказ attach, и каждый
# оффер уходит в error без единой строки в логе.
FRIDA_CLI_VER=$(frida --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
FRIDA_SRV_VER=$(adb -s "$SERIAL" shell /data/local/tmp/frida-server --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$FRIDA_CLI_VER" ] && [ -n "$FRIDA_SRV_VER" ] && [ "$FRIDA_CLI_VER" != "$FRIDA_SRV_VER" ]; then
  echo "ВНИМАНИЕ: версии не совпадают: frida CLI $FRIDA_CLI_VER, frida-server на устройстве $FRIDA_SRV_VER. Attach может молча не проходить." >&2
  echo "Запусти один раз main.py — он сам заменит сервер на совпадающий — и потом снова скан." >&2
elif [ -n "$FRIDA_CLI_VER" ]; then
  echo "frida CLI $FRIDA_CLI_VER, frida-server на устройстве ${FRIDA_SRV_VER:-не определился}"
fi

G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
if [ -z "$G1_PID" ]; then
  echo "Google One не запущен, запускаю..."
  adb -s "$SERIAL" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  sleep 3
  G1_PID=$(adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
  [ -n "$G1_PID" ] || { echo "Не удалось запустить Google One" >&2; exit 1; }
fi
echo "Google One pid=$G1_PID"

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

LIVE=0; MISSING=0; ERRORS=0; CONSEC_ERRORS=0
i=0
while IFS="$(printf '\t')" read -r key sku offer || [ -n "$key" ]; do
  i=$((i + 1))
  [ "$i" -lt "$START" ] && continue
  [ -n "$ONLY" ] && [ "$key" != "$ONLY" ] && continue
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

  # Валидация sku и offer перед подстановкой в JS-шаблон (защита от инъекции в sed/JS).
  if ! printf '%s' "$sku" | grep -Eq '^[A-Za-z0-9._-]+$' || ! printf '%s' "$offer" | grep -Eq '^[A-Za-z0-9._-]*$'; then
    echo "[$i/$TOTAL] ($pct%) $key  sku=$sku offer=$offer_disp -> error (недопустимые символы в sku/offer)" >&2
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$sku" "$offer" "error" "" "" >> "$RESULTS"
    ERRORS=$((ERRORS + 1))
    continue
  fi

  # Подстановка sku/offer в шаблон probe-single.js.
  probe_js="$TMPDIR_SCAN/probe.js"
  sed -e "s/__SKU__/$sku/g" -e "s/__OFFER__/$offer/g" "$TEMPLATE" > "$probe_js"
  out_log="$TMPDIR_SCAN/out.log"
  : > "$out_log"

  frida -D "$SERIAL" -p "$G1_PID" -l "$probe_js" --no-pause > "$out_log" 2>&1 &
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

  [ "$VERBOSE" -eq 1 ] && cat "$out_log"

  result=$(grep '\[probe\] RESULT' "$out_log" 2>/dev/null | tail -1)
  if [ -z "$result" ]; then
    status="error"; price=""; period=""
    fail_log="scan-fail-$key.log"
    cp "$out_log" "$fail_log" 2>/dev/null
    echo "[$i/$TOTAL] ($pct%) $key  sku=$sku offer=$offer_disp -> error (нет ответа от probe)"
    echo "  Полный вывод frida сохранён в $fail_log, последние строки:"
    tail -8 "$fail_log" 2>/dev/null | sed 's/^/    /'
  else
    status=$(echo "$result" | sed -n 's/.*status=\([^ ]*\).*/\1/p')
    code=$(echo "$result" | sed -n 's/.*code=\([^ ]*\).*/\1/p')
    price=$(echo "$result" | sed -n 's/.*priceMicros=\([^ ]*\).*/\1/p')
    period=$(echo "$result" | sed -n 's/.*period=\([^ ]*\).*/\1/p')
    case "$status" in
      live)    LIVE=$((LIVE + 1)) ;;
      missing) MISSING=$((MISSING + 1)) ;;
      *)       ERRORS=$((ERRORS + 1)) ;;
    esac
    echo "[$i/$TOTAL] ($pct%) $key  sku=$sku offer=$offer_disp -> $status${code:+ code=$code}${price:+ price=${price}micros}${period:+ period=$period}"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$sku" "$offer" "$status" "$price" "$period" >> "$RESULTS"

  if [ "$status" = "error" ]; then
    CONSEC_ERRORS=$((CONSEC_ERRORS + 1))
    if [ "$CONSEC_ERRORS" -ge "$MAX_ERRORS" ]; then
      echo
      echo "СТОП: $CONSEC_ERRORS ошибок подряд — дальше гонять бессмысленно, дело не в офферах, а в окружении."
      echo "Проверь по порядку: 1) frida-server от root (см. предупреждение выше), 2) module_521.apk на устройстве, 3) версии frida CLI и frida-server совпадают (frida --version; adb shell /data/local/tmp/frida-server --version)."
      echo "Для отладки одного оффера: ./scan-offers.sh --one lite_base --verbose"
      break
    fi
  else
    CONSEC_ERRORS=0
  fi

  # Задержка 5 секунд между офферами, после последнего — не нужна.
  # При --one оффер один, задержки нет.
  if [ -z "$ONLY" ] && [ "$i" -lt "$TOTAL" ]; then
    sleep "$DELAY"
  fi
done < "$OFFERS_FILE"

echo
echo "Готово: live=$LIVE missing=$MISSING error=$ERRORS"
echo "Итог в $RESULTS"
echo "Живые офферы:"
grep $'\tlive\t' "$RESULTS" || true
