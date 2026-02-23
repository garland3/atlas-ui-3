# Docker Compose Deployment Guide

Last updated: 2026-02-18

> **Note:** This is an example deployment intended for personal home servers and experimentation.
> It is not hardened for production use. Use it as a reference for building your own
> deployment pipeline, and review all security settings before exposing to untrusted networks.

Deploy ATLAS using Docker Compose (or Podman Compose) with Nginx reverse proxy, forward authentication, and MinIO file storage.

## Prerequisites

- **Docker** with Docker Compose v2, or **Podman** with `podman-compose`
- A copy of this repository

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env and set your API keys and ATLAS_AUTH_SECRET
```

### 2. Deploy

```bash
bash deploy/run.sh up
```

This builds and starts all containers. Access ATLAS at **http://localhost:8080**.

### 3. Manage

```bash
bash deploy/run.sh status      # Show container status
bash deploy/run.sh logs -f     # Follow all logs
bash deploy/run.sh restart     # Restart the stack
bash deploy/run.sh down        # Stop and remove containers
```

## Architecture

```
Browser :8080
    |
[Nginx]  (reverse proxy, port 8080)
    |
    |--> /login, /signup  -->  [atlas-auth :5000]
    |
    |--> /* (auth_request to atlas-auth /auth)
    |       |
    |       +--> strips X-User-Email, sets from auth response
    |       +--> [atlas-ui :8000]   (FastAPI + React)
    |
[MinIO :9000]  (internal, console on :9001)
```

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `nginx` | `nginx:alpine` | 8080 (exposed) | Reverse proxy with auth |
| `atlas-ui` | Built from `Dockerfile` | 8000 (internal) | ATLAS backend + frontend |
| `atlas-auth` | Built from `deploy/auth-service/Dockerfile` | 5000 (internal) | Login, signup, session validation |
| `minio` | `minio/minio:latest` | 9001 (console) | S3-compatible file storage |
| `minio-init` | `minio/mc:latest` | - | One-shot bucket creation |

## Files

- `deploy/docker-compose.prod.yml` -- Compose file defining all services
- `deploy/nginx.conf` -- Nginx configuration with auth_request and WebSocket support
- `deploy/run.sh` -- CLI wrapper that auto-detects Docker or Podman Compose
- `deploy/auth-service/` -- Auth service source and Dockerfile

## Configuration

The compose file reads from the project root `.env`. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ATLAS_AUTH_SECRET` | Yes | Session cookie signing secret |
| `OPENAI_API_KEY` | Depends | OpenAI API key (if using OpenAI models) |
| `ANTHROPIC_API_KEY` | Depends | Anthropic API key (if using Claude models) |
| `S3_ACCESS_KEY` | No | MinIO root user (default: `minioadmin`) |
| `S3_SECRET_KEY` | No | MinIO root password (default: `minioadmin`) |

## Data Persistence

Volumes are bind-mounted from the project directory:

| Host Path | Container Path | Service |
|-----------|----------------|---------|
| `config/` | `/app/config` | atlas-ui |
| `logs/` | `/app/logs` | atlas-ui |
| `data/auth/` | `/data` | atlas-auth |
| `data/minio/` | `/data` | minio |
