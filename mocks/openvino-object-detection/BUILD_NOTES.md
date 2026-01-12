# Build Notes - OpenVINO Object Detection MCP Server

This document contains important notes and considerations for building the OpenVINO Object Detection MCP Server container images.

## Base Image Selection

### Ubuntu 24.04 (Recommended)
- **Pros:**
  - Widely used and well-documented
  - Good package availability
  - Smaller image size compared to Fedora
  - Long-term support
- **Cons:**
  - May require additional PPAs for cutting-edge packages
- **Best for:** General deployment, development, CI/CD

### RHEL UBI 9
- **Pros:**
  - Enterprise support from Red Hat
  - Security-focused with minimal attack surface
  - Compliance-friendly (FIPS, STIG)
  - Compatible with OpenShift
- **Cons:**
  - Larger image size
  - Some packages may require subscriptions
- **Best for:** Enterprise deployments, regulated environments, OpenShift

## Dependencies

### System Dependencies
- **Python 3.11+**: Required for FastMCP and modern Python features
- **libgl1**: OpenGL library required by OpenCV for image processing
- **libglib2.0-0**: GLib library required by OpenCV
- **libgomp1**: OpenMP library for parallel processing
- **curl**: For health checks and downloads
- **ca-certificates**: For secure HTTPS downloads

### Python Dependencies
See `requirements.txt` for full list:
- **openvino>=2025.1.0**: Intel OpenVINO inference engine
- **nncf>=2.16.0**: Neural Network Compression Framework
- **ultralytics>=8.3.0**: YOLOv11 models and utilities
- **opencv-python-headless>=4.8.0**: Image processing without GUI dependencies
- **numpy>=1.24.0**: Numerical computations
- **Pillow>=9.0.0**: Image format support
- **fastmcp>=0.1.0**: MCP server framework

## Build Process

### Image Size Optimization
The Dockerfiles implement several optimizations:
1. **Multi-stage not needed**: Single-stage build is sufficient for this use case
2. **Package cleanup**: Remove apt/dnf cache after installation
3. **Headless OpenCV**: Use opencv-python-headless to avoid X11 dependencies
4. **Virtual environment**: Isolate Python dependencies

### Security Considerations
1. **Non-root user**: Container runs as `mcpuser` (not root)
2. **Minimal dependencies**: Only install required packages
3. **Health checks**: Built-in health monitoring
4. **Immutable files**: Application files owned by mcpuser

### Model Caching
- Models are cached in `/tmp/openvino_models`
- First run downloads models (~10-50MB depending on variant)
- Use Docker volumes for persistent cache across container restarts
- Pre-populate cache in custom images for faster startup

## Build Variations

### Development Build
```bash
docker build -f Dockerfile.ubuntu -t openvino-detection:dev .
```

### Production Build with Pre-cached Models
Create a custom Dockerfile that extends the base:

```dockerfile
FROM openvino-detection:ubuntu

USER root

# Pre-download models during build
RUN python3 << 'EOF'
from ultralytics import YOLO
import tempfile
import os

# Set model cache location
os.environ['YOLO_CACHE_DIR'] = '/tmp/openvino_models'

# Download and export models
for model in ['yolo11n', 'yolo11s']:
    print(f"Downloading {model}...")
    yolo = YOLO(f"{model}.pt")
    yolo.export(format="openvino", dynamic=True, half=False)
    print(f"Cached {model}")
EOF

# Fix permissions
RUN chown -R mcpuser:mcpuser /tmp/openvino_models

USER mcpuser
```

### Multi-arch Build
```bash
# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f Dockerfile.ubuntu \
  -t openvino-detection:multi \
  --push .
```

## Common Build Issues

### Issue: OpenCV import errors
**Solution:** Ensure libgl1 and libglib2.0-0 are installed

### Issue: Out of memory during build
**Solution:** Increase Docker daemon memory limit or build on a machine with more RAM

### Issue: Package conflicts
**Solution:** Use specific package versions in requirements.txt

### Issue: Slow first run
**Solution:** Pre-cache models in the image (see Production Build above)

## Testing the Build

### Basic Functionality Test
```bash
# Start container
docker run -d --name test-openvino -p 8006:8006 openvino-detection:ubuntu

# Wait for startup
sleep 10

# Test health endpoint
curl http://localhost:8006/mcp

# Clean up
docker stop test-openvino
docker rm test-openvino
```

### Load Test
Use the provided `build_and_test_dockerfiles.sh` script to run comprehensive tests.

## Image Tagging Strategy

Recommended tagging convention:
- `openvino-detection:latest` - Latest stable build
- `openvino-detection:1.0.0` - Semantic version
- `openvino-detection:ubuntu` - Base OS variant
- `openvino-detection:rhel` - Enterprise variant
- `openvino-detection:dev` - Development build
- `openvino-detection:1.0.0-ubuntu` - Version + OS variant

## Registry Push

```bash
# Tag for registry
docker tag openvino-detection:ubuntu your-registry.com/openvino-detection:1.0.0

# Push to registry
docker push your-registry.com/openvino-detection:1.0.0
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build Docker image
  run: |
    docker build -f Dockerfile.ubuntu -t openvino-detection:${{ github.sha }} .
    docker tag openvino-detection:${{ github.sha }} openvino-detection:latest
```

### GitLab CI Example
```yaml
build:
  stage: build
  script:
    - docker build -f Dockerfile.ubuntu -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

## Performance Benchmarks

Approximate build times (on 4-core 8GB RAM machine):
- Ubuntu base: ~3-5 minutes
- RHEL UBI base: ~4-6 minutes
- With pre-cached models: +5-10 minutes

Final image sizes:
- Ubuntu: ~2.5-3GB
- RHEL: ~3-3.5GB
- With cached models: +100-500MB

## Maintenance

- Update base images monthly for security patches
- Update Python dependencies quarterly or when CVEs are found
- Test new OpenVINO releases in dev before production deployment
- Monitor image size growth and optimize as needed
