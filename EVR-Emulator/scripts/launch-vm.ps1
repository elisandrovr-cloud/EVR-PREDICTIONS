#Requires -Version 5.1
<#
.SYNOPSIS
    Lanza la VM Android (BlissOS / Android-x86) en QEMU con aceleracion WHPX + GPU.

.DESCRIPTION
    Motor de la Capa 1 del EVR Emulator. Usa el patron "imagen base + overlay":
      - base.qcow2  : instalacion golden inmutable (Android + GApps + TikTok).
      - data.qcow2  : overlay de escritura desechable (se recrea al "formatear").

    Modos:
      -Install : arranca desde el ISO para instalar Android en base.qcow2.
      (normal) : arranca desde data.qcow2 (overlay) con red + ADB por TCP.

.PARAMETER Iso
    Ruta al ISO de BlissOS / Android-x86 (solo necesario con -Install).

.PARAMETER BaseDisk
    Imagen golden inmutable. Por defecto images\base.qcow2.

.PARAMETER DataDisk
    Overlay de escritura. Por defecto images\data.qcow2.

.PARAMETER Ram / -Cores
    Recursos asignados a la VM. Por defecto 4096 MB y 4 vCPU.

.PARAMETER HostAdbPort
    Puerto del host reenviado al 5555 del guest (para `adb connect`). Por defecto 4444.

.PARAMETER GpuAccel
    Activa virtio-gpu con virgl (OpenGL). Desactivar si el build de QEMU no lo soporta.

.PARAMETER QemuPath
    Ruta a qemu-system-x86_64.exe. Si se omite, se busca en PATH y en bin\qemu.

.EXAMPLE
    # 1) Instalar Android en la imagen base (una sola vez)
    .\scripts\launch-vm.ps1 -Install -Iso .\images\bliss.iso -DiskSizeGB 32

.EXAMPLE
    # 2) Uso normal (arranca el overlay, red + ADB)
    .\scripts\launch-vm.ps1
#>
[CmdletBinding()]
param(
    [string]$Iso,
    [string]$BaseDisk,
    [string]$DataDisk,
    [int]$DiskSizeGB = 32,
    [int]$Ram = 4096,
    [int]$Cores = 4,
    [int]$HostAdbPort = 4444,
    [switch]$GpuAccel = $true,
    [ValidateSet('gtk', 'sdl')] [string]$Display = 'gtk',
    [string]$QemuPath,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $BaseDisk) { $BaseDisk = Join-Path $ProjectRoot 'images\base.qcow2' }
if (-not $DataDisk) { $DataDisk = Join-Path $ProjectRoot 'images\data.qcow2' }

# --- Resolver QEMU ---------------------------------------------------------
function Resolve-Qemu {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path $Explicit)) { return $Explicit }
    $inPath = Get-Command qemu-system-x86_64.exe -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }
    $bundled = Join-Path $ProjectRoot 'bin\qemu\qemu-system-x86_64.exe'
    if (Test-Path $bundled) { return $bundled }
    throw @'
QEMU no encontrado. Instalalo con uno de estos metodos:
  winget install --id SoftwareFreedomConservancy.QEMU
  o descarga el build de Windows: https://qemu.weilnetz.de/w64/
Luego reejecuta, o pasa -QemuPath "C:\Program Files\qemu\qemu-system-x86_64.exe".
'@
}
$Qemu = Resolve-Qemu -Explicit $QemuPath
$QemuImg = Join-Path (Split-Path $Qemu -Parent) 'qemu-img.exe'
Write-Host "QEMU   : $Qemu" -ForegroundColor DarkGray

# --- Preparar discos -------------------------------------------------------
if ($Install) {
    if (-not $Iso -or -not (Test-Path $Iso)) {
        throw "Con -Install debes pasar un -Iso valido (ISO de BlissOS/Android-x86)."
    }
    if (-not (Test-Path $BaseDisk)) {
        Write-Host "Creando imagen base $DiskSizeGB GB -> $BaseDisk" -ForegroundColor Cyan
        & $QemuImg create -f qcow2 $BaseDisk "${DiskSizeGB}G" | Out-Null
    } else {
        Write-Host "Reutilizando base existente: $BaseDisk" -ForegroundColor Yellow
    }
} else {
    if (-not (Test-Path $BaseDisk)) {
        throw "No existe la imagen base ($BaseDisk). Primero corre con -Install -Iso <iso>."
    }
    if (-not (Test-Path $DataDisk)) {
        Write-Host "Creando overlay de escritura sobre la base -> $DataDisk" -ForegroundColor Cyan
        & $QemuImg create -f qcow2 -b $BaseDisk -F qcow2 $DataDisk | Out-Null
    }
}

# --- Construir argumentos de QEMU -----------------------------------------
# OJO: no usar $args aqui; en PowerShell es una variable automatica y
# sobrescribirla rompe el paso de argumentos del propio script.
$acceleration = 'whpx,kernel-irqchip=off'   # combinacion estable en Windows
$qemuArgs = @(
    '-machine', "q35,accel=$acceleration",
    '-cpu', 'max',
    '-m', "$Ram",
    '-smp', "$Cores",
    '-device', 'virtio-net-pci,netdev=net0',
    '-netdev', "user,id=net0,hostfwd=tcp::${HostAdbPort}-:5555",
    '-device', 'usb-ehci,id=usb',
    '-device', 'usb-tablet',      # puntero absoluto: el raton mapea 1:1 al touch
    '-rtc', 'base=localtime',
    '-boot', 'menu=on'
)

# GPU
if ($GpuAccel) {
    $qemuArgs += @('-device', 'virtio-vga-gl', '-display', "$Display,gl=on")
} else {
    $qemuArgs += @('-device', 'virtio-vga', '-display', "$Display,gl=off")
}

# Discos / origen de arranque. Las rutas van entrecomilladas: Start-Process
# reparte los argumentos por espacios y "C:\Program Files\..." se partiria.
if ($Install) {
    $qemuArgs += @(
        '-drive', "`"file=$BaseDisk,if=virtio,format=qcow2`"",
        '-cdrom', "`"$Iso`""
    )
    Write-Host ''
    Write-Host 'MODO INSTALACION:' -ForegroundColor Magenta
    Write-Host '  En el menu GRUB elige "Installation - Install Bliss-OS to harddisk".'
    Write-Host '  Instala en el disco virtio, crea /data (ext4), instala GRUB, y reinicia.'
    Write-Host '  Al terminar, cierra QEMU y arranca sin -Install (usa el overlay).'
    Write-Host ''
} else {
    $qemuArgs += @('-drive', "`"file=$DataDisk,if=virtio,format=qcow2`"")
}

Write-Host "Lanzando VM Android (RAM ${Ram}MB, ${Cores} vCPU, GPU=$GpuAccel)..." -ForegroundColor Green
Write-Host "ADB por TCP: host 127.0.0.1:$HostAdbPort  ->  guest :5555" -ForegroundColor DarkGray

# --- Arrancar QEMU ---------------------------------------------------------
$proc = Start-Process -FilePath $Qemu -ArgumentList $qemuArgs -PassThru
Write-Host "QEMU PID: $($proc.Id)" -ForegroundColor DarkGray

if (-not $Install) {
    Write-Host ''
    Write-Host 'Cuando Android haya arrancado, conecta ADB:' -ForegroundColor Cyan
    Write-Host "  .\bin\platform-tools\adb.exe connect 127.0.0.1:$HostAdbPort" -ForegroundColor White
    Write-Host ''
    Write-Host 'Si ADB no conecta, habilita "ADB over network" en el guest:' -ForegroundColor DarkGray
    Write-Host '  Ajustes > Sistema > Opciones de desarrollador > ADB por red' -ForegroundColor DarkGray
    Write-Host '  (o con root:  setprop service.adb.tcp.port 5555; stop adbd; start adbd)' -ForegroundColor DarkGray
}
