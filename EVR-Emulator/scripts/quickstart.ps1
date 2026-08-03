#Requires -Version 5.1
<#
.SYNOPSIS
    EVR Emulator - arranque guiado en un comando (Windows). De cero a Android
    con Play Store visible (ventana QEMU tipo BlueStacks) + consola web.

.DESCRIPTION
    Encadena todo el flujo:
      1) Preflight de hardware + descarga de binarios (ADB, scrcpy).
      2) Asegura QEMU (lo instala con winget si falta).
      3) Localiza el ISO de BlissOS (con GApps) en images\ o via -Iso.
      4) Si no hay imagen base: abre QEMU para INSTALAR Android en base.qcow2.
      5) Si ya hay base: arranca la VM + el middleware + abre la consola web.

    La ventana de QEMU ES tu pantalla Android (como un teléfono/tablet). La
    consola web (http://127.0.0.1:5555) la refleja y te da controles.

.PARAMETER Iso
    Ruta al ISO de BlissOS con GApps. Si se omite, se busca en images\*.iso.

.PARAMETER SkipSetup
    Omite el preflight/descarga de binarios (si ya lo corriste).

.PARAMETER Ram / -Cores
    Recursos de la VM. Por defecto 4096 MB y 4 vCPU.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\quickstart.ps1
#>
[CmdletBinding()]
param(
    [string]$Iso,
    [switch]$SkipSetup,
    [int]$Ram = 4096,
    [int]$Cores = 4,
    [switch]$NoConsole
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $PSScriptRoot
function Say([string]$m, [string]$c = 'Cyan') { Write-Host $m -ForegroundColor $c }

# ---------------------------------------------------------------------------
# 1) Preflight + binarios
# ---------------------------------------------------------------------------
if (-not $SkipSetup) {
    Say '== Paso 1/5: preflight de hardware + binarios (ADB, scrcpy) =='
    $setup = Join-Path $Root 'elisandro-setup.ps1'
    $p = Start-Process powershell -PassThru -Wait -NoNewWindow -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $setup, '-FetchBinaries'
    )
    if ($p.ExitCode -ne 0) { Say 'Preflight con FALLOS: resuelvelos (ver arriba) y reintenta.' 'Red'; return }
}

# ---------------------------------------------------------------------------
# 2) Asegurar QEMU
# ---------------------------------------------------------------------------
Say '== Paso 2/5: QEMU =='
$qemu = Get-Command qemu-system-x86_64.exe -ErrorAction SilentlyContinue
if (-not $qemu) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say 'QEMU no encontrado. Instalando con winget...' 'Yellow'
        winget install --id SoftwareFreedomConservancy.QEMU -e --accept-source-agreements --accept-package-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        $qemu = Get-Command qemu-system-x86_64.exe -ErrorAction SilentlyContinue
    }
}
if (-not $qemu) {
    Say 'Instala QEMU y reintenta:  winget install SoftwareFreedomConservancy.QEMU' 'Red'
    Say '  o descarga el build Windows: https://qemu.weilnetz.de/w64/' 'Red'
    return
}
Say ("QEMU: {0}" -f $qemu.Source) 'DarkGray'

# ---------------------------------------------------------------------------
# 3) Localizar el ISO de BlissOS (con GApps)
# ---------------------------------------------------------------------------
Say '== Paso 3/5: imagen de Android =='
if (-not $Iso) {
    $found = Get-ChildItem (Join-Path $Root 'images') -Filter *.iso -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $Iso = $found.FullName }
}
$base = Join-Path $Root 'images\base.qcow2'
if (-not (Test-Path $base) -and -not $Iso) {
    Say @'
No hay imagen base ni ISO en images\.
Descarga una build de BlissOS que INCLUYA GApps (Play Store ya integrado):
    https://blissos.org   ->  build "GApps", Android 13/14, x86_64
Guarda el .iso en:   images\
Luego reejecuta:     .\scripts\quickstart.ps1
'@ 'Yellow'
    return
}

# ---------------------------------------------------------------------------
# 4) Instalar Android en la imagen base (primera vez)
# ---------------------------------------------------------------------------
$launch = Join-Path $Root 'scripts\launch-vm.ps1'
if (-not (Test-Path $base)) {
    Say '== Paso 4/5: INSTALANDO Android en la imagen base (ventana QEMU) =='
    Say 'En el menu GRUB:  "Installation - Install Bliss-OS to harddisk"' 'Gray'
    Say '  -> instala en el disco virtio (crea /data ext4, instala GRUB) y reinicia.' 'Gray'
    Say '  -> cuando Android arranque bien, CIERRA la ventana de QEMU.' 'Gray'
    & $launch -Install -Iso $Iso -Ram $Ram -Cores $Cores
    Say ''
    Say 'Al terminar la instalacion y cerrar QEMU, reejecuta:  .\scripts\quickstart.ps1' 'Green'
    return
}

# ---------------------------------------------------------------------------
# 5) Arranque normal: VM + middleware + consola
# ---------------------------------------------------------------------------
Say '== Paso 5/5: arrancando Android + consola web =='

# 5a) Dependencias del middleware
$mw = Join-Path $Root 'middleware'
if (-not (Test-Path (Join-Path $mw 'node_modules'))) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Say 'Instalando dependencias del middleware...' 'DarkGray'
        Push-Location $mw; npm install --no-audit --no-fund; Pop-Location
    } else {
        Say 'Node.js no instalado: la consola web no arrancara (https://nodejs.org/LTS).' 'Yellow'
    }
}

# 5b) Middleware en su propia ventana
if (Get-Command node -ErrorAction SilentlyContinue) {
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location `"$mw`"; node server.js"
    Start-Sleep -Seconds 1
}

# 5c) La VM (la ventana QEMU es tu pantalla Android)
& $launch -Ram $Ram -Cores $Cores
Start-Sleep -Seconds 2

# 5d) Conectar ADB y abrir la consola
$adb = Join-Path $Root 'bin\platform-tools\adb.exe'
if (Test-Path $adb) { & $adb connect 127.0.0.1:4444 | Out-Null }
if (-not $NoConsole) { Start-Process 'http://127.0.0.1:5555' }

Say ''
Say 'LISTO.' 'Green'
Say '  - La ventana de QEMU es tu Android (como BlueStacks).' 'Gray'
Say '  - Consola web: http://127.0.0.1:5555' 'Gray'
Say '  - En Android: abre Play Store, inicia sesion con tu Google, instala TikTok y crea tu cuenta.' 'Gray'
Say '  - Si Play Store dice "sin certificar": registra el Android ID en' 'Gray'
Say '    https://google.com/android/uncertified (metodo oficial para ROMs personalizadas).' 'Gray'
