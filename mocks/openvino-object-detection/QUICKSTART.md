# Quick Start Guide - OpenVINO Object Detection MCP Server

This is a quick reference guide for deploying the OpenVINO Object Detection MCP Server.

## Docker Quick Start

### Build the Image

Choose one of the following base images:

```bash
# Ubuntu (recommended)
docker build -f Dockerfile.ubuntu -t openvino-detection:ubuntu .

# RHEL UBI
docker build -f Dockerfile.rhel -t openvino-detection:rhel .
```

### Run the Container

```bash
docker run -d \
  --name openvino-server \
  -p 8006:8006 \
  -v openvino-models:/tmp/openvino_models \
  openvino-detection:ubuntu
```

### Test the Server

```bash
# Basic test
curl http://localhost:8006/mcp

# Test with a sample image
# First, copy an image into the container
docker cp /path/to/your/image.jpg openvino-server:/tmp/test.jpg

# Then use the MCP client to detect objects
```

## Docker Compose Quick Start

```bash
# Start the server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the server
docker-compose down
```

## Kubernetes/Helm Quick Start

### Prerequisites
- Kubernetes cluster running
- kubectl configured
- Helm 3.x installed
- Docker image pushed to a registry

### Install

```bash
# Basic installation
helm install openvino-server ./helm/openvino-server --namespace mcp --create-namespace

# With custom image
helm install openvino-server ./helm/openvino-server \
  --namespace mcp \
  --create-namespace \
  --set image.repository=your-registry/openvino-detection \
  --set image.tag=1.0.0

# Development environment
helm install openvino-server ./helm/openvino-server \
  -f ./helm/openvino-server/values-dev.yaml \
  --namespace mcp-dev \
  --create-namespace

# Production environment
helm install openvino-server ./helm/openvino-server \
  -f ./helm/openvino-server/values-prod.yaml \
  --namespace mcp-prod \
  --create-namespace
```

### Verify

```bash
# Check deployment
kubectl get all -n mcp

# Check logs
kubectl logs -n mcp deployment/openvino-server

# Test locally
kubectl port-forward -n mcp svc/openvino-server 8006:8006
curl http://localhost:8006/mcp
```

### Upgrade

```bash
helm upgrade openvino-server ./helm/openvino-server \
  --namespace mcp \
  --set image.tag=1.1.0
```

### Uninstall

```bash
helm uninstall openvino-server --namespace mcp
```

## Local Python Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Server

```bash
# HTTP transport (default)
python main.py

# Custom host/port
python main.py --host 0.0.0.0 --port 8080

# SSE transport
python main.py --sse --port 8006

# STDIO transport
python main.py --stdio
```

### Test Detection

Once the server is running, you can test object detection:

```python
# Using Python MCP client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_detection():
    server_params = StdioServerParameters(
        command="python",
        args=["main.py", "--stdio"],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Detect objects in an image
            result = await session.call_tool(
                "detect_objects",
                arguments={
                    "image_path": "/path/to/image.jpg",
                    "model_name": "yolo11n",
                    "confidence_threshold": 0.25
                }
            )
            print(result)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| PYTHONUNBUFFERED | 1 | Python unbuffered output |

## Common Deployment Scenarios

### Single Instance (Development)

```bash
helm install openvino-dev ./helm/openvino-server \
  --set replicaCount=1 \
  --set service.type=NodePort \
  --namespace dev
```

### High Availability (Production)

```bash
helm install openvino-prod ./helm/openvino-server \
  --set replicaCount=3 \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=3 \
  --set autoscaling.maxReplicas=10 \
  --set service.type=LoadBalancer \
  --namespace prod
```

### With Ingress

```bash
helm install openvino-server ./helm/openvino-server \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=openvino.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix \
  --namespace mcp
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs openvino-server

# Or for Kubernetes
kubectl logs -n mcp deployment/openvino-server
```

### Health check failing
```bash
# Test endpoint manually
curl http://localhost:8006/mcp
```

### Model download errors
- Ensure the container has internet access
- Check disk space in /tmp/openvino_models
- Verify network connectivity to download servers

### Image pull errors
- Verify image exists in registry
- Check imagePullSecrets configuration
- Verify network connectivity

### Out of memory errors
- Increase container memory limits
- Use smaller models (yolo11n instead of yolo11x)
- Reduce batch size if processing multiple images

## Performance Tips

- Use persistent volumes for model cache to avoid re-downloading
- For GPU acceleration, ensure OpenVINO GPU plugin is available
- Use smaller models (yolo11n) for real-time applications
- Use larger models (yolo11l, yolo11x) for accuracy-critical tasks
- Pre-warm the server by running a test detection on startup

## More Information

For detailed documentation, see [DOCKER_K8S_DEPLOYMENT.md](DOCKER_K8S_DEPLOYMENT.md)
