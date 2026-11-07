<#
Ceo auto na laptopu jednom komandom: skladiste -> server -> koordinator -> Bluetooth -> model -> kamera (-> dashboard).
Svaki deo se otvara u svom PowerShell prozoru (tu je njegov log; zatvaranje prozora gasi taj deo).

    .\demo.ps1 -Video "..\dataset\08_14_62_092916_video_inCabin.mp4"            # klip u petlji (telefon)
    .\demo.ps1 -Video "..\dataset\05_23_62_031246_video_inCabin.mp4" -Dashboard  # kolaps + dashboard u browseru
    .\demo.ps1 -PoVoznji                                                         # svaka voznja iz aplikacije = sledeci klip
    .\demo.ps1 -Webcam "Integrated Camera"                                       # web kamera umesto klipa
    .\demo.ps1 -Storage none -NoBle -Video ...                                   # bez servera i bez Bluetooth-a

Telefon: auto preko Bluetooth-a (Settings -> Car connection -> Cars nearby), server na http://<IP laptopa>:8001/api/v1
(preko USB-a: adb reverse tcp:8001 tcp:8001, adresa localhost:8001). Wi-Fi veza sa autom: <IP laptopa>:8000.

-PoVoznji  umesto jedne kamere pokrece rivian_model\klip_po_voznji.py: svaka nova voznja dobija sledeci klip od pocetka
           (spisak: -Klipovi, podrazumevano 031246, 021254, 005853 iz serije 05_23). Ne ide uz -Video/-Webcam: dve kamere
           bi mesale frejmove, pa koordinator prima samo jednu.
-Camera    zona vozaca za model: 08_14 ili 05_23. Bez nje se uzima iz imena klipa (05_23_* -> 05_23).
-Storage   docker (podrazumevano: Postgres :5433 + RustFS :9000 iz backend/docker-compose.yml),
           local (backend/scripts/services.ps1 start, bez Docker-a) ili none (bez servera: voznja radi, nema naloga ni istorije)
-Speed     scenario brzine iz backend/app/coordinator/services/speed.py; podrazumevano cruise (stalnih 50-62 km/h)
-Port      koordinator (8000, otvoren na firewall-u), -ServerPort server (8001). Moraju biti slobodni.
-NoBle     bez Bluetooth gateway-a (telefon se onda vezuje za auto preko Wi-Fi/USB, <IP>:8000)
-Dataset   folder sa klipovima za -PoVoznji (podrazumevano $env:DATASET_DIR, inace ..\dataset pored repoa)

Pre prvog pokretanja (jednom): README.md, odeljak "Demo".
#>
param(
    [string]$Video = "",
    [string]$Webcam = "",
    [ValidateSet("", "08_14", "05_23")] [string]$Camera = "",
    [ValidateSet("docker", "local", "none")] [string]$Storage = "docker",
    [string]$Speed = "cruise",
    [int]$Port = 8000,
    [int]$ServerPort = 8001,
    [string]$CarName = "Rivian demo car",
    [switch]$NoBle,
    [switch]$Dashboard,
    [switch]$PoVoznji,
    [string[]]$Klipovi = @(),
    [string]$Dataset = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
$ModelPy = Join-Path $Root "rivian_model\.venv\Scripts\python.exe"
$ModelWs = "ws://127.0.0.1:$Port/api/v1/model/ws"
$CameraWs = "ws://127.0.0.1:$Port/api/v1/camera/ws"

function Open-Window([string]$Title, [string]$Dir, [string]$Command) {
    $full = "`$Host.UI.RawUI.WindowTitle = 'demo: $Title'; Set-Location '$Dir'; $Command"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $full | Out-Null
    Write-Host "  [ok] $Title" -ForegroundColor Green
}

function Test-PortBusy([int]$P) {
    return [bool](Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http([string]$Url, [string]$What) {
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-RestMethod $Url -TimeoutSec 2 | Out-Null; return } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "$What se nije javio za 30 s ($Url): pogledaj njegov prozor."
}

# ---------------------------------------------------------------- provere
if (-not (Test-Path $BackendPy)) {
    throw "Nema backend\.venv. Jednom: cd backend; py -3.13 -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if (-not (Test-Path $ModelPy)) {
    throw "Nema rivian_model\.venv. Jednom: rivian_model\README.md, odeljak Pokretanje (venv + setup_models.py)"
}
foreach ($f in "yolo11n_640.onnx", "yolo11n-pose_384.onnx", "face_landmarker.task") {
    if (-not (Test-Path (Join-Path $Root "rivian_model\$f"))) {
        throw "Nema rivian_model\$f. Jednom: rivian_model\.venv\Scripts\python.exe rivian_model\setup_models.py"
    }
}
$ports = @($Port) + $(if ($Storage -ne "none") { @($ServerPort) } else { @() })
foreach ($p in $ports) {
    if (Test-PortBusy $p) { throw "Port $p je zauzet (stari backend?). Ugasi ga ili izaberi -Port / -ServerPort." }
}
if ($Video -and -not (Test-Path $Video)) { throw "Nema klipa: $Video" }
if (@($Video, $Webcam, $(if ($PoVoznji) { "x" } else { "" })) -ne "" | Select-Object -Skip 1) {
    throw "Izaberi samo jednu kameru: -Video, -Webcam ili -PoVoznji (koordinator prima jednu kameru)."
}
if (-not $Camera) {
    $Camera = "08_14"
    if ($Video -and ((Split-Path $Video -Leaf) -like "05_23*")) { $Camera = "05_23" }
    if ($PoVoznji) {
        $Camera = "05_23"
        if ($Klipovi.Count -gt 0 -and $Klipovi[0] -like "08_14*") { $Camera = "08_14" }
    }
}

Write-Host "Demo: koordinator :$Port, server :$ServerPort, brzina $Speed, skladiste $Storage, zona vozaca $Camera" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1. skladiste + server (nalozi, istorija, slike)
$serverUrl = "http://127.0.0.1:$ServerPort/api/v1"
switch ($Storage) {
    "docker" {
        # docker compose prints its progress on stderr; PowerShell 5.1 with "Stop" would turn that into an error
        # whenever the output is captured, so judge by the exit code instead.
        Push-Location (Join-Path $Root "backend")
        $ErrorActionPreference = "Continue"
        docker compose up -d 2>&1 | ForEach-Object { "    $_" } | Out-Host
        $code = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        Pop-Location
        if ($code -ne 0) { throw "docker compose up -d nije uspeo (radi li Docker Desktop?). Bez Docker-a: -Storage local" }
        Write-Host "  [ok] Postgres :5433 + RustFS :9000 (docker compose)" -ForegroundColor Green
    }
    "local" { & (Join-Path $Root "backend\scripts\services.ps1") start }
    "none" { $serverUrl = "http://127.0.0.1:8799/api/v1" }   # namerno nedostupan: koordinator radi i bez servera
}
if ($Storage -ne "none") {
    Open-Window "server :$ServerPort" (Join-Path $Root "backend") "& '$BackendPy' run.py --role server --port $ServerPort --no-reload"
    Wait-Http "$serverUrl/health" "Server"
}

# ---------------------------------------------------------------- 2. koordinator (u autu)
Open-Window "koordinator :$Port" (Join-Path $Root "backend") `
    "`$env:SPEED_SCENARIO='$Speed'; `$env:SERVER_URL='$serverUrl'; & '$BackendPy' run.py --role coordinator --port $Port --no-reload"
Wait-Http "http://127.0.0.1:$Port/api/v1/coordinator/status" "Koordinator"

# ---------------------------------------------------------------- 3. Bluetooth veza sa telefonom
if (-not $NoBle) {
    Open-Window "Bluetooth ($CarName)" $Root `
        "& '$BackendPy' backend\coordinator\car_link\gateway.py --coordinator http://127.0.0.1:$Port/api/v1 --name '$CarName'"
}

# ---------------------------------------------------------------- 4. model
Open-Window "model ($Camera)" (Join-Path $Root "rivian_model") "& '$ModelPy' rivian_detector.py --coordinator $ModelWs --camera $Camera"

# ---------------------------------------------------------------- 5. kamera
if ($Video) {
    Open-Window "kamera (klip u petlji)" $Root "& '$BackendPy' tools\camera_stream.py --url $CameraWs --video '$Video'"
} elseif ($Webcam) {
    Open-Window "kamera ($Webcam)" $Root "& '$BackendPy' tools\camera_stream.py --url $CameraWs --webcam '$Webcam'"
} elseif ($PoVoznji) {
    $extra = ""
    if ($Klipovi.Count -gt 0) { $extra += " --klipovi " + ($Klipovi -join " ") }
    if ($Dataset) { $extra += " --dataset '$Dataset'" }
    Open-Window "kamera (klip po voznji)" $Root "& '$BackendPy' rivian_model\klip_po_voznji.py --port $Port$extra"
} else {
    Write-Host "  [--] kamera nije pokrenuta (dodaj -Video <klip>, -Webcam <ime> ili -PoVoznji)" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 6. dashboard (opciono)
if ($Dashboard) {
    Open-Window "dashboard" (Join-Path $Root "frontend\dashboard") "`$env:VITE_API_URL='http://localhost:$Port'; npm run dev"
}

$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4Address.IPAddress
Write-Host ""
Write-Host "Spremno. Voznju pokrece aplikacija na telefonu:" -ForegroundColor Cyan
Write-Host "  auto: Bluetooth '$CarName' (ili Wi-Fi: http://${ip}:$Port/api/v1), server: http://${ip}:$ServerPort/api/v1" -ForegroundColor Cyan
Write-Host "Bez telefona: POST http://127.0.0.1:$Port/api/v1/trips  {""driver_id"": ""demo""}" -ForegroundColor Cyan
Write-Host "Stanje: http://127.0.0.1:$Port/api/v1/coordinator/status . Gasenje: zatvori prozore 'demo: ...'." -ForegroundColor Cyan
