#Requires -Version 5.1
<#
.SYNOPSIS
    Instala y lanza apps en la VM Android via ADB (atajos para TikTok).

.DESCRIPTION
    Dos caminos para instalar TikTok:
      A) Play Store (recomendado): abre la ficha de la app en Google Play dentro
         del emulador para instalarla desde ahi. Requiere GApps en la imagen.
      B) Sideload: instala un APK local que tu proporciones con -Apk.

    "TikTok Pro" = cuenta Business/Pro dentro de la misma app TikTok; se activa
    en la app (Perfil > Ajustes > Gestionar cuenta > Cambiar a cuenta Business),
    no es un paquete distinto.

.PARAMETER Serial
    Endpoint ADB del emulador. Por defecto 127.0.0.1:4444.

.PARAMETER App
    Atajo: tiktok | tiktok-lite | trill. Fija el nombre de paquete.

.PARAMETER Package
    Nombre de paquete explicito (sobrescribe -App).

.PARAMETER Apk
    Ruta a un APK local para sideload (camino B).

.PARAMETER PlayStore
    Abre la ficha de Play Store de la app (camino A).

.PARAMETER Launch
    Lanza la app tras instalar.

.EXAMPLE
    # Abrir TikTok en Play Store para instalarlo
    .\scripts\install-app.ps1 -App tiktok -PlayStore

.EXAMPLE
    # Sideload de un APK y lanzar
    .\scripts\install-app.ps1 -Apk .\downloads\tiktok.apk -App tiktok -Launch
#>
[CmdletBinding()]
param(
    [string]$Serial = '127.0.0.1:4444',
    [ValidateSet('tiktok', 'tiktok-lite', 'trill')] [string]$App = 'tiktok',
    [string]$Package,
    [string]$Apk,
    [switch]$PlayStore,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Adb = Join-Path $ProjectRoot 'bin\platform-tools\adb.exe'
if (-not (Test-Path $Adb)) { throw "adb.exe no encontrado. Corre scripts\fetch-binaries.ps1." }

# Paquetes conocidos de TikTok
$packages = @{
    'tiktok'      = 'com.zhiliaoapp.musically'      # TikTok global
    'tiktok-lite' = 'com.zhiliaoapp.musically.go'   # TikTok Lite
    'trill'       = 'com.ss.android.ugc.trill'      # variante regional
}
if (-not $Package) { $Package = $packages[$App] }

function Adb-Cmd {
    param([Parameter(ValueFromRemainingArguments = $true)] [string[]]$Args)
    & $Adb -s $Serial @Args
}

# Asegura conexion ADB
Write-Host "Conectando ADB a $Serial ..." -ForegroundColor DarkGray
& $Adb connect $Serial | Out-Host
Start-Sleep -Milliseconds 500
& $Adb -s $Serial wait-for-device

# --- Camino B: sideload ----------------------------------------------------
if ($Apk) {
    if (-not (Test-Path $Apk)) { throw "APK no encontrado: $Apk" }
    Write-Host "Instalando (sideload): $Apk" -ForegroundColor Cyan
    Adb-Cmd install -r -g $Apk
}

# --- Camino A: Play Store ---------------------------------------------------
if ($PlayStore) {
    Write-Host "Abriendo ficha de Play Store para $Package ..." -ForegroundColor Cyan
    Adb-Cmd shell am start -a android.intent.action.VIEW -d "market://details?id=$Package"
    Write-Host "Toca 'Instalar' en la pantalla del emulador." -ForegroundColor DarkGray
}

# --- Estado / lanzamiento ---------------------------------------------------
$installed = (Adb-Cmd shell pm list packages $Package) -join ''
if ($installed -match [regex]::Escape($Package)) {
    Write-Host "Instalado: $Package" -ForegroundColor Green
    if ($Launch) {
        Write-Host "Lanzando $Package ..." -ForegroundColor Cyan
        Adb-Cmd shell monkey -p $Package -c android.intent.category.LAUNCHER 1 | Out-Null
    }
} elseif (-not $PlayStore) {
    Write-Host "Aun no aparece $Package instalado." -ForegroundColor Yellow
}
