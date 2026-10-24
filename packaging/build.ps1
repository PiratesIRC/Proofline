# Build dist\Proofline\ (one-folder app) and dist\Proofline-<version>.zip.
# Run from anywhere:  .\packaging\build.ps1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Name = 'Proofline'

if (-not (Test-Path $Python)) { throw "No virtual environment at $Python. See docs/DEVELOPMENT.md." }
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is missing: $Python -m pip install -r requirements-build.txt" }

Push-Location $Root
try {
    # comtypes writes its UIAutomation wrappers on first import; make sure they exist to bundle.
    & $Python -c "import uiautomation" ; if ($LASTEXITCODE -ne 0) { throw 'Could not import uiautomation' }
    & $Python packaging\make_icon.py build\app.ico ; if ($LASTEXITCODE -ne 0) { throw 'Icon build failed' }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\$Name.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

    $Version = & $Python -c "import proofline; print(proofline.__version__)"
    $Zip = Join-Path $Root "dist\$Name-$Version.zip"
    if (Test-Path $Zip) { Remove-Item $Zip }
    Compress-Archive -Path (Join-Path $Root "dist\$Name") -DestinationPath $Zip
    Write-Host "Built $Zip"
}
finally {
    Pop-Location
}
