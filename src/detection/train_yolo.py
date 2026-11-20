"""
train_yolo — YOLOv11 training + ONNX export script

Run in the user-side training environment (requires ultralytics + torch + onnx).
The generated dataset format is compatible with synthetic_data_generator.py in this directory.

Usage:
  # Basic training (using synthetic data or data collected from Delphi)
  python -c "
  from src.detection.train_yolo import train
  train(
      data_yaml='./yolo_dataset/dataset.yaml',
      model_size='n',          # n/s/m/l/x
      epochs=100,
      imgsz=640,
      project='./yolo_output',
  )
  "

  # One-line command (run the module directly)
  python -m src.detection.train_yolo --data ./yolo_dataset/dataset.yaml --epochs 100

Output:
  yolo_output/train/weights/best.pt     ← PyTorch weights
  yolo_output/train/weights/best.onnx   ← ONNX model (can be loaded directly by YOLOONNXDetector)
  yolo_output/train/results.csv         ← Training metrics
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _check_deps() -> None:
    """Check whether the training dependencies are installed."""
    missing = []
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        missing.append("ultralytics")
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    if missing:
        print(
            f"Missing training dependencies: {', '.join(missing)}\n"
            "Please install: pip install ultralytics torch torchvision onnx\n"
            "or run in an environment with a GPU."
        )
        sys.exit(1)


def train(
    data_yaml: str,
    model_size: str = "n",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    project: str = "./yolo_output",
    name: str = "train",
    device: str = "",
    resume: bool = False,
    pretrained: bool = True,
    export_onnx: bool = True,
) -> str:
    """Perform YOLOv11 training and export ONNX.

    Args:
        data_yaml: Path to dataset.yaml.
        model_size: YOLO model size (n/s/m/l/x).
        epochs: Number of training epochs.
        imgsz: Input image size (pixels).
        batch: Batch size.
        project: Output project directory.
        name: Experiment name.
        device: Device (''=auto, 'cpu', '0', '0,1').
        resume: Whether to resume training from a checkpoint.
        pretrained: Whether to use COCO pretrained weights (strongly recommended True).
        export_onnx: Whether to export ONNX after training completes.

    Returns:
        ONNX model file path (if export_onnx=True).
    """
    _check_deps()

    from ultralytics import YOLO

    # 1. Load the pretrained model (YOLO will automatically download .pt)
    model_name = f"yolo11{model_size}.pt" if pretrained else f"yolo11{model_size}.yaml"
    model = YOLO(model_name)

    logger.info("Starting training: model=%s, data=%s, epochs=%d, imgsz=%d",
                 model_name, data_yaml, epochs, imgsz)

    # 2. Train
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        device=device,
        resume=resume,
        pretrained=pretrained,
        # Augmentations specific to UI screenshots (keep text clear)
        hsv_h=0.015,          # Very small hue variation (prevent text from changing color)
        hsv_s=0.2,            # Moderate saturation variation
        hsv_v=0.2,            # Moderate value/brightness variation
        translate=0.1,        # Translation
        scale=0.2,            # Scaling
        fliplr=0.5,           # Horizontal flip
        mosaic=0.5,           # Mosaic augmentation
        mixup=0.1,            # Mixup augmentation
    )

    # 3. Export ONNX
    best_pt = Path(project) / name / "weights" / "best.pt"
    onnx_path = Path(project) / name / "weights" / "best.onnx"

    if export_onnx:
        logger.info("Exporting ONNX: %s → %s", best_pt, onnx_path)
        model.export(
            format="onnx",
            imgsz=imgsz,
            half=False,        # FP32 to ensure compatibility
            simplify=True,     # ONNX simplification
            nms=True,          # Embedded NMS (no Python-side NMS needed during inference)
        )

        if onnx_path.exists():
            logger.info("ONNX export successful: %s (size: %.1f MB)",
                         onnx_path, onnx_path.stat().st_size / 1e6)
        return str(onnx_path)

    return str(best_pt)


def train_from_delphi(
    app_path: str,
    output_dir: str = "./yolo_dataset",
    forms: Optional[list[str]] = None,
    epochs: int = 100,
    model_size: str = "n",
) -> str:
    """Complete in one step: collect data from a Delphi application → train → export ONNX.

    Prerequisites:
      - The Delphi exe is linked with DaofyAutomation
      - ultralytics + torch are installed

    Args:
        app_path: Path to the Delphi exe.
        output_dir: Dataset and output directory.
        forms: List of forms to collect.
        epochs: Number of training epochs.
        model_size: YOLO model size.

    Returns:
        ONNX model path.
    """
    # 1. Collect data
    from .synthetic_data_generator import DelphiDataCollector

    collector = DelphiDataCollector(
        app_path=app_path,
        output_dir=output_dir,
        forms=forms,
    )
    stats = collector.collect_all()
    logger.info("Data collection complete: %s", stats)

    if stats["total_images"] == 0:
        raise RuntimeError("No training data was collected. Please check whether the Delphi application is integrated with DaofyAutomation.")

    # 2. Train
    data_yaml = str(Path(output_dir) / "dataset.yaml")
    onnx_path = train(
        data_yaml=data_yaml,
        epochs=epochs,
        model_size=model_size,
        project=output_dir,
    )

    return onnx_path


def generate_synthetic_and_train(
    num_samples: int = 200,
    output_dir: str = "./yolo_synthetic",
    epochs: int = 50,
    model_size: str = "n",
) -> str:
    """Complete in one step: generate synthetic data → train → export ONNX.

    Used to quickly validate the training pipeline without a Delphi environment.

    Args:
        num_samples: Number of synthetic screenshots.
        output_dir: Output directory.
        epochs: Number of training epochs.
        model_size: YOLO model size.

    Returns:
        ONNX model path.
    """
    from .synthetic_data_generator import SyntheticDataGenerator

    # 1. Generate synthetic data
    gen = SyntheticDataGenerator(output_dir=output_dir)
    stats = gen.generate(num_samples=num_samples)
    logger.info("Synthetic data generation complete: %s", stats)

    # 2. Train
    data_yaml = str(Path(output_dir) / "dataset.yaml")
    onnx_path = train(
        data_yaml=data_yaml,
        epochs=epochs,
        model_size=model_size,
        project=output_dir,
    )

    return onnx_path


def evaluate(
    model_path: str,
    test_images_dir: str,
    test_labels_dir: str,
) -> dict:
    """Evaluate the accuracy of an ONNX or PyTorch model on a test set.

    Args:
        model_path: .onnx or .pt file.
        test_images_dir: Test image directory.
        test_labels_dir: Directory of YOLO-format labels.

    Returns:
        {"map50": ..., "map50_95": ..., "precision": ..., "recall": ...}
    """
    if model_path.endswith(".onnx"):
        # Use YOLOONNXDetector for inference evaluation
        from .yolo_onnx import YOLOONNXDetector
        from .opencv_detector import Detection

        detector = YOLOONNXDetector(model_path)
    else:
        # Evaluate with ultralytics
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("Evaluating a PyTorch model requires ultralytics")

        model = YOLO(model_path)
        results = model.val(data=str(Path(test_images_dir).parent / "dataset.yaml"))
        metrics = {
            "map50": results.box.map50,
            "map50_95": results.box.map,
            "precision": results.box.p[0],
            "recall": results.box.r[0],
        }
        return metrics

    # ONNX evaluation (run inference on each image)
    import glob
    image_files = glob.glob(os.path.join(test_images_dir, "*.png")) + \
                  glob.glob(os.path.join(test_images_dir, "*.jpg"))

    total_gt = 0
    total_tp = 0
    total_fp = 0

    for img_path in image_files:
        img_name = Path(img_path).stem
        label_path = os.path.join(test_labels_dir, f"{img_name}.txt")

        if not os.path.exists(label_path):
            continue

        # Read GT labels
        with open(label_path) as f:
            gt_boxes = []
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    gt_boxes.append({
                        "class_id": int(parts[0]),
                        "x": float(parts[1]),
                        "y": float(parts[2]),
                        "w": float(parts[3]),
                        "h": float(parts[4]),
                    })

        total_gt += len(gt_boxes)

        # Inference
        detections = detector.detect(img_path)

        # Simple matching
        tp = 0
        fp = 0
        matched = set()
        for det in detections:
            found = False
            for i, gt in enumerate(gt_boxes):
                if i in matched:
                    continue
                if det.class_id == gt["class_id"]:
                    # Check IoU (simplified to existence of a positive sample)
                    found = True
                    matched.add(i)
                    break
            if found:
                tp += 1
            else:
                fp += 1

        total_tp += tp
        total_fp += fp

    precision = total_tp / max(total_tp + total_fp, 1)
    recall = total_tp / max(total_gt, 1)

    return {
        "precision": precision,
        "recall": recall,
        "total_gt": total_gt,
        "total_tp": total_tp,
        "total_fp": total_fp,
    }


# ============================================================
# CLI entry point
# ============================================================

def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="YOLOv11 training + ONNX export")
    parser.add_argument("--data", default="./yolo_dataset/dataset.yaml",
                        help="Path to dataset.yaml")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--model", default="n", choices=["n", "s", "m", "l", "x"],
                        help="YOLO model size")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--project", default="./yolo_output", help="Output directory")
    parser.add_argument("--name", default="train", help="Experiment name")
    parser.add_argument("--device", default="", help="Device (''=auto, 'cpu', '0')")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--no-pretrained", action="store_true",
                        help="Do not use COCO pretrained weights")
    parser.add_argument("--no-onnx", action="store_true",
                        help="Do not export ONNX")
    parser.add_argument("--synthetic", type=int, default=0,
                        help="Generate N synthetic samples and train (no Delphi environment required)")

    args = parser.parse_args()

    if args.synthetic > 0:
        print(f"Generating {args.synthetic} synthetic samples and training...")
        onnx_path = generate_synthetic_and_train(
            num_samples=args.synthetic,
            output_dir=args.project,
            epochs=args.epochs,
            model_size=args.model,
        )
    else:
        onnx_path = train(
            data_yaml=args.data,
            model_size=args.model,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            project=args.project,
            name=args.name,
            device=args.device,
            resume=args.resume,
            pretrained=not args.no_pretrained,
            export_onnx=not args.no_onnx,
        )

    print(f"\n✅ Training complete")
    print(f"   ONNX model: {onnx_path}")
    print(f"   Copy it into the project and it can be loaded by YOLOONNXDetector")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

