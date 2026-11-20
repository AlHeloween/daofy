# Download the YOLOv11n ONNX Model

The current environment cannot download it directly. Run the following steps on your development machine:

## Option 1: Direct download (recommended)

1. Open the link and download: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx
2. Put the downloaded `yolo11n.onnx` (about 11MB) into the project's `models/` directory

## Option 2: Download from the command line

```bash
curl -L -o models/yolo11n.onnx https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx
```

## Verification

After downloading, run the following command to verify the model loads:

```bash
python -c "
from src.detection.yolo_onnx import YOLOONNXDetector
yolo = YOLOONNXDetector('models/yolo11n.onnx')
print('✅ Model loaded successfully')
"
```
