$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$AppName = "PhotoTriageAI"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$PackageDir = Join-Path $DistDir $AppName
$ZipPath = Join-Path $DistDir "$AppName-windows-portable.zip"

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --distpath $DistDir `
    --workpath $BuildDir `
    --add-data "i18n;i18n" `
    app.py

Copy-Item -LiteralPath "README.md" -Destination $PackageDir
Copy-Item -LiteralPath "LICENSE" -Destination $PackageDir
Copy-Item -LiteralPath "start-triage-server.example.bat" -Destination $PackageDir
Copy-Item -LiteralPath "requirements.txt" -Destination $PackageDir
Copy-Item -LiteralPath "requirements-raw.txt" -Destination $PackageDir

Compress-Archive -LiteralPath "$PackageDir\*" -DestinationPath $ZipPath -Force

Write-Host "Portable package created: $ZipPath"
