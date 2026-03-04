# Człowiek Roku Desktop — Skrypt budowania dla Windows
# Plik: scripts/build_windows.ps1
#
# Tworzy:
#   dist\CzlowiekRoku-v{VERSION}-portable.exe  — samodzielny przenośny EXE
#   dist\CzlowiekRoku-v{VERSION}-setup.msi      — instalator MSI (WiX v4)
#
# Wymagania:
#   .NET 8 SDK : https://dotnet.microsoft.com/download/dotnet/8.0
#   WiX v4     : dotnet tool install --global wix
#              : wix extension add WixToolset.UI.wixext --global
#
# Użycie:
#   .\scripts\build_windows.ps1
#   .\scripts\build_windows.ps1 -Version "1.2.0" -Configuration Release
#   .\scripts\build_windows.ps1 -SkipMsi          # tylko EXE
#   .\scripts\build_windows.ps1 -Clean            # wyczyszczone + rebuild

param(
    [string]$Version       = "1.0.0",
    [string]$Configuration = "Release",
    [string]$Runtime       = "win-x64",
    [switch]$SkipMsi,
    [switch]$SkipExe,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Ścieżki ──────────────────────────────────────────────────────────────
$RepoRoot     = $PSScriptRoot | Split-Path -Parent
$ProjectDir   = Join-Path $RepoRoot "clients\desktop"
$ProjectFile  = Join-Path $ProjectDir "CzlowiekRoku.Desktop.csproj"
$InstallerDir = Join-Path $ProjectDir "installer"
$WixFile      = Join-Path $InstallerDir "Product.wxs"
$DistDir      = Join-Path $RepoRoot "dist"
$BuildDir     = Join-Path $RepoRoot "build\desktop"

# ── Pomocnicy ────────────────────────────────────────────────────────────
function Write-Step { param($Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param($Msg) Write-Host "  OK  $Msg" -ForegroundColor Green }
function Abort      { param($Msg) Write-Host "  ERR $Msg" -ForegroundColor Red; exit 1 }

# ── Sprawdzenie środowiska ────────────────────────────────────────────────
Write-Step "Sprawdzanie środowiska..."

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Abort ".NET SDK nie jest zainstalowany. Pobierz z https://dotnet.microsoft.com/download/dotnet/8.0"
}
$dotnetVersion = (dotnet --version)
Write-Ok ".NET SDK $dotnetVersion"

if (-not (Test-Path $ProjectFile)) {
    Abort "Nie znaleziono pliku projektu: $ProjectFile"
}
Write-Ok "Plik projektu: $ProjectFile"

# ── Czyszczenie ───────────────────────────────────────────────────────────
if ($Clean) {
    Write-Step "Czyszczenie katalogu build..."
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
    Write-Ok "Wyczyszczono: $BuildDir"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# ── Restore ───────────────────────────────────────────────────────────────
Write-Step "Przywracanie pakietów NuGet..."
& dotnet restore $ProjectFile --runtime $Runtime
if ($LASTEXITCODE -ne 0) { Abort "dotnet restore zakończony błędem." }
Write-Ok "Pakiety przywrócone."

# ── Build ─────────────────────────────────────────────────────────────────
Write-Step "Kompilacja ($Configuration / $Runtime)..."
& dotnet build $ProjectFile `
    --configuration $Configuration `
    --runtime $Runtime `
    --no-restore `
    -p:Version=$Version
if ($LASTEXITCODE -ne 0) { Abort "dotnet build zakończony błędem." }
Write-Ok "Kompilacja zakończona."

# ── Publish: przenośny pojedynczy plik EXE ────────────────────────────────
if (-not $SkipExe) {
    Write-Step "Publikacja: przenośny pojedynczy plik EXE (self-contained)..."
    $ExePublishDir = Join-Path $BuildDir "single-file"
    New-Item -ItemType Directory -Force -Path $ExePublishDir | Out-Null

    & dotnet publish $ProjectFile `
        --configuration $Configuration `
        --runtime $Runtime `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:Version=$Version `
        --output $ExePublishDir `
        --no-build
    if ($LASTEXITCODE -ne 0) { Abort "dotnet publish (single-file) zakończony błędem." }

    $SourceExe = Join-Path $ExePublishDir "CzlowiekRoku.Desktop.exe"
    $TargetExe = Join-Path $DistDir "CzlowiekRoku-v$Version-portable.exe"
    Copy-Item $SourceExe $TargetExe -Force
    $sizeMb = [math]::Round((Get-Item $TargetExe).Length / 1MB, 1)
    Write-Ok "Przenośny EXE: $TargetExe  [$sizeMb MB]"
}

# ── Publish: katalog (dla MSI) ────────────────────────────────────────────
if (-not $SkipMsi) {
    Write-Step "Publikacja: katalog dla instalatora MSI..."
    $MsiPublishDir = Join-Path $BuildDir "msi-source"
    New-Item -ItemType Directory -Force -Path $MsiPublishDir | Out-Null

    & dotnet publish $ProjectFile `
        --configuration $Configuration `
        --runtime $Runtime `
        --self-contained true `
        -p:PublishSingleFile=false `
        -p:Version=$Version `
        --output $MsiPublishDir
    if ($LASTEXITCODE -ne 0) { Abort "dotnet publish (katalog) zakończony błędem." }
    Write-Ok "Pliki aplikacji: $MsiPublishDir"

    # ── MSI via WiX v4 ────────────────────────────────────────────────────
    if (Get-Command wix -ErrorAction SilentlyContinue) {
        Write-Step "Budowanie instalatora MSI za pomocą WiX v4..."
        $MsiTarget = Join-Path $DistDir "CzlowiekRoku-v$Version-setup.msi"
        & wix build $WixFile `
            -ext WixToolset.UI.wixext `
            -d "PublishDir=$MsiPublishDir\" `
            -d "Version=$Version" `
            -o $MsiTarget
        if ($LASTEXITCODE -ne 0) { Abort "wix build zakończony błędem." }
        $sizeMb = [math]::Round((Get-Item $MsiTarget).Length / 1MB, 1)
        Write-Ok "Instalator MSI: $MsiTarget  [$sizeMb MB]"
    }
    else {
        Write-Host "`n  POMINIĘTO  WiX nie jest zainstalowany — MSI nie zostało zbudowane." -ForegroundColor Yellow
        Write-Host "  Aby zainstalować WiX:" -ForegroundColor Yellow
        Write-Host "    dotnet tool install --global wix" -ForegroundColor Yellow
        Write-Host "    wix extension add WixToolset.UI.wixext --global" -ForegroundColor Yellow
        Write-Host "  Następnie uruchom ponownie ten skrypt." -ForegroundColor Yellow
    }
}

# ── Podsumowanie ──────────────────────────────────────────────────────────
Write-Host ""
Write-Step "Gotowe! Pliki wyjściowe w: $DistDir"
Get-ChildItem $DistDir -Filter "CzlowiekRoku-v$Version*" -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "   $($_.Name)  [$([math]::Round($_.Length/1MB, 1)) MB]" }
