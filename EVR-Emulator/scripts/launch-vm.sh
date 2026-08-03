#!/bin/sh
# EVR Emulator - lanza la VM Android en QEMU (Linux / macOS).
#
# Equivalente de launch-vm.ps1 con la aceleracion propia de cada host:
#   Linux -> KVM   ·   macOS -> HVF   (en Windows usa launch-vm.ps1 -> WHPX)
#
#   --install            arranca desde el ISO para instalar Android en la base
#   --iso <ruta>         ISO de BlissOS / Android-x86 (necesario con --install)
#   --ram <MB>           memoria de la VM (por defecto 4096)
#   --cores <n>          vCPUs (por defecto 4)
#   --adb-port <puerto>  puerto del host reenviado al 5555 del guest (4444)
#   --disk-size <GB>     tamano de la imagen base al crearla (32)
#   --no-gpu             desactiva virtio-gpu con virgl
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")

ISO=""
BASE_DISK="$ROOT/images/base.qcow2"
DATA_DISK="$ROOT/images/data.qcow2"
RAM=4096
CORES=4
ADB_PORT=4444
DISK_SIZE=32
GPU=1
INSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --install|-Install)   INSTALL=1 ;;
        --iso|-Iso)           ISO="${2:?--iso necesita una ruta}"; shift ;;
        --ram|-Ram)           RAM="${2:?}"; shift ;;
        --cores|-Cores)       CORES="${2:?}"; shift ;;
        --adb-port)           ADB_PORT="${2:?}"; shift ;;
        --disk-size)          DISK_SIZE="${2:?}"; shift ;;
        --no-gpu)             GPU=0 ;;
        -h|--help)            sed -n '2,15p' "$0"; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v qemu-system-x86_64 >/dev/null 2>&1 || {
    echo 'qemu-system-x86_64 no encontrado. Instala QEMU:' >&2
    echo '  Debian/Ubuntu: sudo apt install qemu-system-x86 qemu-utils' >&2
    echo '  macOS:         brew install qemu' >&2
    exit 1
}
mkdir -p "$ROOT/images"

# --- Aceleracion disponible en este host -----------------------------------
ACCEL=tcg
case "$(uname -s)" in
    Linux)  [ -w /dev/kvm ] && ACCEL=kvm ;;
    Darwin) ACCEL=hvf ;;
esac
[ "$ACCEL" = tcg ] && echo 'AVISO: sin KVM/HVF; la VM ira por emulacion pura (muy lenta).' >&2

# --- Preparar discos -------------------------------------------------------
if [ "$INSTALL" -eq 1 ]; then
    [ -n "$ISO" ] && [ -f "$ISO" ] || { echo 'Con --install debes pasar un --iso valido.' >&2; exit 1; }
    if [ ! -f "$BASE_DISK" ]; then
        echo "Creando imagen base ${DISK_SIZE} GB -> $BASE_DISK"
        qemu-img create -f qcow2 "$BASE_DISK" "${DISK_SIZE}G" >/dev/null
    fi
else
    [ -f "$BASE_DISK" ] || { echo "No existe la imagen base ($BASE_DISK). Corre primero con --install --iso <iso>." >&2; exit 1; }
    if [ ! -f "$DATA_DISK" ]; then
        echo "Creando overlay de escritura sobre la base -> $DATA_DISK"
        qemu-img create -f qcow2 -b "$BASE_DISK" -F qcow2 "$DATA_DISK" >/dev/null
    fi
fi

# --- Argumentos de QEMU ----------------------------------------------------
set -- \
    -machine "q35,accel=$ACCEL" \
    -cpu max \
    -m "$RAM" \
    -smp "$CORES" \
    -device virtio-net-pci,netdev=net0 \
    -netdev "user,id=net0,hostfwd=tcp::${ADB_PORT}-:5555" \
    -device usb-ehci,id=usb \
    -device usb-tablet \
    -rtc base=localtime \
    -boot menu=on

if [ "$GPU" -eq 1 ]; then
    set -- "$@" -device virtio-vga-gl -display "gtk,gl=on"
else
    set -- "$@" -device virtio-vga -display "gtk,gl=off"
fi

if [ "$INSTALL" -eq 1 ]; then
    set -- "$@" -drive "file=$BASE_DISK,if=virtio,format=qcow2" -cdrom "$ISO"
    echo 'MODO INSTALACION: en el menu GRUB elige "Install Bliss-OS to harddisk".'
else
    set -- "$@" -drive "file=$DATA_DISK,if=virtio,format=qcow2"
fi

echo "Lanzando VM Android (RAM ${RAM}MB, ${CORES} vCPU, accel=$ACCEL, GPU=$GPU)..."
echo "ADB por TCP: host 127.0.0.1:${ADB_PORT} -> guest :5555"
exec qemu-system-x86_64 "$@"
