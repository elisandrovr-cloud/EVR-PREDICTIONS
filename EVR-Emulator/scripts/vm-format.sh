#!/bin/sh
# EVR Emulator - "formatea" la VM Android (Linux / macOS).
#
# Equivalente POSIX de vm-format.ps1. Acepta los mismos modificadores para que
# el middleware pueda invocar uno u otro sin saber en que host corre.
#
#   -Force              no preguntar
#   -Snapshot <nombre>  revertir a un snapshot interno qcow2
#   -Fresh              recrear un disco vacio (reinstalar Android desde cero)
#   -SizeGB <n>         tamano del disco en modo -Fresh (por defecto 32)
#   -BaseDisk <ruta>    imagen base   (por defecto images/base.qcow2)
#   -DataDisk <ruta>    overlay       (por defecto images/data.qcow2)
#
# El patron base inmutable + overlay hace que "formatear" sea recrear el
# overlay desde la base: segundos en lugar de una reinstalacion.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")

BASE_DISK="$ROOT/images/base.qcow2"
DATA_DISK="$ROOT/images/data.qcow2"
SNAPSHOT=""
FRESH=0
SIZE_GB=32
FORCE=0

while [ $# -gt 0 ]; do
    case "$1" in
        -Force|--force)       FORCE=1 ;;
        -Fresh|--fresh)       FRESH=1 ;;
        -Snapshot|--snapshot) SNAPSHOT="${2:?-Snapshot necesita un nombre}"; shift ;;
        -SizeGB|--size-gb)    SIZE_GB="${2:?-SizeGB necesita un numero}"; shift ;;
        -BaseDisk|--base)     BASE_DISK="${2:?-BaseDisk necesita una ruta}"; shift ;;
        -DataDisk|--data)     DATA_DISK="${2:?-DataDisk necesita una ruta}"; shift ;;
        -h|--help)            sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v qemu-img >/dev/null 2>&1 || {
    echo "qemu-img no encontrado. Instala QEMU:" >&2
    echo "  Debian/Ubuntu: sudo apt install qemu-utils qemu-system-x86" >&2
    echo "  macOS:         brew install qemu" >&2
    exit 1
}

# Guard: la VM debe estar apagada para no corromper el qcow2.
if pgrep -f 'qemu-system-x86_64' >/dev/null 2>&1; then
    echo "La VM esta en ejecucion. Apaga QEMU antes de formatear." >&2
    exit 1
fi

confirm() {
    [ "$FORCE" -eq 1 ] && return 0
    printf '%s [y/N] ' "$1"
    read -r answer
    case "$answer" in y|Y|s|S|yes|si) return 0 ;; *) return 1 ;; esac
}

# --- Modo SNAPSHOT ---------------------------------------------------------
if [ -n "$SNAPSHOT" ]; then
    [ -f "$DATA_DISK" ] || { echo "No existe $DATA_DISK." >&2; exit 1; }
    confirm "¿Revertir '$DATA_DISK' al snapshot '$SNAPSHOT'?" || { echo 'Cancelado.'; exit 0; }
    qemu-img snapshot -a "$SNAPSHOT" "$DATA_DISK"
    echo "OK: revertido al snapshot '$SNAPSHOT'."
    exit 0
fi

# --- Modo FRESH ------------------------------------------------------------
if [ "$FRESH" -eq 1 ]; then
    confirm "¿Recrear disco VACIO (${SIZE_GB} GB) en '$DATA_DISK'? Se borra TODO." || { echo 'Cancelado.'; exit 0; }
    rm -f "$DATA_DISK"
    qemu-img create -f qcow2 "$DATA_DISK" "${SIZE_GB}G" >/dev/null
    echo "OK: disco vacio recreado. Reinstala Android con launch-vm.sh --install."
    exit 0
fi

# --- Modo OVERLAY (por defecto) -------------------------------------------
[ -f "$BASE_DISK" ] || {
    echo "No existe la imagen base ($BASE_DISK). Sin base no hay a que 'formatear'." >&2
    echo "Usa -Fresh para empezar de cero." >&2
    exit 1
}
confirm "¿Formatear: borrar el overlay '$DATA_DISK' y recrearlo desde la base?" || { echo 'Cancelado.'; exit 0; }
rm -f "$DATA_DISK"
qemu-img create -f qcow2 -b "$BASE_DISK" -F qcow2 "$DATA_DISK" >/dev/null
echo 'OK: emulador formateado al estado base (Android limpio).'
qemu-img info "$DATA_DISK"
