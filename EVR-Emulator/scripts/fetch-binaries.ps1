#Requires -Version 5.1
<#
.SYNOPSIS
    Descarga los binarios portables de ADB (platform-tools) y scrcpy para Windows.

.DESCRIPTION
    - ADB      : platform-tools-latest-windows.zip (Google, canal oficial).
    - scrcpy   : ultimo release win64 desde la API de GitHub (Genymobile/scrcpy).
    Ambos se extraen bajo <ProjectRoot>\bin\ y se verifican ejecutando --version.

.PARAMETER ProjectRoot
    Raiz del proyecto. Por defecto, la carpeta padre de este script.

.PARAMETER Force
    Vuelve a descargar aunque el binario ya exista.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\fetch-binaries.ps1
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$BinDir = Join-Path $ProjectRoot 'bin'
$TmpDir = Join-Path $ProjectRoot 'tmp'
New-Item -ItemType Directory -Path $BinDir, $TmpDir -Force | Out-Null

function Get-File {
    param([string]$Url, [string]$OutFile, [hashtable]$Headers = @{})
    Write-Host ("  -> descargando {0}" -f $Url) -ForegroundColor DarkGray
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -Headers $Headers -UseBasicParsing
}

function Expand-Into {
    param([string]$Zip, [string]$Dest)
    if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue }
    Expand-Archive -Path $Zip -DestinationPath $Dest -Force
}

# ---------------------------------------------------------------------------
# 1. ADB (Android platform-tools)
# ---------------------------------------------------------------------------
Write-Host 'ADB / platform-tools' -ForegroundColor Cyan
$adbExe = Join-Path $BinDir 'platform-tools\adb.exe'
if ((Test-Path $adbExe) -and -not $Force) {
    Write-Host '  ya presente (usa -Force para reinstalar)' -ForegroundColor DarkGray
} else {
    $adbUrl = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
    $adbZip = Join-Path $TmpDir 'platform-tools.zip'
    Get-File -Url $adbUrl -OutFile $adbZip
    Expand-Into -Zip $adbZip -Dest $BinDir   # el zip ya contiene la carpeta platform-tools\
    Remove-Item $adbZip -Force
}
if (Test-Path $adbExe) {
    $v = (& $adbExe version | Select-Object -First 1)
    Write-Host "  OK: $v" -ForegroundColor Green
} else {
    Write-Warning "  no se encontro adb.exe tras la extraccion"
}

# ---------------------------------------------------------------------------
# 2. scrcpy (ultimo release win64 via GitHub API)
# ---------------------------------------------------------------------------
Write-Host 'scrcpy (Genymobile)' -ForegroundColor Cyan
$scrcpyDir = Join-Path $BinDir 'scrcpy'
$scrcpyExe = Join-Path $scrcpyDir 'scrcpy.exe'
if ((Test-Path $scrcpyExe) -and -not $Force) {
    Write-Host '  ya presente (usa -Force para reinstalar)' -ForegroundColor DarkGray
} else {
    $apiHeaders = @{ 'User-Agent' = 'EVR-Emulator-Setup'; 'Accept' = 'application/vnd.github+json' }
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/Genymobile/scrcpy/releases/latest' -Headers $apiHeaders
    $asset = $release.assets | Where-Object { $_.name -match 'win64.*\.zip$' } | Select-Object -First 1
    if (-not $asset) { throw 'No se encontro un asset win64 en el ultimo release de scrcpy.' }

    Write-Host ("  release {0} -> {1}" -f $release.tag_name, $asset.name) -ForegroundColor DarkGray
    $scrcpyZip = Join-Path $TmpDir $asset.name
    Get-File -Url $asset.browser_download_url -OutFile $scrcpyZip

    # El zip trae una carpeta scrcpy-win64-vX.Y\ : la extraemos y normalizamos a bin\scrcpy\
    $stage = Join-Path $TmpDir 'scrcpy-stage'
    Expand-Into -Zip $scrcpyZip -Dest $stage
    $inner = Get-ChildItem $stage -Directory | Select-Object -First 1
    $srcDir = if ($inner) { $inner.FullName } else { $stage }
    if (Test-Path $scrcpyDir) { Remove-Item $scrcpyDir -Recurse -Force }
    Move-Item $srcDir $scrcpyDir
    Remove-Item $scrcpyZip, $stage -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path $scrcpyExe) {
    $v = (& $scrcpyExe --version | Select-Object -First 1)
    Write-Host "  OK: $v" -ForegroundColor Green
} else {
    Write-Warning "  no se encontro scrcpy.exe tras la extraccion"
}

Write-Host ''
Write-Host 'Binarios en:' -ForegroundColor Cyan
Write-Host "  ADB    : $adbExe"    -ForegroundColor DarkGray
Write-Host "  scrcpy : $scrcpyExe" -ForegroundColor DarkGray
