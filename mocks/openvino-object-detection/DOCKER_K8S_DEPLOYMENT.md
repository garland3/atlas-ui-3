# Docker and Kubernetes Deployment Guide

Complete guide for deploying the OpenVINO Object Detection MCP Server in Docker and Kubernetes environments.

## Table of Contents

- [Docker Deployment](#docker-deployment)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Helm Chart Deployment](#helm-chart-deployment)
- [Configuration](#configuration)
- [Monitoring and Logging](#monitoring-and-logging)
- [Troubleshooting](#troubleshooting)

## Docker Deployment

### Building the Image

#### Ubuntu-based Image (Recommended)

```bash
cd mocks/openvino-object-detection
docker build -f Dockerfile.ubuntu -t openvino-detection:ubuntu .
```

**Multi-stage Build:**
- Builder stage: Includes gcc, g++, and all build tools for compiling Python packages
- Runtime stage: Minimal Ubuntu 24.04 with only runtime dependencies
- Result: 30-40% smaller image (~2-2.5GB vs ~3.5-4GB single-stage)

#### RHEL UBI-based Image

```bash
cd mocks/openvino-object-detection
docker build -f Dockerfile.rhel -t openvino-detection:rhel .
```

**Multi-stage Build:**
- Builder stage: Full ubi9 with gcc, python-devel for compilation
- Runtime stage: Minimal ubi9-minimal with microdnf for smallest footprint
- Result: Optimized for enterprise environments with reduced attack surface

### Running a Container

#### Basic Run

```bash
docker run -d \
  --name openvino-server \
  -p 8006:8006 \
  openvino-detection:ubuntu
```

#### With Persistent Model Cache

```bash
docker run -d \
  --name openvino-server \
  -p 8006:8006 \
  -v openvino-models:/tmp/openvino_models \
  openvino-detection:ubuntu
```

#### With Resource Limits

```bash
docker run -d \
  --name openvino-server \
  -p 8006:8006 \
  -v openvino-models:/tmp/openvino_models \
  --memory="4g" \
  --cpus="2" \
  openvino-detection:ubuntu
```

#### With Custom Configuration

```bash
docker run -d \
  --name openvino-server \
  -p 8006:8006 \
  -v openvino-models:/tmp/openvino_models \
  -e PYTHONUNBUFFERED=1 \
  openvino-detection:ubuntu
```

### Container Management

```bash
# View logs
docker logs -f openvino-server

# Check container status
docker ps -f name=openvino-server

# Stop container
docker stop openvino-server

# Start container
docker start openvino-server

# Remove container
docker rm -f openvino-server

# View resource usage
docker stats openvino-server
```

## Docker Compose Deployment

### Basic Deployment

```bash
cd mocks/openvino-object-detection
docker-compose up -d
```

### View Logs

```bash
docker-compose logs -f
```

### Scale Services

```bash
# Run multiple instances
docker-compose up -d --scale openvino-detection-ubuntu=3
```

### Stop Services

```bash
docker-compose down
```

### Clean Up (including volumes)

```bash
docker-compose down -v
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- Container registry with pushed images

### Manual Deployment

#### 1. Create Namespace

```bash
kubectl create namespace openvino-mcp
```

#### 2. Create Deployment

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openvino-detection
  namespace: openvino-mcp
  labels:
    app: openvino-detection
spec:
  replicas: 2
  selector:
    matchLabels:
      app: openvino-detection
  template:
    metadata:
      labels:
        app: openvino-detection
    spec:
      containers:
      - name: openvino-server
        image: your-registry/openvino-detection:1.0.0
        ports:
        - containerPort: 8006
          name: http
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        volumeMounts:
        - name: model-cache
          mountPath: /tmp/openvino_models
        livenessProbe:
          httpGet:
            path: /mcp
            port: 8006
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          httpGet:
            path: /mcp
            port: 8006
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
      volumes:
      - name: model-cache
        emptyDir: {}
```

Apply:
```bash
kubectl apply -f deployment.yaml
```

#### 3. Create Service

Create `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: openvino-detection
  namespace: openvino-mcp
spec:
  type: ClusterIP
  ports:
  - port: 8006
    targetPort: 8006
    protocol: TCP
    name: http
  selector:
    app: openvino-detection
```

Apply:
```bash
kubectl apply -f service.yaml
```

#### 4. Create Ingress (Optional)

Create `ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: openvino-detection
  namespace: openvino-mcp
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: openvino.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: openvino-detection
            port:
              number: 8006
```

Apply:
```bash
kubectl apply -f ingress.yaml
```

### Horizontal Pod Autoscaling

Create `hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: openvino-detection
  namespace: openvino-mcp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: openvino-detection
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

Apply:
```bash
kubectl apply -f hpa.yaml
```

## Helm Chart Deployment

### Chart Structure

```
helm/openvino-server/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml
│   ├── configmap.yaml
│   ├── serviceaccount.yaml
│   ├── _helpers.tpl
│   └── NOTES.txt
└── .helmignore
```

### Installation

#### Development Environment

```bash
helm install openvino-dev ./helm/openvino-server \
  -f ./helm/openvino-server/values-dev.yaml \
  --namespace openvino-dev \
  --create-namespace
```

#### Production Environment

```bash
helm install openvino-prod ./helm/openvino-server \
  -f ./helm/openvino-server/values-prod.yaml \
  --namespace openvino-prod \
  --create-namespace
```

#### Custom Values

```bash
helm install openvino-server ./helm/openvino-server \
  --set image.repository=your-registry/openvino-detection \
  --set image.tag=1.0.0 \
  --set replicaCount=3 \
  --set resources.limits.memory=4Gi \
  --namespace openvino \
  --create-namespace
```

### Chart Management

#### Upgrade

```bash
helm upgrade openvino-server ./helm/openvino-server \
  --namespace openvino \
  --set image.tag=1.1.0
```

#### Rollback

```bash
# List releases
helm history openvino-server -n openvino

# Rollback to previous version
helm rollback openvino-server -n openvino

# Rollback to specific revision
helm rollback openvino-server 2 -n openvino
```

#### Uninstall

```bash
helm uninstall openvino-server --namespace openvino
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| PYTHONUNBUFFERED | Enable unbuffered Python output | 1 |

### Resource Requirements

Recommended resource allocations:

#### Development
- CPU: 500m (request), 1000m (limit)
- Memory: 1Gi (request), 2Gi (limit)
- Replicas: 1

#### Production
- CPU: 1000m (request), 2000m (limit)
- Memory: 2Gi (request), 4Gi (limit)
- Replicas: 3-10 (with autoscaling)

### Persistent Storage

For production deployments, use persistent volumes:

```yaml
volumes:
- name: model-cache
  persistentVolumeClaim:
    claimName: openvino-models-pvc
```

Create PVC:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: openvino-models-pvc
  namespace: openvino-mcp
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 5Gi
  storageClassName: standard
```

## Monitoring and Logging

### Health Checks

The server exposes a health endpoint at `/mcp`:

```bash
# Direct check
curl http://openvino-server:8006/mcp

# Through kubectl
kubectl exec -n openvino-mcp deployment/openvino-detection -- \
  curl -f http://localhost:8006/mcp
```

### Logging

#### View Pod Logs

```bash
# All pods
kubectl logs -n openvino-mcp -l app=openvino-detection

# Specific pod
kubectl logs -n openvino-mcp <pod-name>

# Follow logs
kubectl logs -n openvino-mcp -l app=openvino-detection -f

# Previous container logs (if pod crashed)
kubectl logs -n openvino-mcp <pod-name> --previous
```

### Metrics (Prometheus)

Add Prometheus annotations to deployment:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8006"
    prometheus.io/path: "/metrics"
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl get pods -n openvino-mcp

# Describe pod for events
kubectl describe pod -n openvino-mcp <pod-name>

# Check logs
kubectl logs -n openvino-mcp <pod-name>
```

### Image Pull Errors

```bash
# Check if image exists
docker pull your-registry/openvino-detection:1.0.0

# Create image pull secret
kubectl create secret docker-registry regcred \
  --docker-server=your-registry \
  --docker-username=username \
  --docker-password=password \
  --namespace=openvino-mcp

# Reference in deployment
spec:
  imagePullSecrets:
  - name: regcred
```

### Out of Memory

Increase memory limits in deployment:

```yaml
resources:
  limits:
    memory: "8Gi"
```

Or use smaller models:
- Switch from yolo11l to yolo11n
- Reduce concurrent requests

### Slow Response Times

1. Check resource usage:
```bash
kubectl top pods -n openvino-mcp
```

2. Scale up replicas:
```bash
kubectl scale deployment openvino-detection -n openvino-mcp --replicas=5
```

3. Verify model cache is working:
```bash
kubectl exec -n openvino-mcp <pod-name> -- ls -la /tmp/openvino_models
```

### Network Issues

```bash
# Test service from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n openvino-mcp -- \
  curl http://openvino-detection:8006/mcp

# Check service endpoints
kubectl get endpoints -n openvino-mcp openvino-detection
```

## Best Practices

1. **Use persistent volumes** for model cache in production
2. **Set resource limits** to prevent resource exhaustion
3. **Enable autoscaling** for variable workloads
4. **Use health checks** for automatic recovery
5. **Monitor resource usage** and adjust limits accordingly
6. **Use smaller models** for real-time requirements
7. **Pre-cache models** in custom images for faster startup
8. **Implement proper logging** for debugging
9. **Use image pull secrets** for private registries
10. **Regular security updates** for base images and dependencies

## Security Considerations

1. **Non-root user**: Container runs as mcpuser
2. **Read-only filesystem**: Consider using securityContext
3. **Network policies**: Restrict traffic to necessary services
4. **Resource quotas**: Prevent resource exhaustion
5. **Image scanning**: Scan images for vulnerabilities
6. **RBAC**: Use proper service accounts with minimal permissions

Example security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  capabilities:
    drop:
      - ALL
  readOnlyRootFilesystem: false
  allowPrivilegeEscalation: false
```

## Appendix: Complete Production Example

Full production deployment with all components:

```bash
# Create namespace
kubectl create namespace openvino-prod

# Deploy with Helm using production values
helm install openvino-server ./helm/openvino-server \
  -f ./helm/openvino-server/values-prod.yaml \
  --namespace openvino-prod

# Verify deployment
kubectl get all -n openvino-prod

# Test the service
kubectl port-forward -n openvino-prod svc/openvino-server 8006:8006
curl http://localhost:8006/mcp
```

This completes the deployment guide for the OpenVINO Object Detection MCP Server.
