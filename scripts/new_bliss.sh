#!/usr/bin/env bash
# new_bliss.sh — создание тонкого клона BlissOS из эталона с полной уникализацией ID устройства.
#
# Что уникализируется для каждого нового клона:
#   1. KVM UUID (<uuid>) и MAC-адрес (через virt-clone)
#   2. SMBIOS system.serial и system.uuid (/sys/class/dmi/id/product_serial, product_uuid)
#   3. Settings.Secure android_id (16 hex)
#   4. Android 8+ SSAID мастер-ключ (/data/system/users/0/settings_ssaid.xml) — чтобы Play Store,
#      GMS и Google One получали уникальные per-app ANDROID_ID на каждом клоне
#   5. Очистка кэша и старых GSF ID / Advertising ID (gsf, gms, vending, subscriptions.red, chrome)
#      с последующей быстрой перезагрузкой гостевой ОС.

set -euo pipefail

TEMPLATE="blisstemplate"
TEMPLATE_DISK="/var/lib/libvirt/images/blisstemplate.qcow2"
IMAGES_DIR="/var/lib/libvirt/images"
NETWORK="default"

if [[ $EUID -ne 0 ]]; then
  echo "Запустите через sudo: sudo $0 <имя_клона>"
  exit 1
fi

VM_NAME="${1:-}"
if [[ -z "$VM_NAME" ]]; then
  echo "Использование: sudo $0 <имя_клона>"
  echo "Пример:        sudo $0 bliss-02"
  exit 1
fi

if [[ ! "$VM_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || [[ "$VM_NAME" == "$TEMPLATE" ]]; then
  echo "Ошибка: недопустимое имя ВМ '$VM_NAME'."
  exit 1
fi

NEW_DISK="${IMAGES_DIR}/${VM_NAME}.qcow2"

if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
  echo "Ошибка: ВМ '$VM_NAME' уже существует."
  exit 1
fi

if [[ -e "$NEW_DISK" ]]; then
  echo "Ошибка: диск '$NEW_DISK' уже существует."
  exit 1
fi

if [[ ! -f "$TEMPLATE_DISK" ]]; then
  echo "Ошибка: не найден диск шаблона '$TEMPLATE_DISK'."
  exit 1
fi

TEMPLATE_STATE=$(virsh domstate "$TEMPLATE" 2>/dev/null | tr -d '[:space:]')
if [[ "$TEMPLATE_STATE" != "shutoff" ]]; then
  echo "Ошибка: шаблон '$TEMPLATE' должен быть выключен (сейчас: $TEMPLATE_STATE)."
  exit 1
fi

# VNC по стандарту поддерживает пароль максимум 8 символов
VNC_PASS=$(head -c 256 /dev/urandom | tr -dc 'A-Za-z0-9' | cut -c1-8)
NEW_ANDROID_ID=$(head -c 64 /dev/urandom | sha256sum | cut -c1-16)
HW_SERIAL="BLISS$(head -c 64 /dev/urandom | tr -dc 'A-Z0-9' | cut -c1-11)"

echo "[1/5] Создаю тонкий диск $NEW_DISK..."
qemu-img create -q -f qcow2 -F qcow2 -b "$TEMPLATE_DISK" "$NEW_DISK"

echo "[2/5] Клонирую конфигурацию из $TEMPLATE -> $VM_NAME..."
virt-clone \
  --original "$TEMPLATE" \
  --name "$VM_NAME" \
  --file "$NEW_DISK" \
  --preserve-data >/dev/null

VM_UUID=$(virsh domuuid "$VM_NAME" | tr -d '[:space:]')

echo "[3/5] Настраиваю VNC (autoport + пароль) и уникальный SMBIOS serial ($HW_SERIAL)..."
virt-xml "$VM_NAME" --edit --graphics "vnc,port=-1,listen=0.0.0.0,password=${VNC_PASS}" >/dev/null
virt-xml "$VM_NAME" --edit \
  --sysinfo "type=smbios,system.uuid=${VM_UUID},system.serial=${HW_SERIAL}" \
  --os smbios.mode=sysinfo >/dev/null 2>&1 || true

echo "[4/5] Запускаю $VM_NAME..."
virsh start "$VM_NAME" >/dev/null

VM_MAC=$(virsh domiflist "$VM_NAME" | awk '$2=="network" || $2=="bridge" {print $5; exit}')
VM_IP=""
echo "Ожидаю IP по DHCP (MAC: $VM_MAC)..."
for _ in $(seq 1 35); do
  VM_IP=$(virsh net-dhcp-leases "$NETWORK" | awk -v mac="$VM_MAC" 'tolower($3) == tolower(mac) {sub(/\/.*/, "", $5); print $5; exit}')
  if [[ -n "$VM_IP" ]]; then
    break
  fi
  sleep 2
done

wait_for_android_boot() {
  local ip="$1"
  local max_tries="${2:-45}"
  local boot=""
  for _ in $(seq 1 "$max_tries"); do
    adb connect "${ip}:5555" >/dev/null 2>&1 || true
    boot=$(adb -s "${ip}:5555" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r[:space:]' || true)
    if [[ "$boot" == "1" ]]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

UNIQUE_STATUS="пропущено (нет IP или adb)"
if [[ -n "$VM_IP" ]] && command -v adb >/dev/null 2>&1; then
  echo "[5/5] Ожидаю загрузку Android (${VM_IP}:5555) для генерации уникальных ID..."
  if wait_for_android_boot "$VM_IP" 45; then
    adb -s "${VM_IP}:5555" root >/dev/null 2>&1 || true
    sleep 2
    adb connect "${VM_IP}:5555" >/dev/null 2>&1 || true

    echo "      Сбрасываю старые GSF/GMS/Play/SSAID идентификаторы шаблона..."
    adb -s "${VM_IP}:5555" shell "
      pm clear com.google.android.gsf >/dev/null 2>&1 || true
      pm clear com.google.android.gms >/dev/null 2>&1 || true
      pm clear com.android.vending >/dev/null 2>&1 || true
      pm clear com.google.android.apps.subscriptions.red >/dev/null 2>&1 || true
      pm clear com.android.chrome >/dev/null 2>&1 || true
      settings put secure android_id ${NEW_ANDROID_ID}
      sleep 1
      stop
      rm -f /data/system/users/0/settings_ssaid.xml /data/system/users/0/settings_ssaid.xml.fallback
      rm -rf /data/vendor/mediadrm/* /data/mediadrm/* 2>/dev/null || true
      sync
      reboot
    " >/dev/null 2>&1 || true

    adb disconnect "${VM_IP}:5555" >/dev/null 2>&1 || true
    echo "      Ожидаю повторную загрузку $VM_NAME после обновления SSAID..."
    sleep 6
    if wait_for_android_boot "$VM_IP" 45; then
      # Пробуждаем GMS/Play Store на пару секунд, чтобы создалась свежая таблица SSAID
      adb -s "${VM_IP}:5555" shell "monkey -p com.android.vending -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 2; am force-stop com.android.vending >/dev/null 2>&1" || true
      GOT_AID=$(adb -s "${VM_IP}:5555" shell settings get secure android_id 2>/dev/null | tr -d '\r[:space:]' || true)
      UNIQUE_STATUS="OK (android_id=${GOT_AID}, serial=${HW_SERIAL})"
    else
      UNIQUE_STATUS="ВНИМАНИЕ: клон перезагружается дольше обычного, проверьте через 15 сек"
    fi
    adb disconnect "${VM_IP}:5555" >/dev/null 2>&1 || true
  else
    UNIQUE_STATUS="ВНИМАНИЕ: ADB не ответил за 90 сек"
  fi
fi

VNC_DISP=$(virsh vncdisplay "$VM_NAME" | awk -F: '{print $NF}' | tr -d '[:space:]')
VNC_PORT=$((5900 + VNC_DISP))
PUB_IP=$(curl -s --max-time 2 https://ifconfig.me || echo "<external_ip>")

echo ""
echo "=========================================="
echo " ВМ запущена:  $VM_NAME"
echo "------------------------------------------"
echo " VNC хост:     ${PUB_IP}::${VNC_PORT}"
echo " VNC порт:     ${VNC_PORT}"
echo " VNC пароль:   ${VNC_PASS}"
echo " Уникализация: ${UNIQUE_STATUS}"
echo "------------------------------------------"
if [[ -n "$VM_IP" ]]; then
  echo " IP ВМ (ADB):  ${VM_IP}:5555"
  echo " На рабочей станции поднимите туннель: python tunnel.py"
else
  echo " IP ВМ (ADB):  пока не выдан (проверьте через 15 сек: sudo virsh net-dhcp-leases $NETWORK)"
fi
echo "=========================================="
echo " Удалить клон после работы:"
echo "   sudo virsh destroy $VM_NAME ; sudo virsh undefine $VM_NAME --remove-all-storage"
