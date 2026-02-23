# K3s Deployment Guide

Last updated: 2026-02-22

> **Note:** This is an example deployment intended for personal home servers and experimentation.
> It is not hardened for production use. Use it as a reference for building your own
> deployment pipeline, and review all security settings before exposing to untrusted networks.

Deploy ATLAS on a single-node K3s cluster with Traefik ingress, forward authentication, and MinIO file storage. This guide also covers setting up automatic updates via cron.

## Prerequisites

- **Linux server** (Ubuntu 22.04+ or Fedora 38+ recommended)
- **K3s** installed ([k3s.io](https://k3s.io))
- **Podman** (used to build container images; Docker works too)
- **envsubst** (part of `gettext` -- install with `apt install gettext` or `dnf install gettext`)
- A copy of this repository cloned to the server

### Install K3s

```bash
curl -sfL https://get.k3s.io | sh -
```

Verify it is running:

```bash
sudo k3s kubectl get nodes
```

### Install Podman

```bash
# Ubuntu/Debian
sudo apt install podman

# Fedora/RHEL
sudo dnf install podman
```

## Directory Layout

All K3s manifests live in `deploy/k3s/`:

```
deploy/k3s/
  run.sh                  # Main CLI entrypoint (build, up, down, restart, logs, status)
  boot-deploy.sh          # Waits for K3s, then deploys (called by systemd on boot)
  atlas-deploy.service    # systemd unit for auto-start on boot
  00-namespace.yaml       # "atlas" namespace
  01-secrets.yaml         # Secrets + ConfigMap (templated from .env via envsubst)
  10-atlas-auth.yaml      # Auth service deployment + service
  11-atlas-ui.yaml        # ATLAS UI deployment + service
  12-minio.yaml           # MinIO deployment + service
  13-minio-init-job.yaml  # One-shot job to create the S3 bucket
  20-middleware.yaml       # Traefik middlewares (header stripping + forwardAuth)
  21-ingressroute.yaml    # Traefik IngressRoutes (public + protected)
  traefik-config.yaml     # HelmChartConfig to set Traefik's exposed port

deploy/auth-service/
  auth_service.py         # Minimal FastAPI auth service (login, signup, cookie sessions)
  Dockerfile              # Auth service container image
```

## Quick Start

### 1. Configure Environment

Copy the example `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required variables for K3s deployment:

| Variable | Description | Example |
|----------|-------------|---------|
| `ATLAS_AUTH_SECRET` | HMAC secret for session cookies | Any random string (32+ chars) |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `S3_ACCESS_KEY` | MinIO root user | `minioadmin` |
| `S3_SECRET_KEY` | MinIO root password | Change from default! |

Optional variables (with defaults shown in `01-secrets.yaml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_BUCKET_NAME` | `atlas-files` | MinIO bucket name |
| `ATLAS_AUTH_SESSION_HOURS` | `24` | Session cookie lifetime |
| `VITE_APP_NAME` | `ATLAS` | Application name shown in UI |
| `VITE_FEATURE_POWERED_BY_ATLAS` | `false` | Show "Powered by ATLAS" branding |

### 2. Build Container Images

Build the ATLAS UI and auth service images with Podman, then import them into K3s containerd:

```bash
bash deploy/k3s/run.sh build
```

This runs:
1. `podman build` for `localhost/atlas-ui:latest` (from the root `Dockerfile`)
2. `podman build` for `localhost/atlas-auth:latest` (from `deploy/auth-service/Dockerfile`)
3. `podman save | sudo k3s ctr images import` for both images

### 3. Deploy

```bash
bash deploy/k3s/run.sh up
```

This applies all manifests in order: namespace, secrets/config, deployments, Traefik middleware, and ingress routes. It waits for all deployments to roll out before finishing.

### 4. Access ATLAS

Open your browser at **http://\<server-ip\>:8080**. You will be redirected to the login page. Create an account via the signup link.

## Architecture

```
Browser :8080
    |
    v
[Traefik Ingress]  (K3s built-in, port 8080)
    |
    |--> /login, /signup  -->  [atlas-auth :5000]   (public, no auth)
    |
    |--> /* (everything else)
    |       |
    |       +--> strip-client-auth-header middleware  (removes spoofed X-User-Email)
    |       +--> atlas-forward-auth middleware        (calls atlas-auth /auth endpoint)
    |       |       |
    |       |       +--> 200 + X-User-Email header   (authenticated)
    |       |       +--> 302 redirect to /login       (unauthenticated)
    |       |
    |       +--> [atlas-ui :8000]   (FastAPI backend + React frontend)
    |
    v
[MinIO :9000]  (S3-compatible file storage, internal only)
```

### Authentication Flow

1. Traefik receives a request for a protected route
2. The `strip-client-auth-header` middleware removes any client-provided `X-User-Email` header (prevents spoofing)
3. The `atlas-forward-auth` middleware sends the request to `atlas-auth /auth`
4. The auth service validates the session cookie:
   - Valid: returns `200` with `X-User-Email` header containing the user's email
   - Invalid: returns `302` redirect to `/login`
5. Traefik copies the `X-User-Email` response header to the upstream request
6. ATLAS backend receives the trusted `X-User-Email` header

### Data Persistence

Data is persisted via `hostPath` volumes. The K3s manifests (`10-atlas-auth.yaml`, `11-atlas-ui.yaml`, `12-minio.yaml`) use absolute paths. **You must edit these paths to match your project location** before deploying:

| Service | Host Path | Container Path |
|---------|-----------|----------------|
| atlas-auth | `<project>/data/auth` | `/data` |
| atlas-ui | `<project>/config` | `/app/config` |
| atlas-ui | `<project>/logs` | `/app/logs` |
| minio | `<project>/data/minio` | `/data` |

For example, if your project is at `/opt/atlas-ui-3`, update the `hostPath.path` values in each manifest accordingly.

## CLI Reference

All commands go through `deploy/k3s/run.sh`:

```bash
bash deploy/k3s/run.sh build              # Build images and import into K3s
bash deploy/k3s/run.sh up                 # Deploy all manifests
bash deploy/k3s/run.sh down               # Delete the atlas namespace
bash deploy/k3s/run.sh restart [svc]      # Restart one or all deployments
bash deploy/k3s/run.sh logs [svc]         # Follow logs (all or specific service)
bash deploy/k3s/run.sh status             # Show nodes, pods, ingress, middleware
```

Service aliases: `auth` or `atlas-auth`, `ui` or `atlas-ui`, `minio`.

## Auto-Update via Cron

To keep the deployment in sync with the latest code from a git remote, use the included `prod_setup.sh` script with cron.

### How It Works

`prod_setup.sh` runs these steps:

1. Acquires a lock file to prevent overlapping runs
2. Fetches the configured branch from the remote
3. Compares local and remote SHAs -- exits early if already up to date
4. Pulls new changes
5. Rebuilds container images (`run.sh build`)
6. Redeploys to K3s (`run.sh up`)

### Setup

1. **Create the script** at the project root (if it does not already exist):

   The script is provided at `prod_setup.sh` in the repository root. Review it and adjust the `BRANCH` and `REMOTE` variables at the top if needed:

   ```bash
   BRANCH="main"       # Branch to track
   REMOTE="origin"     # Git remote to pull from
   ```

2. **Create the logs directory:**

   ```bash
   mkdir -p logs
   ```

3. **Add the cron entry:**

   ```bash
   crontab -e
   ```

   Add this line to check for updates every 15 minutes:

   ```
   */15 * * * * /path/to/atlas-ui-3/prod_setup.sh >> /path/to/atlas-ui-3/logs/cron.log 2>&1
   ```

4. **Verify** the cron job is registered:

   ```bash
   crontab -l
   ```

### Monitoring Updates

Check the cron log:

```bash
tail -f logs/cron.log
```

Successful update output looks like:

```
[atlas-auto-update] 2026-02-18 01:15:00 Fetching origin/main...
[atlas-auto-update] 2026-02-18 01:15:01 New changes detected: abc1234 -> def5678
[atlas-auto-update] 2026-02-18 01:15:01 Switching to main and pulling...
[atlas-auto-update] 2026-02-18 01:15:02 Updated to def5678
[atlas-auto-update] 2026-02-18 01:15:02 Rebuilding container images...
[atlas-auto-update] 2026-02-18 01:17:30 Redeploying to K3s...
[atlas-auto-update] 2026-02-18 01:18:00 Auto-update complete. Deployed def5678
```

No-op output when nothing changed:

```
[atlas-auto-update] 2026-02-18 01:30:00 Fetching origin/main...
[atlas-auto-update] 2026-02-18 01:30:01 Already up to date at def5678. Nothing to do.
```

## Auto-Start on Boot

A systemd service ensures ATLAS is deployed automatically whenever the server starts (or restarts). The service waits for K3s to be ready, then runs `deploy/k3s/run.sh up`.

### Files

- `deploy/k3s/atlas-deploy.service` -- systemd unit file
- `deploy/k3s/boot-deploy.sh` -- helper script that waits for K3s API readiness then deploys

### Setup

1. **Copy the service file and enable it:**

   ```bash
   sudo cp deploy/k3s/atlas-deploy.service /etc/systemd/system/atlas-deploy.service
   sudo systemctl daemon-reload
   sudo systemctl enable atlas-deploy.service
   ```

2. **Verify:**

   ```bash
   systemctl is-enabled atlas-deploy.service   # should print "enabled"
   ```

### How It Works

On boot:
1. K3s starts (via its own systemd service)
2. `atlas-deploy.service` starts after `k3s.service`
3. `boot-deploy.sh` polls `k3s kubectl get nodes` until the API is responsive (up to 120s)
4. Runs `deploy/k3s/run.sh up` to apply all manifests

### Monitoring

Check boot deploy logs:

```bash
tail -f logs/boot-deploy.log
```

Check service status:

```bash
sudo systemctl status atlas-deploy.service
```

### Troubleshooting

If ATLAS is not running after a reboot:

```bash
# Check if the service ran
sudo systemctl status atlas-deploy.service

# Check boot deploy log for errors
tail -30 logs/boot-deploy.log

# Check if K3s itself is running
sudo systemctl status k3s

# Manual redeploy
bash deploy/k3s/run.sh up
```

## Configuration Reference

### Feature Flags

Feature flags are set in `01-secrets.yaml` under the ConfigMap section. These map directly to ATLAS `AppSettings` environment variables. Key flags for production:

```yaml
FEATURE_TOOLS_ENABLED: "true"           # Enable MCP tool execution
FEATURE_AGENT_MODE_AVAILABLE: "true"    # Allow agent mode toggle in UI
FEATURE_RAG_ENABLED: "false"            # Enable RAG (requires rag-sources.json)
AGENT_LOOP_STRATEGY: "think-act"        # Agent reasoning strategy
AGENT_MAX_STEPS: "30"                   # Max agent loop iterations
```

### Traefik Port

By default, Traefik exposes on port **8080** (configured in `traefik-config.yaml`). To change it:

```yaml
# traefik-config.yaml
spec:
  valuesContent: |-
    ports:
      web:
        exposedPort: 443    # Change to your desired port
```

After changing, copy the file to K3s manifests:

```bash
sudo cp deploy/k3s/traefik-config.yaml /var/lib/rancher/k3s/server/manifests/traefik-config.yaml
```

### Adding TLS

For HTTPS, add a TLS secret and update the IngressRoute:

```yaml
# In 21-ingressroute.yaml, change entryPoints from "web" to "websecure"
# and add a tls section:
spec:
  entryPoints:
    - websecure
  tls:
    secretName: atlas-tls
```

Create the TLS secret:

```bash
sudo k3s kubectl create secret tls atlas-tls \
  --cert=/path/to/cert.pem \
  --key=/path/to/key.pem \
  -n atlas
```

## Troubleshooting

### Pods not starting

```bash
bash deploy/k3s/run.sh status
sudo k3s kubectl describe pod <pod-name> -n atlas
sudo k3s kubectl logs <pod-name> -n atlas
```

### Images not found

If pods show `ImagePullBackOff` or `ErrImageNeverPull`, re-import the images:

```bash
bash deploy/k3s/run.sh build
```

Verify images exist in containerd:

```bash
sudo k3s ctr images list | grep atlas
```

### Auth redirect loop

Check that the auth service is healthy:

```bash
sudo k3s kubectl logs deployment/atlas-auth -n atlas
```

Verify the `ATLAS_AUTH_SECRET` is set in your `.env`.

### MinIO bucket not created

Check the init job:

```bash
sudo k3s kubectl logs job/minio-init -n atlas
```

Re-run the init job:

```bash
sudo k3s kubectl delete job minio-init -n atlas --ignore-not-found
bash deploy/k3s/run.sh up
```

### Cron auto-update not running

Check cron is installed and the service is active:

```bash
systemctl status cron        # Debian/Ubuntu
systemctl status crond       # Fedora/RHEL
```

Verify the crontab entry exists:

```bash
crontab -l | grep prod_setup
```

Check the log for errors:

```bash
tail -20 logs/cron.log
```

Common issues:
- `prod_setup.sh: No such file or directory` -- script is missing or not executable (`chmod +x prod_setup.sh`)
- `Permission denied` -- run `chmod +x prod_setup.sh`
- Lock file stuck -- remove `.auto-update.lock` if the previous process crashed
