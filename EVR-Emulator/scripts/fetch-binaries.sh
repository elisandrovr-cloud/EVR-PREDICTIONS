#!/bin/sh
# EVR Emulator - descarga los binarios portables (Linux / macOS).
#
# Equivalente de fetch-binaries.ps1:
#   - ADB    : platform-tools del canal oficial de Google.
#   - scrcpy : en Linux/macOS se instala por gestor de paquetes (los releases
#              de GitHub solo publican binarios listos para Windows), asi que
#              aqui solo se comprueba y se indica el comando.
#
#   --force   vuelve a descargar aunque ya exista
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
BIN_DIR="$ROOT/bin"
TMP_DIR="$ROOT/tmp"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

mkdir -p "$BIN_DIR" "$TMP_DIR"

case "$(uname -s)" in
    Linux)  PLATFORM=linux ;;
    Darwin) PLATFORM=darwin ;;
    *) echo "Sistema no soportado por este script: $(uname -s). En Windows usa fetch-binaries.ps1." >&2; exit 1 ;;
esac

fetch() {
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
    else echo 'Hace falta curl o wget.' >&2; exit 1
    fi
}

# --- 1. ADB / platform-tools ----------------------------------------------
echo 'ADB / platform-tools'
ADB_BIN="$BIN_DIR/platform-tools/adb"
if [ -x "$ADB_BIN" ] && [ "$FORCE" -eq 0 ]; then
    echo '  ya presente (usa --force para reinstalar)'
elif command -v adb >/dev/null 2>&1 && [ "$FORCE" -eq 0 ]; then
    echo "  se usara el adb del sistema: $(command -v adb)"
else
    command -v unzip >/dev/null 2>&1 || { echo '  hace falta unzip' >&2; exit 1; }
    URL="https://dl.google.com/android/repository/platform-tools-latest-${PLATFORM}.zip"
    echo "  -> descargando $URL"
    fetch "$URL" "$TMP_DIR/platform-tools.zip"
    rm -rf "$BIN_DIR/platform-tools"
    unzip -q "$TMP_DIR/platform-tools.zip" -d "$BIN_DIR"
    rm -f "$TMP_DIR/platform-tools.zip"
fi
if [ -x "$ADB_BIN" ]; then
    echo "  OK: $("$ADB_BIN" version | head -n 1)"
elif command -v adb >/dev/null 2>&1; then
    echo "  OK: $(adb version | head -n 1)"
else
    echo '  AVISO: no hay adb disponible' >&2
fi

# --- 2. scrcpy -------------------------------------------------------------
echo 'scrcpy (Genymobile)'
if command -v scrcpy >/dev/null 2>&1; then
    echo "  OK: $(scrcpy --version 2>/dev/null | head -n 1)"
else
    echo '  no instalado. Instalalo con el gestor de paquetes:'
    if [ "$PLATFORM" = darwin ]; then
        echo '    brew install scrcpy'
    else
        echo '    sudo apt install scrcpy       (Debian/Ubuntu)'
        echo '    sudo snap install scrcpy      (alternativa)'
    fi
fi

echo
echo 'Binarios en:'
echo "  ADB    : ${ADB_BIN}  (o el del PATH)"
echo "  scrcpy : $(command -v scrcpy 2>/dev/null || echo 'no instalado')"
