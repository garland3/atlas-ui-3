# OpenVINO Object Detection MCP

This MCP (Model Context Protocol) server provides object detection capabilities using YOLOv11 models optimized with Intel OpenVINO for efficient inference.

## Features

- **YOLOv11 Object Detection**: State-of-the-art object detection with multiple model sizes
- **OpenVINO Optimization**: Hardware-accelerated inference on Intel CPUs, GPUs, and VPUs
- **Automatic Model Download**: Models are downloaded and converted automatically on first use
- **Flexible Input**: Accept images via file path or base64-encoded strings
- **Visual Output**: Returns both structured detection data and annotated overlay images
- **COCO Classes**: Detects 80 different object categories

## Installation

```bash
pip install openvino>=2025.1.0 nncf>=2.16.0 ultralytics>=8.3.0 opencv-python numpy Pillow fastmcp
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
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

**Returns:**
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
    "overlay_base64": "base64_encoded_png...",
    "output_path": "/path/to/output.png"
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

### 2. `detect_objects_base64`

Perform object detection on a base64-encoded image.

**Parameters:**
- `image_base64` (str): Base64-encoded image data
- `model_name` (str, optional): YOLO model variant (default: "yolo11n")
- `confidence_threshold` (float, optional): Minimum confidence score (default: 0.25)
- `iou_threshold` (float, optional): IoU threshold for NMS (default: 0.45)
- `device` (str, optional): OpenVINO device (default: "AUTO")

### 3. `list_available_models`

Get information about available YOLO model variants.

**Returns:**
```json
{
  "results": {
    "models": [
      {
        "name": "yolo11n",
        "description": "YOLOv11 Nano - Fastest model",
        "parameters": "~2.6M",
        "speed": "Fastest",
        "accuracy": "Good"
      }
    ],
    "recommended": "yolo11n"
  }
}
```

### 4. `get_class_labels`

Get the list of detectable object classes (COCO dataset).

**Returns:**
```json
{
  "results": {
    "classes": [
      {"id": 0, "name": "person"},
      {"id": 1, "name": "bicycle"},
      ...
    ],
    "total_classes": 80
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
- People: person
- Vehicles: bicycle, car, motorcycle, airplane, bus, train, truck, boat
- Animals: bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe
- Sports: frisbee, skis, snowboard, sports ball, kite, baseball bat/glove, skateboard, surfboard, tennis racket
- Food: banana, apple, sandwich, orange, broccoli, carrot, hot dog, pizza, donut, cake
- Furniture: chair, couch, bed, dining table, toilet
- Electronics: tv, laptop, mouse, remote, keyboard, cell phone
- And many more...

## Usage Example

```python
# Using the MCP server
from fastmcp import Client

async def main():
    async with Client("openvino_object_detection") as client:
        # Detect objects in an image
        result = await client.call_tool("detect_objects", {
            "image_path": "/path/to/image.jpg",
            "model_name": "yolo11n",
            "confidence_threshold": 0.3
        })
        
        # Process results
        detections = result["results"]["detections"]
        for det in detections:
            print(f"Found {det['class_name']} with confidence {det['confidence']:.2f}")
```

## Running the Server

```bash
# Direct execution
python main.py

# Or using uvx/uv
uvx fastmcp run main.py
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
