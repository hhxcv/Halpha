param(
    [string]$BaseInterpreter = ''
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$venvRoot = Join-Path $repositoryRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$verifier = Join-Path $PSScriptRoot 'verify_venv.py'

if ([string]::IsNullOrWhiteSpace($BaseInterpreter)) {
    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw 'BASE_INTERPRETER_NOT_FOUND'
    }
    $BaseInterpreter = $pythonCommand.Source
}
if (-not (Test-Path -LiteralPath $BaseInterpreter -PathType Leaf)) {
    throw "BASE_INTERPRETER_NOT_FOUND"
}

$version = (& $BaseInterpreter -c 'import platform; print(platform.python_version())').Trim()
if ($LASTEXITCODE -ne 0 -or $version -ne '3.13.14') {
    throw "BASE_INTERPRETER_VERSION_MISMATCH"
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $BaseInterpreter -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "VENV_CREATION_FAILED"
    }
}

& $venvPython $verifier
if ($LASTEXITCODE -ne 0) {
    throw "VENV_QUALIFICATION_FAILED"
}
