#Requires -Version 5.1
<#
.SYNOPSIS
    Installs OctoAgent on Windows (local or service mode).
.DESCRIPTION
    Mirrors the Linux install-octoagent.sh but adapted for Windows:
    detects OS, checks prerequisites (Python 3.12+, Node.js 22+, git),
    offers winget installs if missing, clones the repo, runs bootstrap,
    creates Start Menu shortcut, optionally installs as a Windows service.
.PARAMETER Prefix
    Installation directory (default: $HOME/octoagent).
.PARAMETER Yes
    Skip all confirmation prompts.
.PARAMETER Mode
    "local" or "service" (default: local).
.PARAMETER RepoUrl
    Git repository URL (default: https://github.com/sievepub-2000/octoagent.git).
.PARAMETER Branch
    Git branch to install (default: main).
.PARAMETER DefaultModel
    Configure the default model after installation.
.PARAMETER StartAfter
    Start OctoAgent immediately after installation.
.EXAMPLE
    .\install-octoagent.ps1 --yes --mode local
.EXAMPLE
    .\install-octoagent.ps1 --prefix C:\OctoAgent --mode service --yes
#>

param(
    [string]$Prefix = "",
    [switch]$Yes,
    [ValidateSet("local", "service")]
    [string]$Mode = "local",
    [string]$RepoUrl = "https://github.com/sievepub-2000/octoagent.git",
    [string]$Branch = "main",
    [string]$DefaultModel = "",
    [switch]$StartAfter
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Confirm-Action {
    param([string]$Message)
    if ($Yes) { return $true }
    try {
        $answer = Read-Host "$Message [y/N]"
        return $answer -match "^[yy]$|^yes$"
    } catch {
        Write-Warning "Non-interactive mode without --yes; refusing."
        return $false
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

# ---------------------------------------------------------------------------
# OS Detection
# ---------------------------------------------------------------------------

Write-Step "OctoAgent Windows Installer"

$isWindows = ($env:OS -eq "Windows_NT") -or
             ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) -or
             ($PSVersionTable.PSVersion.Major -ge 5)

if (-not $isWindows) {
    Write-Error "This script is intended for Windows. Detected platform: $([System.Environment]::OSVersion.Platform)"
    exit 1
}

Write-Host "Platform: Windows"

# ---------------------------------------------------------------------------
# Prefix resolution
# ---------------------------------------------------------------------------

if ($Prefix -eq "") {
    # If the script lives inside a git checkout, use its parent directory.
    $scriptPath = $MyInvocation.MyCommand.Path
    if ($scriptPath) {
        $scriptDir = Split-Path (Resolve-Path $scriptPath) -Parent
        if (Test-Path (Join-Path $scriptDir ".." ".git")) {
            $Prefix = (Get-Item (Join-Path $scriptDir "..")).FullName
        } else {
            $Prefix = Join-Path $env:USERPROFILE "octoagent"
        }
    } else {
        $Prefix = Join-Path $env:USERPROFILE "octoagent"
    }
}

Write-Host "  prefix: $Prefix"
Write-Host "  mode:   $Mode"

# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------

Write-Step "Checking prerequisites"

$missing = @()

# Python 3.12+
function Test-Python312 {
    $candidates = @("python3.12", "python3", "python")
    foreach ($c in $candidates) {
        $exe = Get-Command $c -ErrorAction SilentlyContinue
        if ($exe) {
            try {
                $verOutput = & $exe.FullName --version 2>&1
                if ($verOutput -match "(\d+)\.(\d+)") {
                    $major = [int]$Matches[1]
                    $minor = [int]$Matches[2]
                    if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 12)) {
                        return $true
                    }
                }
            } catch {}
        }
    }
    return $false
}

if (-not (Test-Python312)) {
    $missing += "python3.12"
} else {
    Write-Host "  Python: OK" -ForegroundColor Green
}

# Node.js 22+
function Test-Node22 {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { return $false }
    try {
        $verStr = & $node.FullName -e "process.version" 2>&1
        if ($verStr -match "v(\d+)\.") {
            return [int]$Matches[1] -ge 22
        }
    } catch {}
    return $false
}

if (-not (Test-Node22)) {
    $missing += "nodejs22"
} else {
    Write-Host "  Node.js: OK" -ForegroundColor Green
}

# Git
if (-not (Test-CommandAvailable "git")) {
    $missing += "git"
} else {
    Write-Host "  Git: OK" -ForegroundColor Green
}

if ($missing.Count -gt 0) {
    Write-Host "`nMissing prerequisites: $($missing -join ', ')" -ForegroundColor Yellow

    if (Confirm-Action "Install missing packages via winget?") {
        foreach ($pkg in $missing) {
            switch ($pkg) {
                "python3.12" {
                    Write-Host "  Installing Python 3.12 via winget..."
                    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
                }
                "nodejs22" {
                    Write-Host "  Installing Node.js 22 via winget..."
                    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
                }
                "git" {
                    Write-Host "  Installing Git via winget..."
                    winget install Git.Git --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
                }
            }
        }
        # Refresh PATH in case winget added new binaries
        $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    } else {
        Write-Error "Refusing to continue without prerequisites. Install them manually or rerun with --yes."
        exit 2
    }

    # Re-check after winget install
    $stillMissing = @()
    if (-not (Test-Python312)) { $stillMissing += "python3.12" }
    if (-not (Test-Node22))     { $stillMissing += "nodejs22" }
    if (-not (Test-CommandAvailable "git")) { $stillMissing += "git" }

    if ($stillMissing.Count -gt 0) {
        Write-Error "winget install did not resolve: $($stillMissing -join ', '). Aborting."
        exit 2
    }
}

# ---------------------------------------------------------------------------
# Clone / update repository
# ---------------------------------------------------------------------------

Write-Step "Cloning repository"

$parentDir = Split-Path $Prefix -Parent
if (-not (Test-Path $parentDir)) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }

if (Test-Path (Join-Path $Prefix ".git")) {
    Write-Host "  Updating existing checkout at $Prefix"
    Set-Location $Prefix
    git fetch origin $Branch
    git checkout $Branch
    git pull --ff-only origin $Branch
} elseif ((Test-Path $Prefix) -and (@(Get-ChildItem $Prefix -Force).Count -gt 0)) {
    Write-Error "Directory $Prefix exists and is not an empty git checkout. Aborting."
    exit 1
} else {
    Write-Host "  Cloning $RepoUrl -> $Prefix"
    git clone --branch $Branch $RepoUrl $Prefix
    Set-Location $Prefix
}

# ---------------------------------------------------------------------------
# Bootstrap (uv sync + pnpm install)
# ---------------------------------------------------------------------------

Write-Step "Bootstrapping dependencies"

$bootstrapScript = Join-Path $Prefix "scripts" "bootstrap.sh"
if (Test-Path $bootstrapScript) {
    # Use git-bash or wsl if available, otherwise fall back to manual steps.
    $bashExe = Get-Command bash -ErrorAction SilentlyContinue
    if ($bashExe) {
        & $bashExe.FullName $bootstrapScript 2>&1 | Out-Null
    } else {
        Write-Warning "No bash found; running bootstrap manually."
        # Backend: uv sync
        $uvExe = Get-Command uv -ErrorAction SilentlyContinue
        if ($uvExe) {
            & $uvExe.FullName sync --group dev 2>&1 | Out-Null
        } else {
            Write-Warning "uv not found; skipping backend dependency install."
        }
        # Frontend: pnpm install
        if (Test-CommandAvailable "pnpm") {
            & pnpm install --frozen-lockfile 2>&1 | Out-Null
        } elseif (Test-CommandAvailable "corepack") {
            corepack enable 2>&1 | Out-Null
            & pnpm install --frozen-lockfile 2>&1 | Out-Null
        } else {
            Write-Warning "No pnpm/corepack found; skipping frontend dependency install."
        }
    }
} else {
    Write-Host "  No bootstrap.sh found; running manual setup."
    $uvExe = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvExe) {
        & $uvExe.FullName sync --group dev 2>&1 | Out-Null
    }
    if (Test-CommandAvailable "pnpm") {
        & pnpm install --frozen-lockfile 2>&1 | Out-Null
    } elseif (Test-CommandAvailable "corepack") {
        corepack enable 2>&1 | Out-Null
        & pnpm install --frozen-lockfile 2>&1 | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Configure project directories and env files
# ---------------------------------------------------------------------------

Write-Step "Configuring project"

$dirs = @("workspace/default", "workspace/env", "workspace/workflow/taskwork",
          "runtime/logs", "runtime/system_tools", "tmp")
foreach ($d in $dirs) {
    $fullPath = Join-Path $Prefix $d
    if (-not (Test-Path $fullPath)) { New-Item -ItemType Directory -Path $fullPath -Force | Out-Null }
}

$envFile = Join-Path $Prefix ".env"
$envExample = Join-Path $Prefix ".env.example"
if ((-not (Test-Path $envFile)) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
}

$frontendEnvFile = Join-Path $Prefix "frontend" ".env"
$frontendEnvExample = Join-Path $Prefix "frontend" ".env.example"
if ((-not (Test-Path $frontendEnvFile)) -and (Test-Path $frontendEnvExample)) {
    Copy-Item $frontendEnvExample $frontendEnvFile
}

$octoagentScript = Join-Path $Prefix "scripts" "octoagent"
if (Test-Path $octoagentScript) {
    if ($DefaultModel -ne "") {
        & $octoagentScript configure --default-model $DefaultModel --yes 2>&1 | Out-Null
    } else {
        & $octoagentScript configure --yes 2>&1 | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Create Start Menu shortcut
# ---------------------------------------------------------------------------

Write-Step "Creating shortcuts"

$shortcutTarget = Join-Path $Prefix "scripts" "octoagent.ps1"
if (-not (Test-Path $shortcutTarget)) { $shortcutTarget = Join-Path $Prefix "scripts" "octoagent" }

$shell = New-Object -ComObject WScript.Shell
$startMenuDir = [Environment]::GetFolderPath("StartMenu")
$lnkPath = Join-Path $startMenuDir "OctoAgent.lnk"

if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }

$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$shortcutTarget`""
$shortcut.WorkingDirectory = $Prefix
$shortcut.Description = "OctoAgent"
$shortcut.Save()
Write-Host "  Start Menu shortcut: $lnkPath"

# Desktop shortcut (optional)
$desktopDir = [Environment]::GetFolderPath("Desktop")
$desktopLnk = Join-Path $desktopDir "OctoAgent.lnk"
if (Confirm-Action "Create desktop shortcut?") {
    if (Test-Path $desktopLnk) { Remove-Item $desktopLnk -Force }
    $shortcut2 = $shell.CreateShortcut($desktopLnk)
    $shortcut2.TargetPath = "powershell.exe"
    $shortcut2.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$shortcutTarget`""
    $shortcut2.WorkingDirectory = $Prefix
    $shortcut2.Description = "OctoAgent"
    $shortcut2.Save()
    Write-Host "  Desktop shortcut: $desktopLnk"
}

# ---------------------------------------------------------------------------
# Service mode (Windows service via nssm or built-in)
# ---------------------------------------------------------------------------

Write-Step "Service installation"

if ($Mode -eq "service") {
    $nssmExe = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssmExe) {
        Write-Host "  NSSM not found. Installing via winget..."
        winget install NSSM.NSSM --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $nssmExe = Get-Command nssm -ErrorAction SilentlyContinue
    }

    if ($nssmExe) {
        Write-Host "  Installing OctoAgent as a Windows service..."
        $startScript = Join-Path $Prefix "scripts" "start-octoagent.ps1"
        if (-not (Test-Path $startScript)) { $startScript = Join-Path $Prefix "scripts" "start-daemon.sh" }

        nssm install octoagent-local "$nssmExe.FullName" start $startScript 2>&1 | Out-Null
        nssm set octoagent-local AppDirectory $Prefix 2>&1 | Out-Null
        nssm set octoagent-local DisplayName "OctoAgent Local Service" 2>&1 | Out-Null
        nssm set octoagent-local Description "OctoAgent local runtime service" 2>&1 | Out-Null
        nssm set octoagent-local Start SERVICE_AUTO_START 2>&1 | Out-Null

        Write-Host "  Service 'octoagent-local' installed. Start with: net start octoagent-local"
    } else {
        Write-Warning "Could not install as service (nssm unavailable). Run in local mode instead."
    }
} else {
    Write-Host "  Skipping service installation (--mode local)."
}

# ---------------------------------------------------------------------------
# Start after install
# ---------------------------------------------------------------------------

if ($StartAfter) {
    Write-Step "Starting OctoAgent"
    if ($Mode -eq "service") {
        net start octoagent-local 2>&1 | Out-Null
    } else {
        & $octoagentScript start 2>&1 | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

Write-Step "Installation complete"
Write-Host "OctoAgent installed at: $Prefix"
Write-Host "Run: octoagent (or open OctoAgent from Start Menu)"

$portsScript = Join-Path $Prefix "scripts" "octoagent"
if (Test-Path $portsScript) {
    & $portsScript ports 2>&1 | Out-Null
}
