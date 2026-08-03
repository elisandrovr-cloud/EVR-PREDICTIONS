#!/bin/sh
# EVR Emulator - instala y lanza apps en la VM Android via ADB (Linux / macOS).
#
#   --serial <endpoint>  endpoint ADB del emulador (por defecto 127.0.0.1:4444)
#   --app <atajo>        tiktok | tiktok-lite | trill
#   --package <nombre>   nombre de paquete explicito (tiene prioridad sobre --app)
#   --apk <ruta>         sideload de un APK local
#   --play               abre la ficha de Play Store de la app (necesita GApps)
#   --launch             lanza la app despues de instalar
#
# "TikTok Pro" = cuenta Business/Pro dentro de la propia app (Perfil > Ajustes >
# Gestionar cuenta > Cambiar a cuenta Business), no es un paquete distinto.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")

SERIAL=127.0.0.1:4444
APP=tiktok
PACKAGE=""
APK=""
PLAY=0
LAUNCH=0

while [ $# -gt 0 ]; do
    case "$1" in
        --serial)  SERIAL="${2:?}"; shift ;;
        --app)     APP="${2:?}"; shift ;;
        --package) PACKAGE="${2:?}"; shift ;;
        --apk)     APK="${2:?}"; shift ;;
        --play)    PLAY=1 ;;
        --launch)  LAUNCH=1 ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; exit 2 ;;
    esac
    shift
done

# adb: primero el portable del proyecto, luego el del sistema.
if [ -x "$ROOT/bin/platform-tools/adb" ]; then
    ADB="$ROOT/bin/platform-tools/adb"
elif command -v adb >/dev/null 2>&1; then
    ADB=$(command -v adb)
else
    echo 'adb no encontrado. Corre scripts/fetch-binaries.sh.' >&2
    exit 1
fi

if [ -z "$PACKAGE" ]; then
    case "$APP" in
        tiktok)      PACKAGE=com.zhiliaoapp.musically ;;
        tiktok-lite) PACKAGE=com.zhiliaoapp.musically.go ;;
        trill)       PACKAGE=com.ss.android.ugc.trill ;;
        *) echo "Atajo desconocido: $APP (usa --package)" >&2; exit 2 ;;
    esac
fi

echo "Conectando ADB a $SERIAL ..."
"$ADB" connect "$SERIAL" >/dev/null 2>&1 || true
"$ADB" -s "$SERIAL" wait-for-device

if [ -n "$APK" ]; then
    [ -f "$APK" ] || { echo "APK no encontrado: $APK" >&2; exit 1; }
    echo "Instalando (sideload): $APK"
    "$ADB" -s "$SERIAL" install -r -g "$APK"
fi

if [ "$PLAY" -eq 1 ]; then
    echo "Abriendo la ficha de Play Store de $PACKAGE ..."
    "$ADB" -s "$SERIAL" shell am start -a android.intent.action.VIEW -d "market://details?id=$PACKAGE"
    echo "Toca 'Instalar' en la pantalla del emulador."
fi

if "$ADB" -s "$SERIAL" shell pm list packages "$PACKAGE" | grep -q "package:$PACKAGE"; then
    echo "Instalado: $PACKAGE"
    if [ "$LAUNCH" -eq 1 ]; then
        echo "Lanzando $PACKAGE ..."
        "$ADB" -s "$SERIAL" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null
    fi
elif [ "$PLAY" -eq 0 ]; then
    echo "Aun no aparece $PACKAGE instalado."
fi
