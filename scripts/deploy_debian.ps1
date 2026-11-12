param(
    [string]$Server,
    [string]$IdentityFile,
    [string]$RdsHost
)

$ErrorActionPreference = 'Stop'
if (-not $Server) { $Server = (Read-Host 'IP publica o nombre DNS de la EC2 Debian').Trim() }
if (-not $RdsHost) { $RdsHost = (Read-Host 'Endpoint de RDS').Trim() }
if ($Server -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$' -or
    $RdsHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') {
    throw 'Escribe las direcciones de EC2 y RDS sin esquema ni puerto.'
}

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $env:USERPROFILE 'Downloads\ClavesServer1.pem'
    if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
        $IdentityFile = Read-Host 'Ruta de ClavesServer1.pem o de la carpeta que lo contiene'
    }
}
$IdentityFile = ([string]$IdentityFile).Trim().Trim('"')
if (-not $IdentityFile) { throw 'Indica la ruta de la llave SSH.' }
if (Test-Path -LiteralPath $IdentityFile -PathType Container) {
    $IdentityFile = Join-Path $IdentityFile 'ClavesServer1.pem'
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "No se encontro la llave SSH en: $IdentityFile. Indica la ruta exacta del archivo .pem."
}
$key = (Get-Item -LiteralPath $IdentityFile).FullName
$sshOptions = @('-o', 'IdentitiesOnly=yes', '-i', $key)
$target = "admin@$Server"
$project = Split-Path -Parent $PSScriptRoot
$bundle = [IO.Path]::GetTempFileName()
$remote = $null

try {
    & tar.exe -czf $bundle --exclude=__pycache__ --exclude='*.pyc' -C $project app requirements.txt control-iot/assets/favicon/excavadora-192.png
    if ($LASTEXITCODE) { throw 'No se pudo preparar el paquete de FastAPI.' }

    $remote = & ssh.exe @sshOptions $target 'mktemp -d /tmp/vehiculo-iot.XXXXXXXXXX'
    if ($LASTEXITCODE -or $remote -notmatch '^/tmp/vehiculo-iot\.[A-Za-z0-9]+$') {
        $remote = $null
        throw 'No se pudo preparar la carga en Debian. Revisa la conexion SSH.'
    }

    & scp.exe @sshOptions $bundle "${target}:$remote/api.tgz"
    if ($LASTEXITCODE) { throw 'Fallo la carga del codigo.' }

    & scp.exe @sshOptions (Join-Path $PSScriptRoot 'deploy_debian.sh') "${target}:$remote/deploy.sh"
    if ($LASTEXITCODE) { throw 'Fallo la carga del instalador.' }

    & ssh.exe -tt @sshOptions $target "tr -d '\r' < '$remote/deploy.sh' | sudo bash -s -- '$remote/api.tgz' '$RdsHost'"
    if ($LASTEXITCODE) { throw 'Debian devolvio un error de instalacion. Revisa la salida anterior.' }
} finally {
    Remove-Item -LiteralPath $bundle -ErrorAction SilentlyContinue
    if ($remote) {
        & ssh.exe -o BatchMode=yes -o ConnectTimeout=5 @sshOptions $target "rm -f -- '$remote/api.tgz' '$remote/deploy.sh'; rmdir -- '$remote'" | Out-Null
    }
}
