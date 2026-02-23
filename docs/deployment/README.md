# Deployment Guide

Last updated: 2026-02-18

This directory contains deployment guides for running ATLAS in production environments.

## Available Deployment Methods

| Method | Guide | Best For |
|--------|-------|----------|
| **K3s + Traefik** | [k3s-deployment.md](k3s-deployment.md) | Single-node or small-cluster production deployments with built-in auth, TLS-ready ingress, and auto-updates |
| **Docker Compose** | [docker-compose-deployment.md](docker-compose-deployment.md) | Quick single-server deployments using Docker or Podman |
| **Docker (standalone)** | [Installation Guide](../getting-started/installation.md) | Development or simple single-container setups |

## Architecture Overview

All production deployment methods share the same core architecture:

```
Client Browser
      |
  [Reverse Proxy / Ingress]    (Traefik, Nginx, etc.)
      |
  [Auth Service]                (Cookie-based auth with bcrypt)
      |
  [ATLAS UI + Backend]          (FastAPI serving React frontend)
      |
  [MinIO / S3]                  (File storage)
```

The auth service runs as a separate container and integrates with the reverse proxy via forward authentication. See [reverse-proxy-examples.md](../example/reverse-proxy-examples.md) for proxy-specific configuration details.
