#!/usr/bin/env python3
"""Convert YOLO models to OpenVINO format for optimized inference."""

from ultralytics import YOLO


def convert_model(model_name: str) -> None:
    """Convert a single YOLO model to OpenVINO format.

    Args:
        model_name: Name of the YOLO model (without .pt extension)
    """
    print(f"Converting {model_name} to OpenVINO format...")
    model = YOLO(f"{model_name}.pt")
    model.export(format="openvino", dynamic=True, half=False)
    print(f"Conversion complete: {model_name}_openvino_model/")


if __name__ == "__main__":
    models = ["yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x"]
    for model_name in models:
        convert_model(model_name)
