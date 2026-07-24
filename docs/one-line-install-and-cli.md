# Docker installation

OctoAgent supports one deployment path: Docker Compose.

## Linux and macOS

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-docker.sh
```

## Windows PowerShell

```powershell
git clone https://github.com/sievepub-2000/octoagent.git
Set-Location octoagent
.\scripts\install-docker.ps1
```

The installers create `.env.docker`, build the two application images, start
the five-service topology, and verify the public health endpoint. Use
`docker compose --env-file .env.docker` for subsequent status, logs, restart,
upgrade, and stop operations.

Host Python virtual environments and `octoagent-local.service` are unsupported.
