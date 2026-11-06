<#
Local Postgres + RustFS (S3) for the backend, without Docker and without admin rights.

    .\scripts\services.ps1 install   # once: Postgres 18.6 + RustFS 1.0.4 (~450 MB download)
    .\scripts\services.ps1 start     # both in the background; the first start creates the database
    .\scripts\services.ps1 status
    .\scripts\services.ps1 stop
    .\scripts\services.ps1 psql      # SQL shell on the "safety" database
    .\scripts\services.ps1 reset     # drop and recreate the database (no migrations yet)

Everything lives in %LOCALAPPDATA%\safety-reviewer, outside the repo: OneDrive must not sync database
files. Both listen on 127.0.0.1 only. The phone gets clips through the backend (GET /api/v1/media/...),
so no firewall rule is needed. With Docker, use backend/docker-compose.yml instead (same ports and keys).
#>
param(
    [ValidateSet("install", "start", "stop", "status", "psql", "reset")]
    [string]$Command = "status"
)

$Root = Join-Path $env:LOCALAPPDATA "safety-reviewer"
$PgVersion = "18.6-1"
$RustfsVersion = "1.0.4"
$PgUrl = "https://get.enterprisedb.com/postgresql/postgresql-$PgVersion-windows-x64-binaries.zip"
$RustfsUrl = "https://github.com/rustfs/rustfs/releases/download/$RustfsVersion/rustfs-windows-x86_64-v$RustfsVersion.zip"
$PgZip = Join-Path $Root "downloads\pg\postgresql-$PgVersion-windows-x64-binaries.zip"
$RustfsZip = Join-Path $Root "downloads\rustfs\rustfs-windows-x86_64-v$RustfsVersion.zip"

$PgBin = Join-Path $Root "pgsql\bin"
$PgData = Join-Path $Root "data\postgres"
$RustfsExe = Join-Path $Root "rustfs\rustfs.exe"
$RustfsData = Join-Path $Root "data\rustfs"
$Logs = Join-Path $Root "logs"

# Same values as the defaults in backend/app/core/config.py and in docker-compose.yml.
# Port 5433, not 5432: a system-wide Postgres install often holds 5432 already.
$DbUser = "safety"; $DbName = "safety"; $DbPort = 5433
$S3Port = 9000; $ConsolePort = 9001
$S3AccessKey = "safety"; $S3SecretKey = "safety-secret"

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return $client.ConnectAsync("127.0.0.1", $Port).Wait(500) } catch { return $false } finally { $client.Dispose() }
}

function Wait-Port([int]$Port, [string]$Name, [string]$Log) {
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Port $Port) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not start on port $Port, see $Log"
}

# Short-lived tools only. stderr is folded into the output, so Windows PowerShell doesn't turn it into errors.
function Invoke-Tool([string]$Exe, [string[]]$Arguments) {
    $output = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "$(Split-Path $Exe -Leaf) failed:`n$($output -join "`n")" }
    return $output
}

function Get-Download([string]$Url, [string]$Path) {
    if (Test-Path $Path) { return }
    New-Item -ItemType Directory -Force (Split-Path $Path) | Out-Null
    Write-Host "Downloading $Url"
    curl.exe -fL --retry 3 -o "$Path.part" $Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
    Move-Item "$Path.part" $Path
}

function Install-Services {
    Get-Download $PgUrl $PgZip
    Get-Download $RustfsUrl $RustfsZip
    if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) {
        Write-Host "Unpacking Postgres (without pgAdmin and docs)"
        tar.exe -xf $PgZip -C $Root --exclude "pgsql/pgAdmin 4" --exclude "pgsql/doc" --exclude "pgsql/StackBuilder" --exclude "pgsql/include" --exclude "pgsql/symbols"
        if ($LASTEXITCODE -ne 0) { throw "Unpacking Postgres failed" }
    }
    if (-not (Test-Path $RustfsExe)) {
        Write-Host "Unpacking RustFS"
        $unpack = Join-Path $Root "rustfs-unpack"
        New-Item -ItemType Directory -Force $unpack | Out-Null
        tar.exe -xf $RustfsZip -C $unpack
        $exe = Get-ChildItem $unpack -Recurse -Filter "rustfs.exe" | Select-Object -First 1
        if (-not $exe) { throw "rustfs.exe not found in $RustfsZip" }
        New-Item -ItemType Directory -Force (Split-Path $RustfsExe) | Out-Null
        Move-Item $exe.FullName $RustfsExe
        Remove-Item -Recurse -Force $unpack
    }
    Write-Host "Installed in $Root"
}

function Start-Postgres {
    if (Test-Port $DbPort) { Write-Host "Postgres  already running on 127.0.0.1:$DbPort"; return }
    if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) { throw "Postgres is not installed: run '.\scripts\services.ps1 install' first" }
    if (-not (Test-Path (Join-Path $PgData "PG_VERSION"))) {
        Write-Host "Creating the database cluster in $PgData"
        Invoke-Tool (Join-Path $PgBin "initdb.exe") @("-D", $PgData, "-U", $DbUser, "-A", "trust", "-E", "UTF8", "--no-locale") | Out-Null
    }
    $log = Join-Path $Logs "postgres.log"
    # Start-Process without redirection: the server must not inherit this shell's output handles.
    Start-Process -FilePath (Join-Path $PgBin "pg_ctl.exe") -WindowStyle Hidden -ArgumentList @(
        "-D", "`"$PgData`"", "-l", "`"$log`"", "-o", "`"-p $DbPort -c listen_addresses=127.0.0.1`"", "start"
    ) | Out-Null
    Wait-Port $DbPort "Postgres" $log
    for ($i = 0; $i -lt 20; $i++) {  # the port opens a moment before connections are accepted
        & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $DbPort -q
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
    $exists = Invoke-Tool (Join-Path $PgBin "psql.exe") @("-h", "127.0.0.1", "-p", $DbPort, "-U", $DbUser, "-d", "postgres", "-tAc", "SELECT 1 FROM pg_database WHERE datname = '$DbName'")
    if ("$exists".Trim() -ne "1") {
        Invoke-Tool (Join-Path $PgBin "createdb.exe") @("-h", "127.0.0.1", "-p", $DbPort, "-U", $DbUser, $DbName) | Out-Null
    }
    Write-Host "Postgres  127.0.0.1:$DbPort  database '$DbName', user '$DbUser' (local only, no password)"
}

function Start-RustFS {
    if (Test-Port $S3Port) { Write-Host "S3        already running on 127.0.0.1:$S3Port"; return }
    if (-not (Test-Path $RustfsExe)) { throw "RustFS is not installed: run '.\scripts\services.ps1 install' first" }
    New-Item -ItemType Directory -Force $RustfsData | Out-Null
    $log = Join-Path $Logs "rustfs.log"
    $env:RUSTFS_ACCESS_KEY = $S3AccessKey
    $env:RUSTFS_SECRET_KEY = $S3SecretKey
    # cmd writes the log; Start-Process without redirection keeps this shell's handles out of the server.
    $server = "`"$RustfsExe`" server --address 127.0.0.1:$S3Port --console-enable --console-address 127.0.0.1:$ConsolePort `"$RustfsData`""
    Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -ArgumentList "/d /c `"$server > `"$log`" 2>&1`"" | Out-Null
    Wait-Port $S3Port "RustFS" $log
    Write-Host "RustFS    http://127.0.0.1:$S3Port (S3)  console http://127.0.0.1:$ConsolePort  key '$S3AccessKey' / '$S3SecretKey'"
}

function Stop-Services {
    if (Test-Path (Join-Path $PgData "postmaster.pid")) {
        & (Join-Path $PgBin "pg_ctl.exe") -D $PgData -m fast -w stop | Out-Null
    }
    Get-Process rustfs -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $RustfsExe } | Stop-Process -Force
    Write-Host "Stopped"
}

function Show-Status {
    $pg = if (Test-Port $DbPort) { "running" } else { "stopped" }
    $s3 = if (Test-Port $S3Port) { "running" } else { "stopped" }
    Write-Host "Postgres  127.0.0.1:$DbPort  $pg"
    Write-Host "RustFS    127.0.0.1:$S3Port  $s3   (console http://127.0.0.1:$ConsolePort)"
    Write-Host "Data      $Root"
}

New-Item -ItemType Directory -Force $Logs | Out-Null
try {
    switch ($Command) {
        "install" { Install-Services }
        "start" { Start-Postgres; Start-RustFS }
        "stop" { Stop-Services }
        "status" { Show-Status }
        "psql" { & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $DbPort -U $DbUser $DbName }
        "reset" {
            Invoke-Tool (Join-Path $PgBin "dropdb.exe") @("-h", "127.0.0.1", "-p", $DbPort, "-U", $DbUser, "--force", "--if-exists", $DbName) | Out-Null
            Invoke-Tool (Join-Path $PgBin "createdb.exe") @("-h", "127.0.0.1", "-p", $DbPort, "-U", $DbUser, $DbName) | Out-Null
            Write-Host "Database '$DbName' is empty again; the backend creates the tables on its next start"
        }
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
