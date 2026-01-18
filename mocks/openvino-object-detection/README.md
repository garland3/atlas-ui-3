# OpenVINO Object Detection MCP (HTTP Server)

This is an external HTTP MCP server that provides object detection capabilities using YOLOv11 models optimized with Intel OpenVINO for efficient inference.

## Features

- **YOLOv11 Object Detection**: State-of-the-art object detection with multiple model sizes
- **OpenVINO Optimization**: Hardware-accelerated inference on Intel CPUs, GPUs, and VPUs
- **HTTP Transport**: Runs as an HTTP server for external service deployment
- **Build-Time Model Conversion**: Docker images pre-convert all models during build (no PyTorch/CUDA in runtime)
- **Automatic Model Download**: Local development automatically downloads models on first use
- **Flexible Input**: Accept images via file path or base64-encoded strings
- **Visual Output**: Returns both structured detection data and annotated overlay images
- **COCO Classes**: Detects 80 different object categories
- **Optimized Docker Images**: 50-60% smaller images with pre-converted models

## Installation

```bash
pip install -r requirements.txt
```

## Running the Server

### HTTP Server (Default)

```bash
python main.py
# Server starts on http://127.0.0.1:8006/mcp
```

### Custom Port/Host

```bash
python main.py --host 0.0.0.0 --port 8080
```

### SSE Transport

```bash
python main.py --sse --port 8006
```

### STDIO Transport (for local MCP)

```bash
python main.py --stdio
```

## Configuration

Add the following to your MCP config to use this server:

```json
{
  "openvino-object-detection": {
    "enabled": true,
    "url": "http://127.0.0.1:8006/mcp",
    "transport": "http",
    "groups": ["users"],
    "description": "Object detection using YOLOv11 with OpenVINO optimization",
    "short_description": "OpenVINO YOLOv11 object detection"
  }
}
```

## Available Tools

### 1. `detect_objects`

Perform object detection on an image file.

**Parameters:**
- `image_path` (str): Path to the input image file
- `model_name` (str, optional): YOLO model variant (default: "yolo11n")
- `confidence_threshold` (float, optional): Minimum confidence score (default: 0.25)
- `iou_threshold` (float, optional): IoU threshold for NMS (default: 0.45)
- `device` (str, optional): OpenVINO device - "AUTO", "CPU", "GPU" (default: "AUTO")
- `output_path` (str, optional): Path to save the annotated output image

### 2. `detect_objects_base64`

Perform object detection on a base64-encoded image.

**Parameters:**
- `image_base64` (str): Base64-encoded image string
- `model_name` (str, optional): YOLO model variant (default: "yolo11n")
- `confidence_threshold` (float, optional): Minimum confidence score (default: 0.25)
- `iou_threshold` (float, optional): IoU threshold for NMS (default: 0.45)
- `device` (str, optional): OpenVINO device (default: "AUTO")

### 3. `list_available_models`

Get information about available YOLO model variants.

### 4. `get_class_labels`

Get the list of 80 detectable COCO object classes.

## Response Format

```json
{
  "results": {
    "detections": [
      {
        "class_id": 0,
        "class_name": "person",
        "confidence": 0.92,
        "bbox": {
          "x1": 100, "y1": 50,
          "x2": 300, "y2": 400,
          "width": 200, "height": 350
        }
      }
    ],
    "detection_count": 1,
    "image_size": {"width": 640, "height": 480},
    "overlay_base64": "base64_encoded_png..."
  },
  "meta_data": {
    "model_name": "yolo11n",
    "device": "AUTO",
    "inference_time_ms": 45.2,
    "elapsed_ms": 120.5,
    "is_error": false
  }
}
```

## Supported Models

| Model | Parameters | Speed | Accuracy | Use Case |
|-------|------------|-------|----------|----------|
| yolo11n | ~2.6M | Fastest | Good | Real-time, embedded |
| yolo11s | ~9.4M | Fast | Better | General purpose |
| yolo11m | ~20.1M | Moderate | High | Balanced |
| yolo11l | ~25.3M | Slower | Very High | High accuracy |
| yolo11x | ~56.9M | Slowest | Highest | Maximum accuracy |

## Supported Object Classes

The models detect 80 COCO classes including:
- **People**: person
- **Vehicles**: bicycle, car, motorcycle, airplane, bus, train, truck, boat
- **Animals**: bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe
- **Sports**: frisbee, skis, snowboard, sports ball, kite, baseball bat/glove, skateboard, surfboard, tennis racket
- **Food**: banana, apple, sandwich, orange, broccoli, carrot, hot dog, pizza, donut, cake
- **Furniture**: chair, couch, bed, dining table, toilet
- **Electronics**: tv, laptop, mouse, remote, keyboard, cell phone
- And many more...

## Docker Deployment

Example Dockerfile:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8006

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8006"]
```

Build and run:

```bash
docker build -t openvino-detection .
docker run -p 8006:8006 openvino-detection
```

## Performance Notes

- First run will download the YOLO model (~10-50MB depending on variant)
- OpenVINO automatically selects the best available hardware
- Model is cached after first load for faster subsequent inferences
- For GPU acceleration, ensure OpenVINO GPU plugin is installed

## License

This MCP uses:
- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) - AGPL-3.0
- [OpenVINO](https://github.com/openvinotoolkit/openvino) - Apache 2.0
