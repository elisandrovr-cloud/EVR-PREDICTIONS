#Requires -Version 5.1
<#
.SYNOPSIS
    EVR Emulator - Script de aprovisionamiento "Elisandro" (Windows 10/11).

.DESCRIPTION
    Preflight de hardware y preparacion del entorno para el motor de
    virtualizacion Android (QEMU/WHPX + Android-x86/BlissOS).

    Verifica:
      - Virtualizacion asistida por hardware (VT-x / AMD-V) + SLAT (EPT/NPT).
      - RAM fisica total (minimo configurable, por defecto 8 GB).
      - GPU(s) instaladas y version de driver.
      - Estado de las caracteristicas de Windows (Hypervisor Platform / Hyper-V).
      - Presencia de Node.js / npm para el middleware.
    Y crea la estructura de directorios del proyecto.

.PARAMETER ProjectRoot
    Raiz del proyecto. Por defecto, la carpeta donde reside este script.

.PARAMETER MinRamGB
    RAM minima requerida en GB. Por defecto 8.

.PARAMETER FetchBinaries
    Si se indica, invoca scripts\fetch-binaries.ps1 al finalizar el preflight.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\elisandro-setup.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\elisandro-setup.ps1 -MinRamGB 16 -FetchBinaries
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [int]$MinRamGB = 8,
    [switch]$FetchBinaries
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------
# Helpers de presentacion
# ---------------------------------------------------------------------------
$script:Failures = 0
$script:Warnings = 0

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host ('==== {0} ' -f $Title).PadRight(74, '=') -ForegroundColor Cyan
}

function Write-Result {
    param(
        [string]$Label,
        [ValidateSet('OK', 'WARN', 'FAIL', 'INFO')] [string]$Status,
        [string]$Detail = ''
    )
    $map = @{
        OK   = @{ Tag = '[  OK  ]'; Color = 'Green'  }
        WARN = @{ Tag = '[ WARN ]'; Color = 'Yellow' }
        FAIL = @{ Tag = '[ FAIL ]'; Color = 'Red'    }
        INFO = @{ Tag = '[ INFO ]'; Color = 'Gray'   }
    }
    $entry = $map[$Status]
    Write-Host ('{0} ' -f $entry.Tag) -ForegroundColor $entry.Color -NoNewline
    Write-Host ('{0}' -f $Label.PadRight(38)) -NoNewline
    if ($Detail) { Write-Host $Detail -ForegroundColor DarkGray } else { Write-Host '' }
    if ($Status -eq 'FAIL') { $script:Failures++ }
    if ($Status -eq 'WARN') { $script:Warnings++ }
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------------------------------------------------------------------------
# 0. Cabecera
# ---------------------------------------------------------------------------
Clear-Host
Write-Host @'
  ______ __      __ _____    ______                       _         _
 |  ____|\ \    / /|  __ \  |  ____|                      | |       | |
 | |__    \ \  / / | |__) | | |__   _ __ ___   _   _  ___ | |  __ _ | |_  ___   _ __
 |  __|    \ \/ /  |  _  /  |  __| | '_ ` _ \ | | | |/ __|| | / _` || __|/ _ \ | '__|
 | |____    \  /   | | \ \  | |____| | | | | || |_| |\__ \| || (_| || |_| (_) || |
 |______|    \/    |_|  \_\ |______|_| |_| |_| \__,_||___/|_| \__,_| \__|\___/ |_|

   Elisandro Provisioning  ::  Fase 1  ::  Preflight & Bootstrap (Windows)
'@ -ForegroundColor Magenta

$osInfo = Get-CimInstance Win32_OperatingSystem
Write-Result -Label 'Sistema operativo' -Status INFO -Detail ("{0} (build {1})" -f $osInfo.Caption, $osInfo.BuildNumber)
Write-Result -Label 'Ejecutando como administrador' -Status $(if (Test-IsAdmin) { 'OK' } else { 'WARN' }) `
    -Detail $(if (Test-IsAdmin) { 'privilegios elevados' } else { 'algunas comprobaciones de features requieren admin' })

# ---------------------------------------------------------------------------
# 1. Virtualizacion por hardware (VT-x / AMD-V + SLAT)
# ---------------------------------------------------------------------------
Write-Section 'Virtualizacion por hardware'

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cs  = Get-CimInstance Win32_ComputerSystem

$vtSupported = [bool]$cpu.VMMonitorModeExtensions                 # CPU soporta VT-x/SVM
$slat        = [bool]$cpu.SecondLevelAddressTranslationExtensions # EPT / NPT (requerido por WHPX)
$fwEnabled   = [bool]$cpu.VirtualizationFirmwareEnabled           # VT habilitado en BIOS/UEFI
$hyperv      = [bool]$cs.HypervisorPresent                        # un hipervisor ya esta activo

Write-Result -Label 'CPU' -Status INFO -Detail $cpu.Name.Trim()
Write-Result -Label 'VT-x / AMD-V soportado (CPU)' -Status $(if ($vtSupported) { 'OK' } else { 'FAIL' }) `
    -Detail "VMMonitorModeExtensions=$vtSupported"
Write-Result -Label 'SLAT (EPT/NPT)' -Status $(if ($slat) { 'OK' } else { 'FAIL' }) `
    -Detail "requerido por Windows Hypervisor Platform"
Write-Result -Label 'VT habilitado en firmware' -Status $(if ($fwEnabled -or $hyperv) { 'OK' } else { 'FAIL' }) `
    -Detail $(if ($hyperv) { 'firmware reporta OFF porque hay un hipervisor activo (normal con Hyper-V)' } else { "VirtualizationFirmwareEnabled=$fwEnabled" })
Write-Result -Label 'Hipervisor activo en el host' -Status INFO -Detail "HypervisorPresent=$hyperv"

$vtUsable = ($vtSupported -and $slat) -and ($fwEnabled -or $hyperv)
if ($vtUsable) {
    Write-Result -Label 'Veredicto virtualizacion' -Status OK -Detail 'apto para QEMU/WHPX acelerado'
} else {
    Write-Result -Label 'Veredicto virtualizacion' -Status FAIL `
        -Detail 'habilita VT-x/AMD-V en la BIOS/UEFI (Intel VT-x + VT-d / AMD SVM)'
}

# ---------------------------------------------------------------------------
# 2. RAM fisica
# ---------------------------------------------------------------------------
Write-Section 'Memoria RAM'

$totalRamGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$freeRamGB  = [math]::Round(($osInfo.FreePhysicalMemory * 1KB) / 1GB, 1)

Write-Result -Label 'RAM total instalada' -Status $(if ($totalRamGB -ge $MinRamGB) { 'OK' } else { 'FAIL' }) `
    -Detail "$totalRamGB GB (minimo requerido: $MinRamGB GB)"
Write-Result -Label 'RAM libre actual' -Status $(if ($freeRamGB -ge 2) { 'OK' } else { 'WARN' }) `
    -Detail "$freeRamGB GB disponibles"

# ---------------------------------------------------------------------------
# 3. GPU
# ---------------------------------------------------------------------------
Write-Section 'GPU'

$gpus = Get-CimInstance Win32_VideoController
foreach ($g in $gpus) {
    $vram = if ($g.AdapterRAM -gt 0) { "{0} MB VRAM" -f [math]::Round($g.AdapterRAM / 1MB) } else { 'VRAM n/d' }
    Write-Result -Label ('GPU: ' + $g.Name) -Status INFO -Detail ("driver {0} | {1}" -f $g.DriverVersion, $vram)
}
if (-not $gpus) { Write-Result -Label 'GPU' -Status WARN -Detail 'no se detectaron adaptadores de video' }

# ---------------------------------------------------------------------------
# 4. Caracteristicas de Windows (WHPX / Hyper-V)
# ---------------------------------------------------------------------------
Write-Section 'Caracteristicas de Windows'

if (Test-IsAdmin) {
    foreach ($feat in @('HypervisorPlatform', 'Microsoft-Hyper-V-All')) {
        try {
            $state = (Get-WindowsOptionalFeature -Online -FeatureName $feat -ErrorAction Stop).State
            $status = if ($state -eq 'Enabled') { 'OK' } else { 'INFO' }
            Write-Result -Label $feat -Status $status -Detail "State=$state"
        } catch {
            Write-Result -Label $feat -Status WARN -Detail 'no disponible en esta edicion de Windows'
        }
    }
    Write-Result -Label 'Sugerencia' -Status INFO `
        -Detail 'para WHPX: Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform'
} else {
    Write-Result -Label 'Estado de features' -Status WARN -Detail 'reejecuta como administrador para inspeccionarlo'
}

# ---------------------------------------------------------------------------
# 5. Toolchain (Node.js / npm)
# ---------------------------------------------------------------------------
Write-Section 'Toolchain del middleware'

$node = Get-Command node -ErrorAction SilentlyContinue
$npm  = Get-Command npm  -ErrorAction SilentlyContinue
if ($node) {
    $nodeVer = (& node --version) 2>$null
    $ok = $nodeVer -match '^v(1[89]|[2-9]\d)\.'   # >= v18
    Write-Result -Label 'Node.js' -Status $(if ($ok) { 'OK' } else { 'WARN' }) -Detail "$nodeVer (se recomienda >= v18)"
} else {
    Write-Result -Label 'Node.js' -Status WARN -Detail 'no instalado -> https://nodejs.org (LTS)'
}
Write-Result -Label 'npm' -Status $(if ($npm) { 'OK' } else { 'WARN' }) -Detail $(if ($npm) { (& npm --version) } else { 'no encontrado' })

# ---------------------------------------------------------------------------
# 6. Estructura de directorios
# ---------------------------------------------------------------------------
Write-Section 'Estructura de directorios del proyecto'

$dirs = @(
    'bin',                 # adb.exe, scrcpy.exe, qemu (binarios portables)
    'images',              # imagenes Android (BlissOS / Android-x86)
    'middleware',          # servidor Node.js (API REST + WebSocket)
    'middleware\src',
    'frontend',            # UI "Elisandro" (HTML5/CSS3/JS)
    'config',              # perfiles de VM, plantillas build.prop, etc.
    'scripts',             # aprovisionamiento y control de la VM
    'logs',
    'tmp'
)
foreach ($d in $dirs) {
    $full = Join-Path $ProjectRoot $d
    if (Test-Path $full) {
        Write-Result -Label $d -Status INFO -Detail 'ya existe'
    } else {
        New-Item -ItemType Directory -Path $full -Force | Out-Null
        Write-Result -Label $d -Status OK -Detail 'creado'
    }
}

# Configuracion local del middleware a partir de la plantilla.
$envExample = Join-Path $ProjectRoot 'middleware\.env.example'
$envFile    = Join-Path $ProjectRoot 'middleware\.env'
if ((Test-Path $envExample) -and -not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Result -Label 'middleware\.env' -Status OK -Detail 'creado desde .env.example'
} elseif (Test-Path $envFile) {
    Write-Result -Label 'middleware\.env' -Status INFO -Detail 'ya existe'
}

# ---------------------------------------------------------------------------
# 7. Fetch de binarios (opcional)
# ---------------------------------------------------------------------------
if ($FetchBinaries) {
    Write-Section 'Descarga de binarios (ADB + scrcpy)'
    $fetch = Join-Path $ProjectRoot 'scripts\fetch-binaries.ps1'
    if (Test-Path $fetch) {
        & $fetch -ProjectRoot $ProjectRoot
    } else {
        Write-Result -Label 'fetch-binaries.ps1' -Status WARN -Detail "no encontrado en $fetch"
    }
}

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
Write-Section 'Resumen'
Write-Result -Label 'Fallos criticos' -Status $(if ($script:Failures -eq 0) { 'OK' } else { 'FAIL' }) -Detail $script:Failures
Write-Result -Label 'Advertencias'    -Status $(if ($script:Warnings -eq 0) { 'OK' } else { 'WARN' }) -Detail $script:Warnings

if ($script:Failures -gt 0) {
    Write-Host ''
    Write-Host 'Preflight con FALLOS: resuelve los items [FAIL] antes de continuar a la Fase 2.' -ForegroundColor Red
    exit 1
} else {
    Write-Host ''
    Write-Host 'Preflight superado. Entorno listo para la Fase 2 (imagen Android).' -ForegroundColor Green
    Write-Host 'Siguiente: cd middleware; npm install; npm start' -ForegroundColor DarkGray
    exit 0
}
