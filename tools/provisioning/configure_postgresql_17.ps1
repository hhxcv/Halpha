[CmdletBinding()]
param(
    [string]$RepositoryRoot = '',
    [string]$InstallRoot = 'D:\Environment\PostgreSQL\17.10',
    [string]$ServiceName = 'postgresql-x64-17'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepositoryRoot = (Resolve-Path (Join-Path $scriptDirectory '..\..')).Path
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'ADMINISTRATOR_TOKEN_REQUIRED'
}

$keyring = Join-Path $RepositoryRoot '.venv\Scripts\keyring.exe'
$psql = Join-Path $InstallRoot 'bin\psql.exe'
$pgIsReady = Join-Path $InstallRoot 'bin\pg_isready.exe'
foreach ($required in ($keyring, $psql, $pgIsReady)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "REQUIRED_COMMAND_MISSING path=$required"
    }
}

$secret = & $keyring get 'Halpha/PostgreSQL/Instance' 'postgres_superuser'
if ([string]::IsNullOrWhiteSpace($secret)) {
    throw 'POSTGRESQL_SUPERUSER_REFERENCE_MISSING'
}

$passFile = Join-Path $env:TEMP 'halpha-postgresql-maintenance.pgpass'
try {
    New-Item -ItemType File -Path $passFile -Force | Out-Null
    & icacls.exe $passFile /inheritance:r /grant:r "$($identity.Name):(F)" 'SYSTEM:(F)' 'Administrators:(F)' | Out-Null
    Set-Content -LiteralPath $passFile -Value "127.0.0.1:5432:postgres:postgres:$secret" -Encoding ascii
    $env:PGPASSFILE = $passFile

    $configurationCommands = @(
        "ALTER SYSTEM SET listen_addresses TO '127.0.0.1,::1'"
        "ALTER SYSTEM SET timezone TO 'UTC'"
        "ALTER SYSTEM SET password_encryption TO 'scram-sha-256'"
    )
    foreach ($configurationCommand in $configurationCommands) {
        & $psql --no-psqlrc --no-password --host 127.0.0.1 --port 5432 --username postgres --dbname postgres --set ON_ERROR_STOP=1 --command $configurationCommand
        if ($LASTEXITCODE -ne 0) {
            throw "POSTGRESQL_CONFIGURATION_FAILED exit=$LASTEXITCODE"
        }
    }

    Restart-Service -Name $ServiceName
    $service = Get-Service -Name $ServiceName
    $service.WaitForStatus(
        [System.ServiceProcess.ServiceControllerStatus]::Running,
        [TimeSpan]::FromSeconds(30)
    )
    & $pgIsReady --host 127.0.0.1 --port 5432 --timeout 5
    if ($LASTEXITCODE -ne 0) {
        throw "POSTGRESQL_READINESS_FAILED exit=$LASTEXITCODE"
    }

    $query = "SELECT current_setting('server_version'), current_setting('listen_addresses'), current_setting('timezone'), current_setting('password_encryption')"
    $settings = & $psql --no-psqlrc --no-password --tuples-only --no-align --field-separator '|' --host 127.0.0.1 --port 5432 --username postgres --dbname postgres --set ON_ERROR_STOP=1 --command $query
    if ($LASTEXITCODE -ne 0) {
        throw "POSTGRESQL_CONFIGURATION_VERIFICATION_FAILED exit=$LASTEXITCODE"
    }
    $values = ($settings.Trim() -split '\|')
    if ($values.Count -ne 4) {
        throw 'POSTGRESQL_CONFIGURATION_VERIFICATION_SHAPE_INVALID'
    }
    [pscustomobject]@{
        status = 'CONFIGURED'
        server_version = $values[0]
        listen_addresses = $values[1]
        timezone = $values[2]
        password_encryption = $values[3]
        credential_transport = 'RESTRICTED_TEMPORARY_PGPASSFILE'
        runtime_secret_environment_variable = $false
    } | ConvertTo-Json -Compress
}
finally {
    $secret = $null
    Remove-Item Env:PGPASSFILE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $passFile) {
        Remove-Item -LiteralPath $passFile -Force
    }
}
