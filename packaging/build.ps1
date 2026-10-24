# Build the two release files:
#   dist\Proofline-<version>-portable.zip   unzip and run; settings stay in a data folder beside the exe
#   dist\Proofline-<version>-setup.exe      per-user installer (Inno Setup 6)
# Run in its own PowerShell process:  powershell -File packaging\build.ps1 [-SkipInstaller]
# (PyInstaller logs to stderr; under a 2>&1 redirect that would stop this script.)
param([switch]$SkipInstaller)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Name = 'Proofline'
$IsccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe')
)
$PortableNote = @"
This copy of Proofline is portable: settings, logs and usage files are kept in the
"data" folder next to Proofline.exe instead of %LOCALAPPDATA%\Proofline.
Delete this file to make the copy use %LOCALAPPDATA%\Proofline like an installed one.
"@

if (-not (Test-Path $Python)) { throw "No virtual environment at $Python. See docs/DEVELOPMENT.md." }
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is missing: $Python -m pip install -r requirements-build.txt" }
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $SkipInstaller -and -not $Iscc) {
    throw 'Inno Setup 6 is missing: winget install --id JRSoftware.InnoSetup -e --scope user (or use -SkipInstaller)'
}

Push-Location $Root
try {
    # comtypes writes its UIAutomation wrappers on first import; make sure they exist to bundle.
    & $Python -c "import uiautomation" ; if ($LASTEXITCODE -ne 0) { throw 'Could not import uiautomation' }
    & $Python packaging\make_icon.py build\app.ico ; if ($LASTEXITCODE -ne 0) { throw 'Icon build failed' }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\$Name.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $Version = & $Python -c "import proofline; print(proofline.__version__)"
    # GPL-3.0: binary releases carry the license text and the third-party notices.
    Copy-Item (Join-Path $Root 'LICENSE') (Join-Path $Root "dist\$Name\LICENSE.txt")
    Copy-Item (Join-Path $PSScriptRoot 'THIRD-PARTY-NOTICES.txt') (Join-Path $Root "dist\$Name\THIRD-PARTY-NOTICES.txt")

    # Portable: the app folder plus the marker that keeps its data beside the exe.
    $Stage = Join-Path $Root 'build\portable'
    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force $Stage | Out-Null
    Copy-Item (Join-Path $Root "dist\$Name") $Stage -Recurse
    Set-Content -Path (Join-Path $Stage "$Name\portable.txt") -Value $PortableNote -Encoding ascii
    $Zip = Join-Path $Root "dist\$Name-$Version-portable.zip"
    if (Test-Path $Zip) { Remove-Item $Zip }
    Compress-Archive -Path (Join-Path $Stage $Name) -DestinationPath $Zip
    Write-Host "Built $Zip"

    if (-not $SkipInstaller) {
        & $Iscc /Qp "/DAppVersion=$Version" packaging\$Name.iss
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
        Write-Host "Built $(Join-Path $Root "dist\$Name-$Version-setup.exe")"
    }
}
finally {
    Pop-Location
}
