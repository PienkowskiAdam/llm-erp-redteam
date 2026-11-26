# One-shot setup + run on Windows. Ollama by default; LM Studio optional. Safe to re-run.
# Usage (PowerShell, in repo folder):
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
#   powershell -ExecutionPolicy Bypass -File .\run.ps1 -Model qwen2.5:3b -Trials 5
#   powershell -ExecutionPolicy Bypass -File .\run.ps1 -Backend lmstudio -BaseUrl http://localhost:1234/v1
param(
    [ValidateSet('auto', 'ollama', 'lmstudio')]
    [string]$Backend = $(if ($env:LLM_BACKEND) {
        if ($env:LLM_BACKEND -in @('openai', 'lmstudio')) { 'lmstudio' } else { 'ollama' }
    } else { 'auto' }),
    [string]$Model     = $env:MODEL,
    [int]   $Trials    = $(if ($env:TRIALS) { [int]$env:TRIALS } else { 3 }),
    [string]$BaseUrl   = $env:OPENAI_BASE_URL,
    [string]$OllamaUrl = $(if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { 'http://localhost:11434' }),
    [int]   $Timeout   = $(if ($env:LLM_TIMEOUT) { [int]$env:LLM_TIMEOUT } else { 600 })
)
# Native tools write to stderr on success; don't let that abort the script. Exit codes are checked manually.
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m)  { Write-Host "    OK: $m" -ForegroundColor Green }
function Die($m) { Write-Host "`nERROR: $m" -ForegroundColor Red; exit 1 }

# ---------- 1. Python >= 3.10 ----------
Say "1/6 Checking Python >= 3.10"
$py = $null
$candidates = @(
    @{ exe = 'py';     args = @('-3.13') },
    @{ exe = 'py';     args = @('-3.12') },
    @{ exe = 'py';     args = @('-3.11') },
    @{ exe = 'py';     args = @('-3.10') },
    @{ exe = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"; args = @() },
    @{ exe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; args = @() },
    @{ exe = "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe"; args = @('-3') },
    @{ exe = 'python'; args = @() }
)
foreach ($c in $candidates) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    $a = $c.args
    & $c.exe @a -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) {
    Die "Python 3.10+ not found. Install from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), open a NEW PowerShell window, re-run."
}
$pa = $py.args
Ok ((& $py.exe @pa --version) + " ($($py.exe) $($pa -join ' '))")

if ($Backend -eq 'auto') {
    $Backend = if (Get-Command ollama -ErrorAction SilentlyContinue) { 'ollama' }
               elseif ($BaseUrl) { 'lmstudio' }
               else { 'ollama' }
}

if ($Backend -eq 'ollama') {
# ---------- 2-3. Ollama server ----------
Say "2/6 Checking Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "Installing Ollama via winget"
        winget install --id Ollama.Ollama -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }
}
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Die "Ollama not found. Install from https://ollama.com/download and re-run."
}
Ok ((& ollama --version 2>$null | Select-Object -First 1))

Say "3/6 Making sure Ollama server is running at $OllamaUrl"
$up = $false
try { Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 3 | Out-Null; $up = $true } catch {}
if (-not $up) {
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try { Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 3 | Out-Null; $up = $true; break } catch {}
    }
}
if (-not $up) { Die "Ollama server did not start. Run 'ollama serve' in a terminal and re-run." }
Ok "server up"

# ---------- 4. Model ----------
Say "4/6 Selecting model"
if (-not $Model) {
    $ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    $Model = if ($ram -ge 12) { 'qwen2.5:7b' } else { 'qwen2.5:3b' }
    Ok "RAM ${ram} GB -> $Model"
}
$have = @(& ollama list 2>$null | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ })
if ($have -notcontains $Model) {
    Say "Pulling $Model (first run can take a while)"
    & ollama pull $Model
    if ($LASTEXITCODE -ne 0) { Die "ollama pull $Model failed" }
}
Ok "model $Model"
} else {
# ---------- 2-3. LM Studio server ----------
Say "2/6 Looking for LM Studio server"
$urls = if ($BaseUrl) { @($BaseUrl.TrimEnd('/')) } else { @('http://localhost:1234/v1', 'http://localhost:1235/v1') }
$models = $null
foreach ($u in $urls) {
    try { $models = Invoke-RestMethod -Uri "$u/models" -TimeoutSec 5; $BaseUrl = $u; break } catch {}
}
if (-not $models) {
    Die "No LM Studio server at $($urls -join ' or '). LM Studio -> Developer tab -> load model -> Status: Running. Or in terminal: lms server start. Other port? Re-run with -BaseUrl http://localhost:<port>/v1"
}
Ok "server at $BaseUrl"

Say "3/6 Selecting model"
if (-not $Model) {
    $Model = ($models.data | Where-Object { $_.id -notmatch 'embed' } | Select-Object -First 1).id
    if (-not $Model) { Die "Server has no chat model loaded. Load one in LM Studio and re-run." }
}
Ok "model $Model"
}

# ---------- 5a. venv + tests ----------
Say "5/6 Python venv + tests (no LLM)"
$vpy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    & $py.exe @pa -m venv .venv
    if ($LASTEXITCODE -ne 0) { Die "Could not create .venv" }
}
& $vpy -m pip install --quiet --disable-pip-version-check pytest
if ($LASTEXITCODE -ne 0) { Die "pip install pytest failed (no internet?)" }
& $vpy -m pytest -q
if ($LASTEXITCODE -ne 0) { Die "Tests failed. Do NOT continue; paste output above." }
Ok "tests passed"

# ---------- 5b. Attack harness ----------
Say "6/6 Running attacks: backend=$Backend model=$Model trials=$Trials timeout=${Timeout}s (CPU: expect 30-120 min)"
if ($Backend -eq 'lmstudio') {
    $env:LLM_BACKEND     = 'openai'
    $env:OPENAI_BASE_URL = $BaseUrl
} else {
    $env:LLM_BACKEND     = 'ollama'
    $env:OLLAMA_URL      = $OllamaUrl
}
$env:MODEL           = $Model
$env:LLM_TIMEOUT     = "$Timeout"
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path results | Out-Null
$safe = ($Model -replace '[:/\\]', '-')
$out  = "results\$(Get-Date -Format 'yyyyMMdd-HHmmss')_$safe.txt"
$header = "backend=$Backend model=$Model trials=$Trials timeout=$Timeout date=$((Get-Date).ToUniversalTime().ToString('s'))Z host_os=Windows"
Write-Host $header
& $vpy -m harness.run --trials $Trials | Tee-Object -Variable lines
Set-Content -Path $out -Encoding utf8 -Value (@($header) + $lines)
Say "DONE. Results saved to $(Join-Path $PSScriptRoot $out)"
