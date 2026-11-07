<#
Reserve the demo's TCP ports so Windows never hands them to someone else. Run ONCE, as administrator, with the demo stopped
(.\demo.ps1 -Stop): an elevated PowerShell in the repo root, then  .\tools\reserve-ports.ps1

Why: Hyper-V, WSL and Docker (WinNAT) reserve whole port ranges at boot, and the ranges move between reboots. A port that
lands in one fails with WinError 10013 ("access forbidden"), as 8685-8884 did on Matija's laptop. An administered
exclusion (store=persistent, survives reboots) keeps a port out of those ranges and out of the dynamic pool, while our own
programs can still listen on it. Check the result with: netsh interface ipv4 show excludedportrange protocol=tcp (ours are
the lines marked *). Undo one: netsh int ipv4 delete excludedportrange protocol=tcp startport=8000 numberofports=1

Ports: 8000 coordinator, 8001 server, 5173 dashboard, 5174 video-sim, 8081 Metro. Docker's own (5433, 9000, 9001) are left
to Docker Desktop.
#>
#Requires -RunAsAdministrator
param([int[]]$Ports = @(8000, 8001, 5173, 5174, 8081))

$ErrorActionPreference = "Continue"
$existing = netsh interface ipv4 show excludedportrange protocol=tcp
net stop winnat 2>&1 | Out-Null   # WinNAT holds its reservations while it runs; it starts again below
foreach ($p in $Ports) {
    if ($existing -match "^\s*$p\s+$p\s+\*") { Write-Host "  [ok] $p already reserved"; continue }
    $out = netsh int ipv4 add excludedportrange protocol=tcp startport=$p numberofports=1 store=persistent 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "  [ok] $p reserved" -ForegroundColor Green }
    else { Write-Host "  [!!] $p not reserved: $out (in use right now? stop the demo first)" -ForegroundColor Yellow }
}
net start winnat 2>&1 | Out-Null
netsh interface ipv4 show excludedportrange protocol=tcp
