<#
Ceo sistem u Docker-u, jednom komandom: auto (koordinator + model + kamera), server (+ Postgres + RustFS) i dashboard,
svaki deo u svom kontejneru (docker-compose.yml -> docker/car.yml, docker/server.yml, docker/dashboard.yml).
Skripta sama: instalira i pokrece Docker Desktop ako treba, nadje dataset, upise docker/.env (IP laptopa, klipovi),
izgradi i pokrene kontejnere, saceka da se svi jave, pa na samom laptopu pokrene ono sto ne moze u Docker:
Bluetooth gateway (radio laptopa) i adb reverse za telefon preko USB-a. Uputstvo: DOCKER.md.

    .\start.ps1                                  # sve (prvi put traje ~10 min: preuzimanje i izgradnja)
    .\start.ps1 -Dataset "D:\Hackathon dataset 2026"   # gde su klipovi (zapamti se u docker/.env)
    .\start.ps1 -CameraMode loop -Video 05_23_62_031246_video_inCabin.mp4   # jedan klip u petlji
    .\start.ps1 -CameraMode test                 # bez dataseta: test slika
    .\start.ps1 -Status                          # sta radi
    .\start.ps1 -Logs                            # logovi svih kontejnera (Ctrl+C izlaz); -Logs -Service model
    .\start.ps1 -Stop                            # ugasi sve (podaci ostaju)
    .\start.ps1 -Reset                           # ugasi sve i obrisi bazu i slike (posle promene tabela)

-Camera      zona vozaca modela: 05_23 ili 08_14 (podrazumevano po klipovima)
-Clips       klipovi za -CameraMode per-trip (svaka voznja = sledeci), npr. 05_23_62_031246 05_23_62_022338
-Speed       scenario brzine: city, highway, stop_and_go, country_road, cruise (podrazumevano), parked, random
-NoBle       bez Bluetooth gateway-a (telefon se vezuje za auto preko Wi-Fi/USB: <IP>:8000)
-NoAdb       bez adb reverse (telefon preko hotspota umesto USB-a)
-NoBrowser   ne otvaraj dashboard u browseru
#>
param(
    [string]$Dataset = "",
    [ValidateSet("", "05_23", "08_14")] [string]$Camera = "",
    [ValidateSet("per-trip", "loop", "test", "off")] [string]$CameraMode = "per-trip",
    [string[]]$Clips = @(),
    [string]$Video = "",
    [string]$Speed = "cruise",
    [string]$CarName = "Rivian demo car",
    [int]$CoordinatorPort = 8000,
    [int]$ServerPort = 8001,
    [int]$DashboardPort = 5173,
    [switch]$NoBle,
    [switch]$NoAdb,
    [switch]$NoBrowser,
    [switch]$Stop,
    [switch]$Reset,
    [switch]$Status,
    [switch]$Logs,
    [string]$Service = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$EnvFile = Join-Path $Root "docker\.env"
$DefaultClips = @("05_23_62_031246", "05_23_62_021254", "05_23_62_005853")   # kolaps, telefon, telefon u krilu
$DockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$DockerBin = "C:\Program Files\Docker\Docker\resources\bin"

function Say([string]$Text, [string]$Color = "Gray") { Write-Host $Text -ForegroundColor $Color }
function Ok([string]$Text) { Say "  [ok] $Text" Green }
function Warn([string]$Text) { Say "  [!!] $Text" Yellow }
function Fail([string]$Text) { Say "`n  [xx] $Text`n" Red; exit 1 }

# docker / compose write progress to stderr; in PowerShell 5.1 "Stop" would turn that into an error, so judge by exit code.
function Invoke-Docker([string[]]$DockerArgs, [switch]$Quiet) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($Quiet) { & docker @DockerArgs 2>&1 | Out-Null } else { & docker @DockerArgs 2>&1 | ForEach-Object { "    $_" } | Out-Host }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return $code
}

function Compose([string[]]$ComposeArgs, [switch]$Quiet) {
    Push-Location $Root
    try { return Invoke-Docker (@("compose") + $ComposeArgs) -Quiet:$Quiet } finally { Pop-Location }
}

function Open-Window([string]$Title, [string]$Command) {
    $full = "`$Host.UI.RawUI.WindowTitle = 'rivian: $Title'; Set-Location '$Root'; $Command"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $full | Out-Null
    Ok "prozor 'rivian: $Title'"
}

function Stop-HostWindows {
    $windows = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like "*WindowTitle = 'rivian: *" -and $_.ProcessId -ne $PID }
    foreach ($w in $windows) { taskkill /T /F /PID $w.ProcessId 2>&1 | Out-Null }
    if ($windows) { Ok "zatvoreno prozora 'rivian:': $(@($windows).Count)" }
}

function Wait-Http([string]$Url, [string]$What, [int]$Seconds = 120) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        try { Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 2 | Out-Null; Ok "$What odgovara ($Url)"; return } catch { Start-Sleep -Seconds 1 }
    }
    Fail "$What se nije javio za $Seconds s ($Url). Pogledaj: .\start.ps1 -Logs"
}

function Get-LanIp {
    $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1
    if ($cfg) { return $cfg.IPv4Address.IPAddress }
    return ""
}

function Test-DockerEngine { return (Invoke-Docker @("info") -Quiet) -eq 0 }

# ---------------------------------------------------------------- 1. Docker: instaliran i pokrenut
function Initialize-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $DockerBin)) { $env:Path = "$DockerBin;$env:Path" }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail "Nema Docker-a ni winget-a. Instaliraj Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/ pa pokreni ponovo."
        }
        Say "Docker Desktop nije instaliran: instaliram ga (winget, trazice dozvolu administratora)..." Cyan
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        if (Test-Path $DockerBin) { $env:Path = "$DockerBin;$env:Path" }
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Fail "Docker Desktop je instaliran, ali Windows mora da se restartuje (WSL 2). Posle restarta pokreni .\start.ps1 ponovo."
        }
    }
    if (Test-DockerEngine) { Ok "Docker radi"; return }
    if (-not (Test-Path $DockerExe)) { Fail "Docker komanda postoji, ali Docker Desktop nije na $DockerExe. Pokreni ga rucno pa ponovo." }
    Say "Pokrecem Docker Desktop (prvi put prihvati uslove u njegovom prozoru)..." Cyan
    Start-Process $DockerExe | Out-Null
    for ($i = 0; $i -lt 180; $i += 3) {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) { Ok "Docker radi"; return }
    }
    Fail "Docker Desktop se nije pokrenuo za 3 min. Otvori ga rucno, sacekaj 'Engine running', pa pokreni ponovo."
}

# ---------------------------------------------------------------- komande koje ne pokrecu sistem
if ($Stop -or $Reset) {
    Stop-HostWindows
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        if (Test-DockerEngine) {
            $downArgs = @("down", "--remove-orphans")
            if ($Reset) { $downArgs += "-v" }
            Compose $downArgs | Out-Null
            if ($Reset) { Ok "kontejneri ugaseni, baza i slike obrisane" } else { Ok "kontejneri ugaseni (podaci ostaju)" }
        } else { Ok "Docker ne radi, nema sta da se gasi" }
    }
    return
}
if ($Status) {
    Initialize-Docker
    Compose @("ps", "--format", "table {{.Service}}`t{{.Status}}`t{{.Ports}}") | Out-Null
    try {
        $s = Invoke-RestMethod "http://127.0.0.1:$CoordinatorPort/api/v1/coordinator/status" -TimeoutSec 3
        Say ("  koordinator: voznja={0}  kamera={1} fps  model={2} ({3})  server={4}" -f `
            $(if ($s.trip_id) { $s.trip_id.Substring(0, 8) } else { "-" }), $s.camera.fps, $s.model.connected, $s.model.device, `
            ($s.server | ConvertTo-Json -Compress -Depth 1)) Cyan
    } catch { Warn "koordinator ne odgovara na :$CoordinatorPort" }
    return
}
if ($Logs) {
    Initialize-Docker
    $logArgs = @("logs", "-f", "--tail", "100")
    if ($Service) { $logArgs += $Service }
    Compose $logArgs | Out-Null
    return
}

Say "Rivian: ceo sistem u Docker-u" Cyan
Initialize-Docker

# ---------------------------------------------------------------- 2. stari demo i portovi
$demo = Join-Path $Root "demo.ps1"
if (Test-Path $demo) { & $demo -Stop | Out-Null }   # prozori 'demo: ...' i stari backend bi drzali 8000/8001
Stop-HostWindows

$ourContainers = @()
Push-Location $Root
$old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$ourContainers = @(docker compose ps -q 2>$null)
$ErrorActionPreference = $old
Pop-Location
foreach ($p in @($CoordinatorPort, $ServerPort, $DashboardPort)) {
    foreach ($line in (netsh interface ipv4 show excludedportrange protocol=tcp)) {
        if ($line -match '^\s*(\d+)\s+(\d+)\s*$' -and $p -ge [int]$Matches[1] -and $p -le [int]$Matches[2]) {
            Fail "Windows je rezervisao port $p (Hyper-V/WSL). Jednom, kao administrator: tools\reserve-ports.ps1; ili drugi port (-CoordinatorPort / -ServerPort / -DashboardPort)."
        }
    }
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { continue }
    $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.Name -in @("com.docker.backend", "wslrelay", "vpnkit") -and $ourContainers.Count -gt 0) { continue }   # nasi kontejneri, compose ih menja
    if ($proc -and $proc.Name -in @("com.docker.backend", "wslrelay", "vpnkit")) {
        Fail "Port $p drzi neki drugi Docker kontejner (docker ps). Ugasi ga ili izaberi drugi port."
    }
    $name = if ($proc) { "$($proc.Name) (PID $($proc.Id))" } else { "PID $($c.OwningProcess)" }
    Fail "Port $p drzi $name. Ugasi ga (npr. npm run dev za dashboard) ili izaberi drugi port."
}
Ok "portovi $CoordinatorPort, $ServerPort, $DashboardPort slobodni"

# ---------------------------------------------------------------- 3. dataset, kamera, docker/.env
function Read-EnvFile {
    $values = @{}
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) { if ($line -match '^\s*([A-Z_]+)=(.*)$') { $values[$Matches[1]] = $Matches[2].Trim() } }
    }
    return $values
}
function Test-Dataset([string]$Dir) { return $Dir -and (Test-Path $Dir) -and (Get-ChildItem $Dir -Filter "*_video_inCabin.mp4" -ErrorAction SilentlyContinue | Select-Object -First 1) }

$previous = Read-EnvFile
$parent = Split-Path $Root -Parent
$candidates = @($Dataset, $env:DATASET_DIR, $previous["DATASET_DIR"],
    (Join-Path $parent "dataset"),
    (Join-Path $parent "Hackathon dataset 2026"),
    (Join-Path $parent "Hackathon dataset 2026\Hackathon dataset 2026"),
    (Join-Path $HOME "Downloads\Hackathon dataset 2026\Hackathon dataset 2026"),
    (Join-Path $HOME "Downloads\Hackathon dataset 2026")) | Where-Object { $_ }
if ($Dataset -and -not (Test-Dataset $Dataset)) { Fail "U '$Dataset' nema klipova *_video_inCabin.mp4." }
$datasetDir = ""
foreach ($d in $candidates) { if (Test-Dataset $d) { $datasetDir = (Resolve-Path $d).Path; break } }
if ($datasetDir) {
    Ok "dataset: $datasetDir ($(@(Get-ChildItem $datasetDir -Filter '*_video_inCabin.mp4').Count) klipova)"
} elseif ($CameraMode -in @("per-trip", "loop")) {
    Warn "nema dataseta (klipovi *_video_inCabin.mp4): kamera salje test sliku. Daj ga sa -Dataset <folder>."
}
if ($CameraMode -eq "loop") {
    if (-not $Video) { Fail "-CameraMode loop trazi -Video <ime klipa iz dataseta>." }
    $Video = Split-Path $Video -Leaf
    if ($datasetDir -and -not (Test-Path (Join-Path $datasetDir $Video))) { Fail "Nema klipa $Video u $datasetDir." }
}
if ($Clips.Count -eq 0) { $Clips = $DefaultClips }
if (-not $Camera) {   # zona vozaca = serija klipova koje kamera pusta
    $first = if ($CameraMode -eq "loop") { $Video } else { $Clips[0] }
    $Camera = if ($first -like "08_14*") { "08_14" } else { "05_23" }
    if ($datasetDir -and -not (Get-ChildItem $datasetDir -Filter "${Camera}_*_video_inCabin.mp4" | Select-Object -First 1)) {
        $Camera = if ($Camera -eq "05_23") { "08_14" } else { "05_23" }
    }
}
$ip = Get-LanIp
if (-not $ip) { Warn "nema mreze sa gateway-em: telefon samo preko USB-a (adb reverse)"; $ip = "127.0.0.1" }

$envText = @"
# Written by start.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm"). Example with every setting: docker/.env.example
HOST_IP=$ip
DATASET_DIR=$($datasetDir -replace '\\', '/')
CAMERA_MODE=$CameraMode
CLIPS=$($Clips -join ' ')
VIDEO=$Video
MODEL_CAMERA=$Camera
SPEED_SCENARIO=$Speed
COORDINATOR_PORT=$CoordinatorPort
SERVER_PORT=$ServerPort
DASHBOARD_PORT=$DashboardPort
"@
[IO.File]::WriteAllText($EnvFile, $envText, (New-Object Text.UTF8Encoding $false))
Ok "docker/.env: IP $ip, kamera $CameraMode, zona vozaca $Camera, brzina $Speed"

# ---------------------------------------------------------------- 4. izgradnja i pokretanje kontejnera
Say "Gradim i pokrecem kontejnere (prvi put ~10 min: model ima ~3 GB)..." Cyan
# Not piped (unlike Invoke-Docker): docker keeps its compact live progress view in the terminal. "Continue" because when
# the script's own output is redirected (.\start.ps1 *> log.txt), PowerShell 5.1 turns docker's stderr into errors.
Push-Location $Root
$ErrorActionPreference = "Continue"
& docker compose up -d --build --remove-orphans
$code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location
if ($code -ne 0) { Fail "docker compose up nije uspeo (greska iznad). Logovi: .\start.ps1 -Logs" }
Wait-Http "http://127.0.0.1:$ServerPort/api/v1/health" "server"
Wait-Http "http://127.0.0.1:$CoordinatorPort/api/v1/coordinator/status" "koordinator"
Wait-Http "http://127.0.0.1:$DashboardPort/" "dashboard"
$modelUp = $false
for ($i = 0; $i -lt 90 -and -not $modelUp; $i += 2) {
    try { $modelUp = (Invoke-RestMethod "http://127.0.0.1:$CoordinatorPort/api/v1/coordinator/status" -TimeoutSec 2).model.connected } catch { }
    if (-not $modelUp) { Start-Sleep -Seconds 2 }
}
if ($modelUp) { Ok "model povezan na koordinator" } else { Warn "model se jos nije povezao (.\start.ps1 -Logs -Service model)" }

if (-not (Get-NetFirewallRule -DisplayName "Docker Desktop Backend" -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq "True" -and $_.Action -eq "Allow" })) {
    Warn "nema firewall pravila 'Docker Desktop Backend': telefon preko hotspota mozda ne vidi portove (USB radi)"
}

# ---------------------------------------------------------------- 5. Bluetooth gateway (na laptopu: treba radio)
function Get-HostPython {
    $ErrorActionPreference = "Continue"   # py's stderr for a missing version must not stop the script
    foreach ($v in @("-3.13", "-3.12", "-3.11")) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $exe = & py $v -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        }
    }
    $installed = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    if (Test-Path $installed) { return $installed }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "Nema Python-a za Bluetooth gateway: instaliram Python 3.13 (winget)..." Cyan
        winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements | Out-Host
        if (Test-Path $installed) { return $installed }
    }
    return $null
}

if (-not $NoBle) {
    $gateway = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*car_link*gateway.py*" }
    if ($gateway) {
        Ok "Bluetooth gateway vec radi (PID $(@($gateway)[0].ProcessId)), ostaje"
    } else {
        $linkDir = Join-Path $Root "backend\coordinator\car_link"
        $venvPy = Join-Path $linkDir ".venv\Scripts\python.exe"
        $req = Join-Path $linkDir "requirements.txt"
        $stamp = Join-Path $linkDir ".venv\requirements.sha256"
        $hash = (Get-FileHash $req -Algorithm SHA256).Hash
        $ready = (Test-Path $venvPy) -and (Test-Path $stamp) -and ((Get-Content $stamp -ErrorAction SilentlyContinue) -eq $hash)
        if (-not $ready) {
            $hostPy = Get-HostPython
            if (-not $hostPy) {
                Warn "nema Python-a: Bluetooth gateway preskocen (telefon preko Wi-Fi/USB, <IP>:$CoordinatorPort)"
            } else {
                Say "Pripremam Bluetooth gateway (svoj venv, jednom)..." Cyan
                $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
                if (-not (Test-Path $venvPy)) { & $hostPy -m venv (Join-Path $linkDir ".venv") 2>&1 | Out-Host }
                & $venvPy -m pip install --disable-pip-version-check -q -r $req 2>&1 | Out-Host
                $code = $LASTEXITCODE
                $ErrorActionPreference = $old
                if ($code -eq 0) { Set-Content $stamp $hash; $ready = $true } else { Warn "pip install za gateway nije uspeo: Bluetooth preskocen" }
            }
        }
        if ($ready) {
            Open-Window "Bluetooth ($CarName)" ("& '$venvPy' backend\coordinator\car_link\gateway.py --coordinator http://127.0.0.1:$CoordinatorPort/api/v1 " +
                "--name '$CarName' --server-url http://${ip}:$ServerPort/api/v1")
        }
    }
}

# ---------------------------------------------------------------- 6. telefon preko USB-a: adb reverse stalno vazi
$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
if (-not (Test-Path $adb)) { $adb = (Get-Command adb -ErrorAction SilentlyContinue).Source }
if ($adb -and -not $NoAdb) {
    # Only single quotes inside: Start-Process passes this command line to powershell.exe as it is.
    $keep = "while (`$true) { if ((& '$adb' get-state 2>`$null) -eq 'device') { `$list = (& '$adb' reverse --list 2>`$null) -join ' '; " +
            "foreach (`$p in 8081, $CoordinatorPort, $ServerPort) { `$r = 'tcp:' + `$p; if (`$list -notmatch (`$r + ' ' + `$r)) { " +
            "& '$adb' reverse `$r `$r | Out-Null; Write-Host ((Get-Date -Format 'HH:mm:ss') + ' adb reverse ' + `$r) } } }; Start-Sleep -Seconds 3 }"
    Open-Window "telefon USB (adb reverse 8081, $CoordinatorPort, $ServerPort)" $keep
}

# ---------------------------------------------------------------- 7. gotovo
Say ""
Say "Spremno. Voznju pokrece aplikacija na telefonu (svaka voznja = sledeci klip):" Cyan
Say "  dashboard   http://localhost:$DashboardPort   (sa drugog uredjaja: http://${ip}:$DashboardPort)" Cyan
Say "  auto        Bluetooth '$CarName', ili Wi-Fi/USB: ${ip}:$CoordinatorPort (USB: localhost:$CoordinatorPort)" Cyan
Say "  server      http://${ip}:$ServerPort/api/v1   (USB: localhost:$ServerPort)" Cyan
Say "  stanje      .\start.ps1 -Status    logovi: .\start.ps1 -Logs    gasenje: .\start.ps1 -Stop" Cyan
if (-not $NoBrowser) { Start-Process "http://localhost:$DashboardPort" }
