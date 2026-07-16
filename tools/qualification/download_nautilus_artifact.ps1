param(
    [string]$Destination = ''
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$venvPython = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$verifier = Join-Path $PSScriptRoot 'verify_nautilus_artifact.py'
if (-not $Destination) {
    $Destination = Join-Path $repositoryRoot 'build\qualification\wheels'
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw 'VENV_REQUIRED'
}
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$env:PIP_CONFIG_FILE = 'NUL'
$env:PIP_INDEX_URL = 'https://pypi.org/simple'
Remove-Item Env:PIP_EXTRA_INDEX_URL -ErrorAction SilentlyContinue
Remove-Item Env:PIP_TRUSTED_HOST -ErrorAction SilentlyContinue

& $venvPython -m pip download `
    --no-deps `
    --only-binary=:all: `
    --index-url https://pypi.org/simple `
    --dest $Destination `
    nautilus-trader==1.230.0
if ($LASTEXITCODE -ne 0) {
    throw 'NAUTILUS_WHEEL_DOWNLOAD_FAILED'
}

$wheel = Join-Path $Destination 'nautilus_trader-1.230.0-cp313-cp313-win_amd64.whl'
& $venvPython $verifier --wheel $wheel
if ($LASTEXITCODE -ne 0) {
    throw 'NAUTILUS_WHEEL_QUALIFICATION_FAILED'
}
