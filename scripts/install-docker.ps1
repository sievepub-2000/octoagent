param(
    [string]$Prefix = $(if ($env:OCTOAGENT_HOME) { $env:OCTOAGENT_HOME } else { Join-Path $HOME "octoagent" }),
    [string]$Repo = $(if ($env:OCTOAGENT_REPO_URL) { $env:OCTOAGENT_REPO_URL } else { "https://github.com/sievepub-2000/octoagent.git" }),
    [string]$Branch = $(if ($env:OCTOAGENT_BRANCH) { $env:OCTOAGENT_BRANCH } else { "main" }),
    [switch]$NoStart,
    [switch]$NoBuild,
    [switch]$Pull,
    [int]$WaitSeconds = 240
)

$ErrorActionPreference = "Stop"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Invoke-Compose([string[]]$Args) {
    & docker compose --env-file .env.docker -f compose.yaml @Args
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($Args -join ' ')" }
}

function New-Secret {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes)
}

Require-Command git
Require-Command docker
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 is required. Install Docker Desktop." }

if (Test-Path (Join-Path $Prefix ".git")) {
    Set-Location $Prefix
    git fetch origin $Branch
    git checkout $Branch
    git pull --ff-only origin $Branch
} elseif ((Test-Path $Prefix) -and ((Get-ChildItem -LiteralPath $Prefix -Force | Select-Object -First 1) -ne $null)) {
    throw "Prefix exists and is not an empty git checkout: $Prefix"
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Prefix) | Out-Null
    git clone --branch $Branch $Repo $Prefix
    Set-Location $Prefix
}

if (-not (Test-Path config.yaml)) { Copy-Item config.example.yaml config.yaml }
if (-not (Test-Path .env.docker)) { Copy-Item .env.docker.example .env.docker }
$envText = Get-Content .env.docker -Raw
if ($envText.Contains("replace-with-a-long-random-secret")) {
    $envText = $envText.Replace("replace-with-a-long-random-secret", (New-Secret))
    Set-Content -Encoding utf8 -NoNewline -Path .env.docker -Value $envText
}

foreach ($dir in @("logs", "runtime/cache", "runtime/logs", "runtime/system_tools", "workspace/env", "workspace/default", "tmp")) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

if ($Pull) { docker compose --env-file .env.docker -f compose.yaml pull --ignore-buildable }
if (-not $NoStart) {
    if ($NoBuild) {
        Invoke-Compose @("up", "-d", "--remove-orphans")
    } else {
        Invoke-Compose @("up", "-d", "--build", "--remove-orphans")
    }
    $portLine = (Get-Content .env.docker | Where-Object { $_ -match '^OCTO_NGINX_PORT=' } | Select-Object -Last 1)
    $port = if ($portLine) { ($portLine -split '=', 2)[1].Trim() } else { "19800" }
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5 | Out-Null
            Write-Host "OctoAgent Docker is ready: http://127.0.0.1:$port"
            exit 0
        } catch {
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)
    docker compose --env-file .env.docker -f compose.yaml ps
    docker compose --env-file .env.docker -f compose.yaml logs --tail=120 nginx gateway langgraph frontend
    throw "Timed out waiting for http://127.0.0.1:$port/health"
}

Write-Host "OctoAgent Docker files are ready in $Prefix. Start with: docker compose --env-file .env.docker -f compose.yaml up -d --build"
