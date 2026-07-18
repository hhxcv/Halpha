[CmdletBinding()]
param(
    [string]$RepositoryRoot = '',
    [string]$InstallRoot = 'D:\Environment\PostgreSQL\17.10',
    [string]$DataRoot = 'D:\HalphaData\PostgreSQL\17'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepositoryRoot = (Resolve-Path (Join-Path $scriptDirectory '..\..')).Path
}

$InstallerUrl = 'https://get.enterprisedb.com/postgresql/postgresql-17.10-2-windows-x64.exe'
$InstallerSha256 = '81554536268e499f431efa3fa20736736c64102c719308a03ceb32aa0cb6ae06'
$ServiceName = 'postgresql-x64-17'
$VaultService = 'Halpha/PostgreSQL/Instance'
$VaultAccount = 'postgres_superuser'
$ServiceAccount = 'NT AUTHORITY\NetworkService'

function Assert-Elevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'ADMINISTRATOR_TOKEN_REQUIRED'
    }
}

function Get-RepositoryCommand([string]$RelativePath) {
    $path = Join-Path $RepositoryRoot $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "REPOSITORY_COMMAND_MISSING path=$RelativePath"
    }
    return $path
}

Assert-Elevated
$python = Get-RepositoryCommand '.venv\Scripts\python.exe'
$keyring = Get-RepositoryCommand '.venv\Scripts\keyring.exe'
Write-Output 'stage=PRECHECK_COMPLETE'

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -ne $existingService) {
    $postgres = Join-Path $InstallRoot 'bin\postgres.exe'
    if (-not (Test-Path -LiteralPath $postgres -PathType Leaf)) {
        throw 'POSTGRESQL_SERVICE_PRESENT_BUT_BINARY_MISSING'
    }
    $version = & $postgres --version
    if ($version -notmatch '17\.10') {
        throw "POSTGRESQL_VERSION_MISMATCH actual=$version"
    }
    & icacls.exe $InstallRoot /grant 'NETWORK SERVICE:(OI)(CI)(RX)' /T | Out-Null
    $identityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe (Join-Path $DataRoot '*') /grant:r "${identityName}:(F)" 'NETWORK SERVICE:(F)' 'SYSTEM:(F)' 'Administrators:(F)' /T /C | Out-Null
    if ($existingService.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running) {
        Start-Service -Name $ServiceName
        $existingService.WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Running,
            [TimeSpan]::FromSeconds(30)
        )
    }
    $pgIsReady = Join-Path $InstallRoot 'bin\pg_isready.exe'
    & $pgIsReady --host 127.0.0.1 --port 5432 --timeout 5
    if ($LASTEXITCODE -ne 0) {
        throw "POSTGRESQL_READINESS_FAILED exit=$LASTEXITCODE"
    }
    $existingService.Refresh()
    [pscustomobject]@{
        status = 'ALREADY_INSTALLED'
        service = $ServiceName
        service_status = $existingService.Status.ToString()
        install_root = $InstallRoot
        version = $version
    } | ConvertTo-Json -Compress
    exit 0
}

$downloadRoot = Join-Path $env:TEMP 'halpha-postgresql-download'
$installer = Join-Path $downloadRoot 'postgresql-17.10-2-windows-x64.exe'
New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $installer
}
$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
if ($actualSha256 -ne $InstallerSha256) {
    throw 'POSTGRESQL_INSTALLER_CHECKSUM_MISMATCH'
}
Write-Output 'stage=INSTALLER_VERIFIED'

$postgres = Join-Path $InstallRoot 'bin\postgres.exe'
$requiredLibrary = Join-Path $InstallRoot 'lib\dict_snowball.dll'
if (
    -not (Test-Path -LiteralPath $postgres -PathType Leaf) -or
    -not (Test-Path -LiteralPath $requiredLibrary -PathType Leaf)
) {
    Write-Output 'stage=BINARY_EXTRACTION_STARTING'
    & $installer --mode unattended --unattendedmodeui none --extract-only 1 --prefix $InstallRoot
    if (
        -not (Test-Path -LiteralPath $postgres -PathType Leaf) -or
        -not (Test-Path -LiteralPath $requiredLibrary -PathType Leaf)
    ) {
        throw 'POSTGRESQL_BINARY_EXTRACTION_FAILED'
    }
}
Write-Output 'stage=POSTGRESQL_BINARY_READY'

$initdb = Join-Path $InstallRoot 'bin\initdb.exe'
$pgCtl = Join-Path $InstallRoot 'bin\pg_ctl.exe'
$pgIsReady = Join-Path $InstallRoot 'bin\pg_isready.exe'
$clusterVersion = Join-Path $DataRoot 'PG_VERSION'
if ((Test-Path -LiteralPath $DataRoot) -and -not (Test-Path -LiteralPath $clusterVersion)) {
    $unexpected = Get-ChildItem -LiteralPath $DataRoot -Force -ErrorAction SilentlyContinue
    if ($null -ne $unexpected) {
        throw 'POSTGRESQL_DATA_DIRECTORY_NONEMPTY_WITHOUT_CLUSTER_IDENTITY'
    }
}
if (-not (Test-Path -LiteralPath $DataRoot)) {
    New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
}
$identityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $DataRoot /inheritance:r /grant:r "${identityName}:(OI)(CI)(F)" 'NETWORK SERVICE:(OI)(CI)(F)' 'SYSTEM:(OI)(CI)(F)' 'Administrators:(OI)(CI)(F)' /T | Out-Null
Write-Output 'stage=EMPTY_DATA_ACL_APPLIED'

$provisionSecret = @'
import keyring
import secrets
import string

service = "Halpha/PostgreSQL/Instance"
account = "postgres_superuser"
value = keyring.get_password(service, account)
if not value:
    alphabet = string.ascii_letters + string.digits + "-_!@#%"
    value = "H!" + "".join(secrets.choice(alphabet) for _ in range(38)) + "9z"
    keyring.set_password(service, account, value)
print("WINVAULT_REFERENCE_READY")
'@
$provisionResult = $provisionSecret | & $python -
if ($provisionResult -ne 'WINVAULT_REFERENCE_READY') {
    throw 'POSTGRESQL_INSTALL_SECRET_PROVISION_FAILED'
}
Write-Output 'stage=WINVAULT_REFERENCE_READY'

$secret = & $keyring get $VaultService $VaultAccount
if ([string]::IsNullOrWhiteSpace($secret)) {
    throw 'POSTGRESQL_INSTALL_SECRET_READ_FAILED'
}

$passwordFile = Join-Path $env:TEMP 'halpha-postgresql-initdb.pwfile'

try {
    if (-not (Test-Path -LiteralPath $clusterVersion -PathType Leaf)) {
        Set-Content -LiteralPath $passwordFile -Value $secret -Encoding ascii -NoNewline
        $identityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $passwordFile /inheritance:r /grant:r "${identityName}:(F)" 'SYSTEM:(F)' 'Administrators:(F)' | Out-Null
        Write-Output 'stage=CLUSTER_INITIALIZATION_STARTING'
        & $initdb --pgdata $DataRoot --username postgres --pwfile $passwordFile --auth-host scram-sha-256 --auth-local scram-sha-256 --encoding UTF8 --locale C
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $clusterVersion -PathType Leaf)) {
            throw "POSTGRESQL_INITDB_FAILED exit=$LASTEXITCODE"
        }
    }
}
finally {
    $secret = $null
    if (Test-Path -LiteralPath $passwordFile) {
        Remove-Item -LiteralPath $passwordFile -Force
    }
}

& icacls.exe $DataRoot /inheritance:r /grant:r "${identityName}:(OI)(CI)(F)" 'NETWORK SERVICE:(OI)(CI)(F)' 'SYSTEM:(OI)(CI)(F)' 'Administrators:(OI)(CI)(F)' /T | Out-Null
& icacls.exe (Join-Path $DataRoot '*') /grant:r "${identityName}:(F)" 'NETWORK SERVICE:(F)' 'SYSTEM:(F)' 'Administrators:(F)' /T /C | Out-Null
& icacls.exe $InstallRoot /grant 'NETWORK SERVICE:(OI)(CI)(RX)' /T | Out-Null
Write-Output 'stage=DATA_ACL_APPLIED'

& $pgCtl register -N $ServiceName -D $DataRoot -S auto -U $ServiceAccount
if ($LASTEXITCODE -ne 0) {
    throw "POSTGRESQL_SERVICE_REGISTRATION_FAILED exit=$LASTEXITCODE"
}
$service = Get-Service -Name $ServiceName
Start-Service -Name $ServiceName
$service.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(30))
& $pgIsReady --host 127.0.0.1 --port 5432 --timeout 5
if ($LASTEXITCODE -ne 0) {
    throw "POSTGRESQL_READINESS_FAILED exit=$LASTEXITCODE"
}

$service = Get-Service -Name $ServiceName
$version = & $postgres --version
if ($version -notmatch '17\.10') {
    throw "POSTGRESQL_VERSION_MISMATCH actual=$version"
}
[pscustomobject]@{
    status = 'INSTALLED'
    installer_sha256 = $actualSha256
    service = $ServiceName
    service_status = $service.Status.ToString()
    install_root = $InstallRoot
    data_root = $DataRoot
    version = $version
    service_account = $ServiceAccount
    secret_storage = 'WINVAULT_REFERENCE_ONLY'
} | ConvertTo-Json -Compress
