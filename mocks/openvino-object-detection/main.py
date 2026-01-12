#!/usr/bin/env python3
"""
OpenVINO Object Detection MCP Server (HTTP Transport)

Provides YOLOv11 object detection with OpenVINO optimization through MCP protocol.
This version runs as an HTTP server for external service deployment.

Takes an input image file or base64 data, performs object detection, and returns:
- Detection results in structured format
- Overlay image with detected objects visualized
"""

import argparse
import base64
import io
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
from fastmcp import FastMCP

# Global model cache
_model_cache = {}

# COCO class names for object detection
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
    'toothbrush'
]

# Colors for visualization (one per class, will cycle through)
COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255),
    (0, 255, 255), (128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 0),
    (128, 0, 128), (0, 128, 128), (255, 128, 0), (255, 0, 128), (128, 255, 0),
    (0, 255, 128), (128, 0, 255), (0, 128, 255), (255, 128, 128), (128, 255, 128)
]

# Initialize FastMCP server
mcp = FastMCP(
    name="OpenVINO Object Detection",
    instructions="""
    This server provides object detection using YOLOv11 models optimized with Intel OpenVINO.
    Use the available tools to detect objects in images provided via file path or base64 encoding.
    The server returns detection results with bounding boxes, class labels, confidence scores,
    and an annotated overlay image.
    """
)


def get_color(class_id: int) -> tuple:
    """Get a color for a given class ID."""
    return COLORS[class_id % len(COLORS)]


def _ensure_model_downloaded(model_name: str = "yolo11n") -> Path:
    """
    Ensure the YOLO model is downloaded and converted to OpenVINO format.
    
    Args:
        model_name: Name of the YOLO model (e.g., 'yolo11n', 'yolo11s', etc.)
    
    Returns:
        Path to the OpenVINO model
    """
    from ultralytics import YOLO
    
    model_dir = Path(tempfile.gettempdir()) / "openvino_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    
    ov_model_path = model_dir / f"{model_name}_openvino_model" / f"{model_name}.xml"
    
    if not ov_model_path.exists():
        # Download and export to OpenVINO format
        pt_model = YOLO(f"{model_name}.pt")
        pt_model.export(format="openvino", dynamic=True, half=False)
        
        # Move exported model to our model directory
        exported_path = Path(f"{model_name}_openvino_model")
        if exported_path.exists():
            import shutil
            target_dir = model_dir / f"{model_name}_openvino_model"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(exported_path), str(target_dir))
    
    return ov_model_path


def _get_model(model_name: str = "yolo11n", device: str = "AUTO"):
    """
    Get or create an OpenVINO compiled model.
    
    Args:
        model_name: Name of the YOLO model
        device: OpenVINO device (AUTO, CPU, GPU, etc.)
    
    Returns:
        Compiled OpenVINO model
    """
    import openvino as ov
    
    cache_key = f"{model_name}_{device}"
    
    if cache_key not in _model_cache:
        model_path = _ensure_model_downloaded(model_name)
        core = ov.Core()
        model = core.read_model(model_path)
        compiled_model = core.compile_model(model, device)
        _model_cache[cache_key] = compiled_model
    
    return _model_cache[cache_key]


def _preprocess_image(image: np.ndarray, target_size: int = 640) -> tuple:
    """
    Preprocess image for YOLO inference.
    
    Args:
        image: Input image (BGR format from cv2)
        target_size: Target size for the model
    
    Returns:
        Tuple of (preprocessed_image, original_shape, scale_factors)
    """
    original_h, original_w = image.shape[:2]
    
    # Calculate scale to fit in target_size while maintaining aspect ratio
    scale = min(target_size / original_h, target_size / original_w)
    new_h, new_w = int(original_h * scale), int(original_w * scale)
    
    # Resize image
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    # Create padded image
    padded = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
    pad_h = (target_size - new_h) // 2
    pad_w = (target_size - new_w) // 2
    padded[pad_h:pad_h + new_h, pad_w:pad_w + new_w] = resized
    
    # Convert to float and normalize
    input_tensor = padded.astype(np.float32) / 255.0
    input_tensor = input_tensor.transpose(2, 0, 1)  # HWC -> CHW
    input_tensor = np.expand_dims(input_tensor, 0)  # Add batch dimension
    
    return input_tensor, (original_h, original_w), (scale, pad_h, pad_w)


def _postprocess_detections(
    output: np.ndarray,
    original_shape: tuple,
    preprocessing_info: tuple,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45
) -> List[Dict[str, Any]]:
    """
    Post-process YOLO detection output.
    
    Args:
        output: Raw model output
        original_shape: Original image shape (h, w)
        preprocessing_info: Tuple of (scale, pad_h, pad_w)
        conf_threshold: Confidence threshold
        iou_threshold: IoU threshold for NMS
    
    Returns:
        List of detection dictionaries
    """
    scale, pad_h, pad_w = preprocessing_info
    original_h, original_w = original_shape
    
    # Output shape: [1, 84, num_boxes] for detection (80 classes + 4 box coords)
    predictions = output[0].T  # Transpose to [num_boxes, 84]
    
    # Extract box coordinates and class scores
    boxes = predictions[:, :4]  # x_center, y_center, width, height
    scores = predictions[:, 4:]  # Class scores
    
    # Get max score and class for each box
    max_scores = np.max(scores, axis=1)
    class_ids = np.argmax(scores, axis=1)
    
    # Filter by confidence
    mask = max_scores >= conf_threshold
    boxes = boxes[mask]
    max_scores = max_scores[mask]
    class_ids = class_ids[mask]
    
    if len(boxes) == 0:
        return []
    
    # Convert from center format to corner format
    x_center, y_center, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    x1 = x_center - w / 2
    y1 = y_center - h / 2
    x2 = x_center + w / 2
    y2 = y_center + h / 2
    
    # Scale back to original image coordinates
    x1 = (x1 - pad_w) / scale
    y1 = (y1 - pad_h) / scale
    x2 = (x2 - pad_w) / scale
    y2 = (y2 - pad_h) / scale
    
    # Clip to image bounds
    x1 = np.clip(x1, 0, original_w)
    y1 = np.clip(y1, 0, original_h)
    x2 = np.clip(x2, 0, original_w)
    y2 = np.clip(y2, 0, original_h)
    
    # Apply NMS
    boxes_for_nms = np.stack([x1, y1, x2, y2], axis=1)
    indices = cv2.dnn.NMSBoxes(
        boxes_for_nms.tolist(),
        max_scores.tolist(),
        conf_threshold,
        iou_threshold
    )
    
    if len(indices) == 0:
        return []
    
    # Flatten indices if needed (OpenCV version dependent)
    if isinstance(indices, np.ndarray):
        indices = indices.flatten()
    
    # Build detection results
    detections = []
    for idx in indices:
        class_id = int(class_ids[idx])
        class_name = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else f"class_{class_id}"
        
        detections.append({
            "class_id": class_id,
            "class_name": class_name,
            "confidence": float(max_scores[idx]),
            "bbox": {
                "x1": float(x1[idx]),
                "y1": float(y1[idx]),
                "x2": float(x2[idx]),
                "y2": float(y2[idx]),
                "width": float(x2[idx] - x1[idx]),
                "height": float(y2[idx] - y1[idx])
            }
        })
    
    return detections


def _draw_detections(image: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
    """
    Draw detection boxes and labels on image.
    
    Args:
        image: Input image (BGR format)
        detections: List of detection dictionaries
    
    Returns:
        Image with drawn detections
    """
    output = image.copy()
    
    for det in detections:
        bbox = det["bbox"]
        x1, y1, x2, y2 = int(bbox["x1"]), int(bbox["y1"]), int(bbox["x2"]), int(bbox["y2"])
        color = get_color(det["class_id"])
        
        # Draw bounding box
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        
        # Prepare label
        label = f"{det['class_name']}: {det['confidence']:.2f}"
        
        # Calculate text size for background
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        )
        
        # Draw label background
        cv2.rectangle(
            output,
            (x1, y1 - text_height - baseline - 5),
            (x1 + text_width, y1),
            color,
            -1
        )
        
        # Draw label text
        cv2.putText(
            output,
            label,
            (x1, y1 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )
    
    return output


def _image_to_base64(image: np.ndarray) -> str:
    """Convert numpy image to base64 string."""
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode('utf-8')


def _load_image(image_path: str) -> np.ndarray:
    """Load image from file path."""
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image from: {image_path}")
    return image


@mcp.tool
def detect_objects(
    image_path: str,
    model_name: str = "yolo11n",
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    device: str = "AUTO",
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform object detection on an image using YOLOv11 optimized with OpenVINO.
    
    This tool uses Intel OpenVINO for optimized inference, providing fast and efficient
    object detection on various Intel hardware (CPU, GPU, VPU, etc.).
    
    **Supported Models:**
    - yolo11n (nano - fastest, least accurate)
    - yolo11s (small)
    - yolo11m (medium)
    - yolo11l (large)
    - yolo11x (extra large - slowest, most accurate)
    
    **Detection Output:**
    Each detection includes:
    - class_id: Numeric class identifier (COCO dataset)
    - class_name: Human-readable class name
    - confidence: Detection confidence score (0-1)
    - bbox: Bounding box coordinates (x1, y1, x2, y2, width, height)
    
    **Overlay Output:**
    An annotated image with detection boxes and labels is returned as base64-encoded PNG.
    Optionally, the overlay can be saved to a specified file path.
    
    Args:
        image_path: Path to the input image file (supports jpg, png, bmp, etc.)
        model_name: YOLO model variant to use (default: 'yolo11n')
        confidence_threshold: Minimum confidence for detections (0-1, default: 0.25)
        iou_threshold: IoU threshold for non-max suppression (0-1, default: 0.45)
        device: OpenVINO device to use ('AUTO', 'CPU', 'GPU', etc., default: 'AUTO')
        output_path: Optional path to save the overlay image
    
    Returns:
        Dictionary containing:
        - results:
            - detections: List of detected objects with class, confidence, and bbox
            - detection_count: Total number of objects detected
            - image_size: Original image dimensions
            - overlay_base64: Base64-encoded PNG of image with drawn detections
            - output_path: Path where overlay was saved (if output_path was provided)
        - meta_data:
            - model_name: Model used for detection
            - device: OpenVINO device used
            - inference_time_ms: Time taken for inference
            - is_error: Whether an error occurred
    """
    start_time = time.perf_counter()
    meta_data: Dict[str, Any] = {
        "model_name": model_name,
        "device": device,
        "is_error": False
    }
    
    try:
        # Load and validate image
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        image = _load_image(image_path)
        original_h, original_w = image.shape[:2]
        
        # Get model
        model = _get_model(model_name, device)
        
        # Preprocess
        input_tensor, original_shape, preprocessing_info = _preprocess_image(image)
        
        # Run inference
        inference_start = time.perf_counter()
        output = model(input_tensor)[0]
        inference_time = (time.perf_counter() - inference_start) * 1000
        meta_data["inference_time_ms"] = round(inference_time, 2)
        
        # Handle output format (may be tensor or numpy array)
        if hasattr(output, 'data'):
            output = output.data
        output = np.array(output)
        
        # Postprocess
        detections = _postprocess_detections(
            output,
            original_shape,
            preprocessing_info,
            confidence_threshold,
            iou_threshold
        )
        
        # Draw overlay
        overlay = _draw_detections(image, detections)
        overlay_base64 = _image_to_base64(overlay)
        
        # Save output if path provided
        saved_path = None
        if output_path:
            cv2.imwrite(output_path, overlay)
            saved_path = output_path
        
        results = {
            "detections": detections,
            "detection_count": len(detections),
            "image_size": {
                "width": original_w,
                "height": original_h
            },
            "overlay_base64": overlay_base64
        }
        
        if saved_path:
            results["output_path"] = saved_path
        
        meta_data["elapsed_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return {
            "results": results,
            "meta_data": meta_data
        }
    
    except Exception as e:
        meta_data["is_error"] = True
        meta_data["error_type"] = type(e).__name__
        meta_data["elapsed_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return {
            "results": {
                "error": str(e)
            },
            "meta_data": meta_data
        }


@mcp.tool
def detect_objects_base64(
    image_base64: str,
    model_name: str = "yolo11n",
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    device: str = "AUTO"
) -> Dict[str, Any]:
    """
    Perform object detection on a base64-encoded image using YOLOv11 optimized with OpenVINO.
    
    This tool accepts images as base64-encoded strings, making it suitable for API integrations
    where file paths may not be available. Uses Intel OpenVINO for optimized inference.
    
    **Input Format:**
    - Base64-encoded image data (JPEG, PNG, etc.)
    - Can include or exclude the data URI prefix (e.g., 'data:image/png;base64,')
    
    **Supported Models:**
    - yolo11n (nano - fastest)
    - yolo11s (small)
    - yolo11m (medium)
    - yolo11l (large)
    - yolo11x (extra large - most accurate)
    
    **Detection Output:**
    Each detection includes class_id, class_name, confidence, and bounding box coordinates.
    
    Args:
        image_base64: Base64-encoded image string
        model_name: YOLO model variant to use (default: 'yolo11n')
        confidence_threshold: Minimum confidence for detections (0-1, default: 0.25)
        iou_threshold: IoU threshold for non-max suppression (0-1, default: 0.45)
        device: OpenVINO device to use ('AUTO', 'CPU', 'GPU', etc., default: 'AUTO')
    
    Returns:
        Dictionary containing:
        - results:
            - detections: List of detected objects
            - detection_count: Total number of objects
            - image_size: Image dimensions
            - overlay_base64: Base64-encoded overlay image
        - meta_data: Model info, timing, error status
    """
    start_time = time.perf_counter()
    meta_data: Dict[str, Any] = {
        "model_name": model_name,
        "device": device,
        "is_error": False
    }
    
    try:
        # Remove data URI prefix if present
        if ',' in image_base64:
            image_base64 = image_base64.split(',', 1)[1]
        
        # Decode base64 to image
        image_bytes = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("Could not decode base64 image data")
        
        original_h, original_w = image.shape[:2]
        
        # Get model
        model = _get_model(model_name, device)
        
        # Preprocess
        input_tensor, original_shape, preprocessing_info = _preprocess_image(image)
        
        # Run inference
        inference_start = time.perf_counter()
        output = model(input_tensor)[0]
        inference_time = (time.perf_counter() - inference_start) * 1000
        meta_data["inference_time_ms"] = round(inference_time, 2)
        
        # Handle output format
        if hasattr(output, 'data'):
            output = output.data
        output = np.array(output)
        
        # Postprocess
        detections = _postprocess_detections(
            output,
            original_shape,
            preprocessing_info,
            confidence_threshold,
            iou_threshold
        )
        
        # Draw overlay
        overlay = _draw_detections(image, detections)
        overlay_base64 = _image_to_base64(overlay)
        
        results = {
            "detections": detections,
            "detection_count": len(detections),
            "image_size": {
                "width": original_w,
                "height": original_h
            },
            "overlay_base64": overlay_base64
        }
        
        meta_data["elapsed_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return {
            "results": results,
            "meta_data": meta_data
        }
    
    except Exception as e:
        meta_data["is_error"] = True
        meta_data["error_type"] = type(e).__name__
        meta_data["elapsed_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return {
            "results": {
                "error": str(e)
            },
            "meta_data": meta_data
        }


@mcp.tool
def list_available_models() -> Dict[str, Any]:
    """
    List all available YOLO models and their characteristics.
    
    This tool returns information about the available YOLOv11 model variants
    that can be used with the detect_objects tools.
    
    Returns:
        Dictionary containing:
        - results:
            - models: List of available models with their descriptions
            - recommended: Recommended model for general use
    """
    models = [
        {
            "name": "yolo11n",
            "description": "YOLOv11 Nano - Fastest model, suitable for real-time applications",
            "parameters": "~2.6M",
            "speed": "Fastest",
            "accuracy": "Good"
        },
        {
            "name": "yolo11s",
            "description": "YOLOv11 Small - Good balance of speed and accuracy",
            "parameters": "~9.4M",
            "speed": "Fast",
            "accuracy": "Better"
        },
        {
            "name": "yolo11m",
            "description": "YOLOv11 Medium - Higher accuracy, moderate speed",
            "parameters": "~20.1M",
            "speed": "Moderate",
            "accuracy": "High"
        },
        {
            "name": "yolo11l",
            "description": "YOLOv11 Large - High accuracy for demanding applications",
            "parameters": "~25.3M",
            "speed": "Slower",
            "accuracy": "Very High"
        },
        {
            "name": "yolo11x",
            "description": "YOLOv11 Extra Large - Maximum accuracy, slowest speed",
            "parameters": "~56.9M",
            "speed": "Slowest",
            "accuracy": "Highest"
        }
    ]
    
    return {
        "results": {
            "models": models,
            "recommended": "yolo11n",
            "note": "Models are automatically downloaded on first use"
        }
    }


@mcp.tool
def get_class_labels() -> Dict[str, Any]:
    """
    Get the list of object classes that can be detected.
    
    This tool returns the complete list of COCO dataset class labels
    that the YOLO models are trained to detect.
    
    Returns:
        Dictionary containing:
        - results:
            - classes: List of class names with their IDs
            - total_classes: Number of classes
    """
    classes = [
        {"id": i, "name": name} for i, name in enumerate(COCO_CLASSES)
    ]
    
    return {
        "results": {
            "classes": classes,
            "total_classes": len(COCO_CLASSES)
        }
    }


# Resource to provide server information
@mcp.resource("detection://info")
def detection_info() -> str:
    """Provides general information about the object detection server"""
    import json
    from datetime import datetime
    info = {
        "server_name": "OpenVINO Object Detection",
        "type": "YOLOv11 with OpenVINO optimization",
        "models_available": ["yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x"],
        "total_classes": len(COCO_CLASSES),
        "last_updated": datetime.now().isoformat(),
        "description": "Object detection server using Intel OpenVINO for optimized inference"
    }
    return json.dumps(info, indent=2)


# Entry point
if __name__ == "__main__":
    print("Starting OpenVINO Object Detection MCP Server...")
    print("Available transports:")
    print("  - HTTP (default): python main.py")
    print("  - STDIO: python main.py --stdio")
    print("  - SSE: python main.py --sse")

    parser = argparse.ArgumentParser(description="Start OpenVINO Object Detection MCP Server")
    parser.add_argument(
        "--stdio", action="store_true", help="Use STDIO transport"
    )
    parser.add_argument(
        "--sse", action="store_true", help="Use SSE transport"
    )
    parser.add_argument(
        "--port", type=int, default=8006, help="Port for HTTP/SSE server (default: 8006)"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host for HTTP/SSE server (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    if args.stdio:
        print("\n🚀 Starting STDIO server...")
        mcp.run()  # Default STDIO transport
    elif args.sse:
        print(f"\n🚀 Starting SSE server on http://{args.host}:{args.port}/sse")
        mcp.run(
            transport="sse",
            host=args.host,
            port=args.port,
        )
    else:
        print(f"\n🚀 Starting HTTP server on http://{args.host}:{args.port}/mcp")
        mcp.run(
            transport="http",
            host=args.host,
            port=args.port,
            path="/mcp"
        )
