<#
Ceo demo na laptopu jednom komandom: skladiste -> backend (koordinator + server) -> model -> kamera (-> dashboard).
Svaki deo se otvara u svom PowerShell prozoru (tu je njegov log; zatvaranje prozora gasi taj deo).

    .\demo.ps1 -Video "C:\...\08_14_62_092916_video_inCabin.mp4"            # nas model, klip u petlji
    .\demo.ps1 -Video "C:\...\05_23_62_031246_video_inCabin.mp4" -Dashboard # kolaps + dashboard u browseru
    .\demo.ps1 -Webcam "Integrated Camera"                                   # web kamera umesto klipa
    .\demo.ps1 -Model cv -Video ...                                          # model CV kolege, isti backend
    .\demo.ps1 -Port 8765 -Storage none -Video ...                           # proba: drugi port, bez baze
    .\demo.ps1 -PoVoznji                                                     # svaka voznja iz aplikacije = sledeci klip

-PoVoznji  umesto jedne kamere pokrece rivian_model\klip_po_voznji.py: svaka nova voznja dobija sledeci klip od pocetka
           (spisak: -Klipovi, podrazumevano 022338, 032409, 032617, 005853). Ne ide uz -Video/-Webcam: koordinator
           mesa frejmove dve kamere, pa model vidi "dva vozaca".

-Model     nas (podrazumevano, rivian_model/) ili cv (model/worker.py)
-Camera    zona vozaca za nas model: 08_14 ili 05_23. Bez nje se uzima iz imena klipa (05_23_* -> 05_23).
-Storage   docker (podrazumevano: Postgres :5433 + RustFS :9000 iz backend/docker-compose.yml),
           local (backend/scripts/services.ps1 start, bez Docker-a) ili none (samo koordinator, bez naloga i istorije)
-Speed     scenario brzine iz backend/app/coordinator/services/speed.py; podrazumevano cruise (stalnih 50-62 km/h)
-Port      8000 za telefon (otvoren na firewall-u). Mora biti slobodan: ugasi mock_backend.py pre demo-a.

Pre prvog pokretanja (jednom): README.md, odeljak "Demo sa nasim modelom".
#>
param(
    [ValidateSet("nas", "cv")] [string]$Model = "nas",
    [string]$Video = "",
    [string]$Webcam = "",
    [ValidateSet("", "08_14", "05_23")] [string]$Camera = "",
    [ValidateSet("docker", "local", "none")] [string]$Storage = "docker",
    [string]$Speed = "cruise",
    [int]$Port = 8000,
    [switch]$Dashboard,
    [switch]$PoVoznji,
    [string[]]$Klipovi = @()
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
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

# ---------------------------------------------------------------- provere
if (-not (Test-Path $BackendPy)) {
    throw "Nema backend\.venv. Jednom: cd backend; python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if (Test-PortBusy $Port) {
    throw "Port $Port je zauzet (npr. mock_backend.py ili stari backend). Ugasi ga ili pokreni sa -Port 8765."
}
if ($Video -and -not (Test-Path $Video)) { throw "Nema klipa: $Video" }
if (@($Video, $Webcam, $(if ($PoVoznji) { "x" } else { "" })) -ne "" | Select-Object -Skip 1) {
    throw "Izaberi samo jednu kameru: -Video, -Webcam ili -PoVoznji. Dve kamere se u koordinatoru mesaju (model vidi dva vozaca)."
}
if ($PoVoznji -and -not $Camera) {
    $Camera = "05_23"
    if ($Klipovi.Count -gt 0 -and $Klipovi[0] -like "08_14*") { $Camera = "08_14" }
}
if ($Model -eq "nas") {
    foreach ($f in "yolo11n_640.onnx", "yolo11n-pose_384.onnx", "face_landmarker.task") {
        if (-not (Test-Path (Join-Path $Root "rivian_model\$f"))) {
            throw "Nema rivian_model\$f. Jednom: cd rivian_model; python setup_models.py"
        }
    }
    if (-not $Camera) {
        $Camera = "08_14"
        if ($Video -and ((Split-Path $Video -Leaf) -like "05_23*")) { $Camera = "05_23" }
    }
} else {
    foreach ($f in "face_landmarker.task", "hand_landmarker.task", "yolo11s_640.onnx") {
        if (-not (Test-Path (Join-Path $Root "notebooks\models\$f"))) {
            throw "Nema notebooks\models\$f (model CV kolege). Jednom: cd notebooks; .\setup_models.bat"
        }
    }
}

Write-Host "Demo: model=$Model, port=$Port, brzina=$Speed, skladiste=$Storage" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1. skladiste (server: nalozi, istorija, slike)
$role = "all"
$serverEnv = ""
switch ($Storage) {
    "docker" {
        Push-Location (Join-Path $Root "backend")
        docker compose up -d
        Pop-Location
        Write-Host "  [ok] Postgres :5433 + RustFS :9000 (docker compose)" -ForegroundColor Green
    }
    "local" {
        & (Join-Path $Root "backend\scripts\services.ps1") start
    }
    "none" {
        # Samo koordinator: voznja radi, ali nema naloga, istorije ni slika (server namerno nedostupan).
        $role = "coordinator"
        $serverEnv = "`$env:SERVER_URL='http://127.0.0.1:8799/api/v1'; "
    }
}

# ---------------------------------------------------------------- 2. backend
Open-Window "backend :$Port" (Join-Path $Root "backend") `
    "`$env:SPEED_SCENARIO='$Speed'; $serverEnv& '$BackendPy' run.py --role $role --port $Port --no-reload"

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/coordinator/status" -TimeoutSec 2 | Out-Null
        $ready = $true; break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) { throw "Backend se nije javio na portu $Port za 30 s: pogledaj njegov prozor." }

# ---------------------------------------------------------------- 3. model
if ($Model -eq "nas") {
    Open-Window "nas model ($Camera)" (Join-Path $Root "rivian_model") `
        "python rivian_detector.py --coordinator $ModelWs --camera $Camera"
} else {
    $cvPy = Join-Path $Root "model\.venv\Scripts\python.exe"
    if (-not (Test-Path $cvPy)) { $cvPy = "python" }
    Open-Window "CV model" $Root "& '$cvPy' model\worker.py --coordinator $ModelWs"
}

# ---------------------------------------------------------------- 4. kamera
if ($Video) {
    Open-Window "kamera (klip u petlji)" $Root "& '$BackendPy' tools\camera_stream.py --url $CameraWs --video '$Video'"
} elseif ($Webcam) {
    Open-Window "kamera ($Webcam)" $Root "& '$BackendPy' tools\camera_stream.py --url $CameraWs --webcam '$Webcam'"
} elseif ($PoVoznji) {
    $lista = ""
    if ($Klipovi.Count -gt 0) { $lista = "--klipovi " + ($Klipovi -join " ") }
    Open-Window "kamera (klip po voznji)" $Root "python rivian_model\klip_po_voznji.py --port $Port $lista"
} else {
    Write-Host "  [--] kamera nije pokrenuta (dodaj -Video <klip>, -Webcam <ime> ili -PoVoznji)" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 5. dashboard (opciono)
if ($Dashboard) {
    Open-Window "dashboard" (Join-Path $Root "frontend\dashboard") "`$env:VITE_API_URL='http://localhost:$Port'; npm run dev"
}

$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4Address.IPAddress
Write-Host ""
Write-Host "Spremno. Voznju pokrece aplikacija na telefonu (adresa backenda: http://${ip}:$Port/api/v1)." -ForegroundColor Cyan
Write-Host "Bez telefona: POST http://127.0.0.1:$Port/api/v1/trips  {""driver_id"": ""demo""}" -ForegroundColor Cyan
Write-Host "Stanje: http://127.0.0.1:$Port/api/v1/coordinator/status . Gasenje: zatvori prozore 'demo: ...'." -ForegroundColor Cyan
