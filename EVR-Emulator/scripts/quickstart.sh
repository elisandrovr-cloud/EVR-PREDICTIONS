#!/bin/sh
# EVR Emulator - arranque guiado en un comando (Linux / macOS).
#
# Equivalente de quickstart.ps1:
#   1) Preflight (virtualizacion, RAM, Node.js).
#   2) Binarios (adb).
#   3) Dependencias del middleware.
#   4) Si hay ISO y no hay imagen base: arranca QEMU para INSTALAR Android.
#   5) Si ya hay base: arranca la VM y la consola web en http://127.0.0.1:5555
#
#   --no-vm      solo la consola web (util en un host sin GUI o sin QEMU)
#   --iso <ruta> ISO de BlissOS con GApps (por defecto el primero de images/)
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")

ISO=""
START_VM=1
while [ $# -gt 0 ]; do
    case "$1" in
        --no-vm)   START_VM=0 ;;
        --iso)     ISO="${2:?}"; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; exit 2 ;;
    esac
    shift
done

say() { printf '%s\n' "$*"; }
ok()   { printf '[  OK  ] %s\n' "$*"; }
warn() { printf '[ WARN ] %s\n' "$*"; }

say '== Paso 1/5: preflight =='
case "$(uname -s)" in
    Linux)
        if [ -e /dev/kvm ]; then
            [ -w /dev/kvm ] && ok 'KVM disponible y accesible' \
                            || warn 'KVM existe pero sin permisos (añadete al grupo kvm: sudo usermod -aG kvm $USER)'
        else
            warn 'sin /dev/kvm: la VM iria por emulacion pura (muy lenta)'
        fi
        RAM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
        RAM_GB=$((RAM_KB / 1024 / 1024))
        [ "$RAM_GB" -ge 8 ] && ok "RAM total: ${RAM_GB} GB" || warn "RAM total: ${RAM_GB} GB (se recomiendan 8 GB)"
        ;;
    Darwin)
        ok 'macOS: aceleracion HVF disponible'
        RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
        [ "$RAM_GB" -ge 8 ] && ok "RAM total: ${RAM_GB} GB" || warn "RAM total: ${RAM_GB} GB (se recomiendan 8 GB)"
        ;;
esac
if command -v node >/dev/null 2>&1; then
    ok "Node.js $(node --version)"
else
    warn 'Node.js no instalado: la consola web no arrancara (https://nodejs.org)'
fi

say ''
say '== Paso 2/5: binarios (adb) =='
sh "$SCRIPT_DIR/fetch-binaries.sh" || warn 'fetch-binaries fallo; se seguira con el adb del sistema si lo hay'

say ''
say '== Paso 3/5: dependencias del middleware =='
if [ ! -d "$ROOT/middleware/node_modules" ] && command -v npm >/dev/null 2>&1; then
    (cd "$ROOT/middleware" && npm install --no-audit --no-fund)
else
    ok 'ya instaladas'
fi
[ -f "$ROOT/middleware/.env" ] || cp "$ROOT/middleware/.env.example" "$ROOT/middleware/.env"

say ''
say '== Paso 4/5: imagen de Android =='
BASE="$ROOT/images/base.qcow2"
if [ -z "$ISO" ]; then
    ISO=$(find "$ROOT/images" -maxdepth 1 -name '*.iso' 2>/dev/null | head -n 1 || true)
fi
if [ ! -f "$BASE" ] && [ -z "$ISO" ]; then
    warn 'No hay imagen base ni ISO en images/.'
    say '  Descarga una build de BlissOS que INCLUYA GApps (Play Store integrado):'
    say '    https://blissos.org  ->  build "GApps", Android 13/14, x86_64'
    say '  Guardala en images/ y reejecuta este script.'
    say '  Mientras tanto puedes usar la consola con un AVD o un telefono por USB.'
    START_VM=0
elif [ ! -f "$BASE" ]; then
    say "Instalando Android en la imagen base desde: $ISO"
    say '  En el menu GRUB: "Installation - Install Bliss-OS to harddisk".'
    say '  Al terminar, cierra QEMU y reejecuta este script.'
    exec sh "$SCRIPT_DIR/launch-vm.sh" --install --iso "$ISO"
else
    ok "imagen base lista: $BASE"
fi

say ''
say '== Paso 5/5: consola web + VM =='
if [ "$START_VM" -eq 1 ] && command -v qemu-system-x86_64 >/dev/null 2>&1; then
    sh "$SCRIPT_DIR/launch-vm.sh" &
    say "VM lanzada (PID $!)"
    sleep 2
fi

say 'Consola web: http://127.0.0.1:5555   (Ctrl+C para parar)'
cd "$ROOT/middleware"
exec npm start
