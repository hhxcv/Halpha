param(
    [string]$BaseInterpreter = 'D:\Environment\python313\python.exe',
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$venvRoot = Join-Path $repositoryRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$lockFile = Join-Path $repositoryRoot 'requirements\b00.txt'
$verifier = Join-Path $PSScriptRoot 'verify_venv.py'
$officialIndex = 'https://pypi.org/simple'

if (-not (Test-Path -LiteralPath $BaseInterpreter -PathType Leaf)) {
    throw 'BASE_INTERPRETER_NOT_FOUND'
}

$version = (& $BaseInterpreter -c 'import platform; print(platform.python_version())').Trim()
if ($LASTEXITCODE -ne 0 -or $version -ne '3.13.14') {
    throw 'BASE_INTERPRETER_VERSION_MISMATCH'
}

if (-not (Test-Path -LiteralPath $lockFile -PathType Leaf)) {
    throw 'B00_LOCK_NOT_FOUND'
}

if ($Rebuild -and (Test-Path -LiteralPath $venvRoot)) {
    $venvParent = Split-Path -Parent $venvRoot
    $venvLeaf = Split-Path -Leaf $venvRoot
    if ($venvParent -ne $repositoryRoot -or $venvLeaf -ne '.venv') {
        throw 'UNSAFE_VENV_REMOVE_TARGET'
    }
    Remove-Item -LiteralPath $venvRoot -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $BaseInterpreter -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'VENV_CREATION_FAILED'
    }
}

# Ignore machine/user pip configuration so the lock is always resolved from the
# documented source and never silently weakened by a trusted-host setting.
$env:PIP_CONFIG_FILE = 'NUL'
$env:PIP_INDEX_URL = $officialIndex
Remove-Item Env:PIP_EXTRA_INDEX_URL -ErrorAction SilentlyContinue
Remove-Item Env:PIP_TRUSTED_HOST -ErrorAction SilentlyContinue

& $venvPython -m pip install `
    --require-hashes `
    --only-binary=:all: `
    --index-url $officialIndex `
    --requirement $lockFile
if ($LASTEXITCODE -ne 0) {
    throw 'B00_HASH_LOCK_INSTALL_FAILED'
}

& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) {
    throw 'B00_DEPENDENCY_CHECK_FAILED'
}

& $venvPython $verifier
if ($LASTEXITCODE -ne 0) {
    throw 'VENV_QUALIFICATION_FAILED'
}
