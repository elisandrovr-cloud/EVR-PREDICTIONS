#Requires -Version 5.1
<#
.SYNOPSIS
    "Formatea" la VM Android: la devuelve a un estado limpio conocido.

.DESCRIPTION
    Tres estrategias, de mas a menos rapida:

    1) OVERLAY (por defecto, recomendado):
       Borra el overlay de escritura (data.qcow2) y lo recrea desde la imagen
       base inmutable. Reset instantaneo al estado "golden" (Android + GApps +
       TikTok ya instalados en la base). Es el "formateo" real del emulador.

    2) SNAPSHOT:
       Revierte el disco a un snapshot interno qcow2 (-Snapshot <nombre>).

    3) FRESH:
       Recrea un disco vacio (-Fresh -SizeGB N) para reinstalar Android desde 0.

    Requiere que la VM este apagada (QEMU cerrado) para no corromper el qcow2.

.PARAMETER DataDisk / -BaseDisk
    Overlay y base. Por defecto images\data.qcow2 e images\base.qcow2.

.PARAMETER Snapshot
    Nombre del snapshot al que revertir (modo SNAPSHOT).

.PARAMETER Fresh
    Recrea un disco vacio en lugar de un overlay (modo FRESH).

.PARAMETER SizeGB
    Tamano del disco en modo FRESH. Por defecto 32.

.PARAMETER Force
    No pide confirmacion.

.EXAMPLE
    # Formateo estandar: overlay limpio desde la base
    .\scripts\vm-format.ps1 -Force

.EXAMPLE
    # Revertir a un snapshot "limpio"
    .\scripts\vm-format.ps1 -Snapshot clean
#>
[CmdletBinding()]
param(
    [string]$BaseDisk,
    [string]$DataDisk,
    [string]$Snapshot,
    [switch]$Fresh,
    [int]$SizeGB = 32,
    [string]$QemuPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $BaseDisk) { $BaseDisk = Join-Path $ProjectRoot 'images\base.qcow2' }
if (-not $DataDisk) { $DataDisk = Join-Path $ProjectRoot 'images\data.qcow2' }

# --- Resolver qemu-img -----------------------------------------------------
function Resolve-QemuImg {
    param([string]$Explicit)
    if ($Explicit) {
        $c = Join-Path (Split-Path $Explicit -Parent) 'qemu-img.exe'
        if (Test-Path $c) { return $c }
    }
    $inPath = Get-Command qemu-img.exe -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }
    $bundled = Join-Path $ProjectRoot 'bin\qemu\qemu-img.exe'
    if (Test-Path $bundled) { return $bundled }
    throw 'qemu-img.exe no encontrado (instala QEMU o pasa -QemuPath).'
}
$QemuImg = Resolve-QemuImg -Explicit $QemuPath

# --- Guard: la VM debe estar apagada --------------------------------------
$running = Get-Process -Name 'qemu-system-x86_64' -ErrorAction SilentlyContinue
if ($running) {
    throw "La VM esta en ejecucion (PID $($running.Id)). Apaga QEMU antes de formatear."
}

function Confirm-Action {
    param([string]$Message)
    if ($Force) { return $true }
    $ans = Read-Host "$Message  [y/N]"
    return $ans -match '^(y|s|yes|si)$'
}

# --- Modo SNAPSHOT ---------------------------------------------------------
if ($Snapshot) {
    if (-not (Test-Path $DataDisk)) { throw "No existe $DataDisk." }
    if (-not (Confirm-Action "Revertir '$DataDisk' al snapshot '$Snapshot' (se pierde lo posterior)?")) {
        Write-Host 'Cancelado.' -ForegroundColor Yellow; return
    }
    & $QemuImg snapshot -a $Snapshot $DataDisk
    Write-Host "OK: revertido al snapshot '$Snapshot'." -ForegroundColor Green
    return
}

# --- Modo FRESH ------------------------------------------------------------
if ($Fresh) {
    if (-not (Confirm-Action "Recrear disco VACIO ($SizeGB GB) en '$DataDisk'? Se borra TODO.")) {
        Write-Host 'Cancelado.' -ForegroundColor Yellow; return
    }
    if (Test-Path $DataDisk) { Remove-Item $DataDisk -Force }
    & $QemuImg create -f qcow2 $DataDisk "${SizeGB}G" | Out-Null
    Write-Host "OK: disco vacio recreado. Reinstala Android con launch-vm.ps1 -Install." -ForegroundColor Green
    return
}

# --- Modo OVERLAY (por defecto) -------------------------------------------
if (-not (Test-Path $BaseDisk)) {
    throw "No existe la imagen base ($BaseDisk). Sin base no hay a que 'formatear'. Usa -Fresh para empezar de 0."
}
if (-not (Confirm-Action "Formatear: borrar overlay '$DataDisk' y recrearlo desde la base?")) {
    Write-Host 'Cancelado.' -ForegroundColor Yellow; return
}
if (Test-Path $DataDisk) { Remove-Item $DataDisk -Force }
& $QemuImg create -f qcow2 -b $BaseDisk -F qcow2 $DataDisk | Out-Null

$info = & $QemuImg info $DataDisk
Write-Host 'OK: emulador formateado al estado base (Android limpio).' -ForegroundColor Green
Write-Host $info -ForegroundColor DarkGray
