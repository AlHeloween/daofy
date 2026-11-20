r"""
PP-OCRv6 OCR service — pure ONNX Runtime implementation, zero PaddlePaddle dependency.

Architecture:
  OcrService (singleton)
   ├─ _detect_backend() → auto-select inference backend
   ├─ _ensure_models()  → auto-download models on first use → data/ocr-models/
   ├─ detect(image)     → DBNet detection → [{box: [[x1,y1],...], score}]
   ├─ classify(crop)    → [optional] orientation classification → 0°/180°
   ├─ recognize(crop)   → SVTR recognition → {text, confidence}
   └─ recognize(image)  → full pipeline: detect → classify → recognize → [{text, conf, box}]

Model files (auto-downloaded to data/ocr-models/ on first use):
  det/model.onnx    — PP-OCRv6_medium text detection (DBNet)
  rec/model.onnx    — PP-OCRv6_medium text recognition (SVTR)
  cls/model.onnx    — ch_ppocr_mobile_v2.0 orientation classification [optional]
  ppocr_keys_v1.txt — character dictionary
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from ..constants import (
    CHUNK_SIZE_DOWNLOAD,
    OCR_MAX_LONG_EDGE,
    OCR_MAX_SHORT_EDGE,
    TIMEOUT_NETWORK_DOWNLOAD,
    TIMEOUT_NETWORK_DOWNLOAD_LARGE,
)

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

# Data root directory for this service (relative to the project root)
_DATA_DIR = Path("data") / "ocr-models"

# Model download sources (HuggingFace direct links)
_MODEL_URLS: dict[str, str] = {
    "det": "https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_onnx/resolve/main/model.onnx",
    "rec": "https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec_onnx/resolve/main/model.onnx",
    "cls": "https://huggingface.co/PaddlePaddle/ch_ppocr_mobile_v2.0_cls_onnx/resolve/main/inference.onnx",
}

# HuggingFace China mirror (hf-mirror.com, faster for users in China)
_MODEL_MIRROR_URLS: dict[str, str] = {
    k: v.replace("huggingface.co", "hf-mirror.com")
    for k, v in _MODEL_URLS.items()
}

# ModelScope China mirror sources (file name inference.onnx, not HuggingFace's model.onnx)
_MODEL_MODELSCOPE_URLS: dict[str, str] = {
    "det": "https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_det_onnx/resolve/master/inference.onnx",
    "rec": "https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_rec_onnx/resolve/master/inference.onnx",
}

# Fallback sources (Baidu PaddleX tar packages, directly reachable in China)
_MODEL_TAR_URLS: dict[str, str] = {
    "det": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/tmp/PP-OCRv6_medium_det_onnx.tar",
    "rec": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/tmp/PP-OCRv6_medium_rec_onnx.tar",
}

# Character dictionary (GitHub direct link + China proxy mirror)
_DICT_URL = (
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/ppocr_keys_v1.txt"
)
_DICT_MIRROR_URL = (
    "https://raw.staticdn.net/PaddlePaddle/PaddleOCR/main/ppocr/utils/ppocr_keys_v1.txt"
)

# DBNet post-processing parameters
_DET_DB_THRESH = 0.3       # binarization threshold
_DET_DB_BOX_THRESH = 0.5   # text box confidence threshold
_DET_DB_UNCLIP_RATIO = 1.5  # text box expansion ratio
_DET_MIN_AREA = 3.0         # minimum text box area

# Recognition parameters
_REC_IMAGE_HEIGHT = 48       # recognition model input height
_REC_BATCH_SIZE = 6          # recognition batch size

# Classification parameters
_CLS_IMAGE_HEIGHT = 48
_CLS_IMAGE_WIDTH = 192
_CLS_THRESH = 0.9


# ============================================================
# Utility functions
# ============================================================

def _project_root() -> Path:
    """Return the project root directory (parent of src/)."""
    return Path(__file__).resolve().parent.parent.parent


def _models_dir() -> Path:
    """Return the model cache directory, creating it if it does not exist."""
    d = _project_root() / _DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_path(model_type: str) -> Path:
    """Return the path of a model file."""
    return _models_dir() / model_type / "model.onnx"


def _cls_model_path() -> Path:
    """Return the path of the classification model file."""
    return _models_dir() / "cls" / "inference.onnx"


def _dict_path() -> Path:
    """Return the path of the character dictionary file."""
    return _models_dir() / "ppocr_keys_v1.txt"


def _fastest_url(urls: list[str], timeout: int = 5) -> list[str]:
    """Benchmark multiple URLs and return them in ascending response time (fastest first).

    Response time is measured by requesting the first 64KB of data from each URL.
    Returns an empty list if none of the URLs are reachable.

    Args:
        urls: list of URLs to benchmark
        timeout: timeout in seconds for each URL

    Returns:
        list of URLs sorted by speed (fastest first)
    """
    import time
    import requests

    results: list[tuple[float, str]] = []
    for url in urls:
        try:
            start = time.time()
            r = requests.get(url, stream=True, timeout=timeout)
            r.raise_for_status()
            # Read only the first chunk to measure initial transfer speed
            for _ in r.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                break
            elapsed = time.time() - start
            results.append((elapsed, url))
        except Exception:
            continue

    results.sort(key=lambda x: x[0])
    return [url for _, url in results]


def _download_file(
    url: str, dest: Path, desc: str = "",
    fallback_urls: list[str] | None = None,
) -> bool:
    """Download a file to the given path, returning whether it succeeded.

    Args:
        url: download address
        dest: save path
        desc: description text (used for logging)
        fallback_urls: fallback download addresses (tried in order if the primary url fails)
    """
    import requests
    all_urls = [url] + (fallback_urls or [])
    for i, try_url in enumerate(all_urls):
        try:
            logger.info(f"Downloading {desc or 'file'} ({i+1}/{len(all_urls)}): {try_url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(try_url, stream=True, timeout=TIMEOUT_NETWORK_DOWNLOAD)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                    f.write(chunk)
            logger.info(f"Download complete: {dest}")
            return True
        except requests.exceptions.SSLError:
            logger.warning(f"SSL verification failed: {try_url}")
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(
                    try_url,
                    stream=True,
                    timeout=TIMEOUT_NETWORK_DOWNLOAD,
                    verify=False,
                )
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                        f.write(chunk)
                logger.info(f"Download complete (certificate verification disabled): {dest}")
                return True
            except Exception as e2:
                logger.warning(f"Download failed (certificate verification disabled) {try_url}: {e2}")
                continue
        except Exception as e:
            logger.warning(f"Download failed {try_url}: {e}")
            continue
    # All URLs failed
    return False


def _download_tar_and_extract(url: str, dest_dir: Path, desc: str = "") -> bool:
    """Download a tar package and extract it to dest_dir, returning whether it succeeded. dest_dir should contain the .onnx file."""
    import requests
    try:
        logger.info(f"Downloading {desc or 'tar package'}: {url}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tmp_path = tmp.name
            try:
                r = requests.get(url, stream=True, timeout=TIMEOUT_NETWORK_DOWNLOAD_LARGE)
                r.raise_for_status()
            except requests.exceptions.SSLError:
                logger.warning(f"SSL verification failed, retrying without certificate verification: {url}")
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(
                    url,
                    stream=True,
                    timeout=TIMEOUT_NETWORK_DOWNLOAD_LARGE,
                    verify=False,
                )
                r.raise_for_status()
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                tmp.write(chunk)
        # Extract
        with tarfile.open(tmp_path, "r") as tar:
            tar.extractall(path=dest_dir)
        # Find the .onnx file and rename it to model.onnx
        onnx_files = list(dest_dir.rglob("*.onnx"))
        if onnx_files:
            # If there are multiple, take the first one
            src = onnx_files[0]
            dst = dest_dir / "model.onnx"
            if src != dst:
                shutil.move(str(src), str(dst))
            logger.info(f"Extraction complete: {dest_dir}")
            os.unlink(tmp_path)
            return True
        else:
            logger.warning(f"No .onnx file found in the tar package: {dest_dir}")
            os.unlink(tmp_path)
            return False
    except Exception as e:
        logger.warning(f"Download/extraction failed {url}: {e}")
        return False


def _load_character_dict_from_yml(yml_path: Path) -> list[str] | None:
    """Parse the character dictionary from the rec model's inference.yml.

    The PostProcess.character_dict field of PP-OCRv6's inference.yml
    contains the complete character set used during model training (18714 classes).

    Args:
        yml_path: path to the inference.yml file

    Returns:
        list of characters (the last one is blank), or None if parsing fails
    """
    if not yml_path.exists():
        return None
    try:
        chars: list[str] = []
        in_dict = False
        with open(yml_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("  character_dict:"):
                    in_dict = True
                    continue
                if in_dict:
                    stripped = line.lstrip()
                    if stripped.startswith("- "):
                        # Extract the character inside the quotes: - '!' → !
                        val = stripped[2:].strip()
                        if val.startswith("'") and val.endswith("'"):
                            # Escaping '' → ' inside YAML single-quoted strings
                            inner = val[1:-1]
                            inner = inner.replace("''", "'")
                            val = inner
                        elif val.startswith('"') and val.endswith('"'):
                            val = val[1:-1]
                        chars.append(val)
                    else:
                        # Stop parsing when a non-list line is encountered
                        break
        if not chars:
            return None
        return chars
    except Exception:
        return None


def _load_character_dict(path: Path) -> list[str]:
    """Load the character dictionary and return a list of characters (excluding blank).

    Prefers loading from the rec model's inference.yml (contains the full PP-OCRv6
    character set of 18712 characters), falls back to ppocr_keys_v1.txt, and finally
    uses a minimal fallback dictionary.

    blank is handled by the blank_indices parameter of _ctc_decode and is not added
    to the character list.
    """
    # Preferred: load from the rec model's inference.yml
    rec_yml = _models_dir() / "rec" / "PP-OCRv6_medium_rec_onnx" / "inference.yml"
    if rec_yml.exists():
        chars = _load_character_dict_from_yml(rec_yml)
        if chars and len(chars) > 1000:  # ensure it is the complete dictionary
            logger.info(f"Loaded character dictionary from inference.yml: {len(chars)} characters")
            # Download ppocr_keys_v1.txt as a cached by-product (does not affect recognition)
            _download_dict_if_needed()
            return chars

    # Second choice: load from ppocr_keys_v1.txt
    if path.exists():
        try:
            chars: list[str] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        chars.append(line)
            if chars:
                logger.info(f"Loaded character dictionary from ppocr_keys_v1.txt: {len(chars)} characters")
                return chars
        except Exception:
            pass

    # Minimal fallback dictionary
    chars = list("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    logger.warning(f"Using minimal fallback dictionary: {len(chars)} characters")
    return chars


def _download_dict_if_needed():
    """Download ppocr_keys_v1.txt (cache only; does not affect the recognition pipeline)."""
    dict_path = _dict_path()
    if not dict_path.exists():
        _download_file(_DICT_URL, dict_path, desc="character dictionary",
                       fallback_urls=[_DICT_MIRROR_URL])


def _detect_cpu_vendor() -> str:
    """Detect the CPU vendor."""
    import platform
    proc = platform.processor().lower()
    if "intel" in proc or "genuineintel" in proc:
        return "intel"
    if "amd" in proc:
        return "amd"
    # fallback: check environment variables or CPU features
    try:
        import cpuinfo  # type: ignore[import-untyped]
        brand = cpuinfo.get_cpu_info().get("brand_raw", "").lower()
        if "intel" in brand:
            return "intel"
        if "amd" in brand:
            return "amd"
    except ImportError:
        pass
    return "unknown"


def _check_openvino_available() -> bool:
    """Check whether the openvino package is available."""
    try:
        import openvino  # noqa: F401
        return True
    except ImportError:
        return False


def _select_optimal_backend() -> str:
    """Automatically select the optimal inference backend."""
    py_version = sys.version_info
    cpu = _detect_cpu_vendor()

    # Python >= 3.14: PaddlePaddle unavailable, use ONNX Runtime
    if py_version >= (3, 14):
        if cpu == "intel" and _check_openvino_available():
            return "openvino"
        return "onnxruntime"

    # Python 3.9-3.13: multiple backends available
    if cpu == "intel" and _check_openvino_available():
        return "openvino"

    return "onnxruntime"


# ============================================================
# DBNet post-processing
# ============================================================

def _db_post_process(
    pred_map: "np.ndarray",
    original_shape: tuple[int, int],
) -> list[dict[str, Any]]:
    """DBNet post-processing: threshold binarization → find contours → generate text boxes.

    Args:
        pred_map: probability map output by the model (H, W)
        original_shape: original image size (h, w)

    Returns:
        [{box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], score: float}, ...]
    """
    import cv2
    import numpy as np
    import pyclipper
    from shapely.geometry import Polygon

    h, w = original_shape
    pred_h, pred_w = pred_map.shape

    # Scale factors
    scale_h, scale_w = h / pred_h, w / pred_w

    # 1. Threshold binarization
    binary = (pred_map > _DET_DB_THRESH).astype(np.uint8) * 255

    # 2. Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        # cv2 contour format (N, 1, 2) → squeeze to (N, 2)
        contour = contour.squeeze(1) if contour.ndim == 3 else contour
        # Compute contour area
        area = cv2.contourArea(contour)
        if area < _DET_MIN_AREA:
            continue

        # ★ Compute text confidence on the original (unexpanded) contour, matching the original PaddleOCR behavior
        mask = np.zeros((pred_h, pred_w), dtype=np.uint8)
        cv2.fillPoly(mask, [contour.astype(np.int32)], 1)
        score = float(np.mean(pred_map[mask > 0]))
        if score < _DET_DB_BOX_THRESH:
            continue

        # Expand contour (unclip) — only to smooth the text box shape, not used for scoring
        distance = area * _DET_DB_UNCLIP_RATIO / cv2.arcLength(contour, True)
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(contour, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(distance)
        if not expanded:
            continue

        # Take the largest expanded contour (pyclipper returns a list of lists; convert to np.ndarray)
        expanded_np = [np.array(p, dtype=np.int32).reshape(-1, 2) for p in expanded]
        expanded = max(expanded_np, key=cv2.contourArea)

        # Fit the minimum area rectangle
        rect = cv2.minAreaRect(expanded)
        box = cv2.boxPoints(rect)  # (4, 2)

        # Scale to original image coordinates
        box[:, 0] = box[:, 0] * scale_w
        box[:, 1] = box[:, 1] * scale_h
        box = np.clip(box, 0, [w, h])

        # Sort the 4 points: top-left, top-right, bottom-right, bottom-left
        box = _order_points(box)

        boxes.append({
            "box": box.tolist(),
            "score": round(float(score), 4),
        })

    # Sort by (y + x) (top to bottom, left to right)
    boxes.sort(key=lambda b: b["box"][0][1] + b["box"][0][0] * 0.01)

    return boxes


def _order_points(pts: "np.ndarray") -> "np.ndarray":
    """Sort 4 points into [top-left, top-right, bottom-right, bottom-left]."""
    import numpy as np

    # Sort by x+y → the first is top-left, the last is bottom-right
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _get_rotate_crop_image(
    img: "np.ndarray", box: list[list[float]]
) -> "np.ndarray":
    """Crop and rectify the image according to the text box."""
    import cv2
    import numpy as np

    box = np.array(box, dtype=np.float32)
    # Compute width and height
    w = max(
        np.linalg.norm(box[1] - box[0]),
        np.linalg.norm(box[2] - box[3]),
    )
    h = max(
        np.linalg.norm(box[3] - box[0]),
        np.linalg.norm(box[2] - box[1]),
    )

    dst = np.array(
        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(box, dst)
    crop = cv2.warpPerspective(img, M, (int(w), int(h)))
    return crop


# ============================================================
# CTC decoding
# ============================================================

def _ctc_decode(
    preds: "np.ndarray",
    char_list: list[str],
    blank_indices: set[int] | None = None,
) -> tuple[str, float]:
    """CTC greedy decoding: argmax → deduplicate → remove blank → convert to characters.

    Model output layout:
      - Index 0 is always blank (CTC convention)
      - Indices 1..len(char_list) map to char_list[0..len-1]
      - PP-OCRv6 models additionally treat the last class as blank (dual-blank design)
        → num_classes = len(char_list) + 2
      - Older models have only one blank
        → num_classes = len(char_list) + 1

    Args:
        preds: (W, num_classes) probability distribution
        char_list: list of characters (real characters only, no blank)
        blank_indices: set of indices to ignore. When None, auto-detected:
                       - if num_classes == len(char_list) + 2 → {0, len(char_list)+1}
                       - if num_classes == len(char_list) + 1 → {0}

    Returns:
        (text, avg_confidence)
    """
    import numpy as np

    num_classes = preds.shape[1]
    if blank_indices is None:
        if num_classes == len(char_list) + 2:
            blank_indices = {0, len(char_list) + 1}
        else:
            blank_indices = {0}

    preds_idx = preds.argmax(axis=1)
    preds_prob = preds.max(axis=1)

    result = []
    conf_list = []
    prev = -1
    for i, idx in enumerate(preds_idx):
        if idx in blank_indices:
            prev = -1
            continue
        if idx == prev:
            continue
        char_idx = idx - 1
        if char_idx < 0 or char_idx >= len(char_list):
            prev = -1
            continue
        result.append(char_list[char_idx])
        conf_list.append(float(preds_prob[i]))
        prev = idx

    text = "".join(result)
    avg_conf = float(np.mean(conf_list)) if conf_list else 0.0
    return text, avg_conf


# ============================================================
# Inference preprocessing
# ============================================================

def _resize_normalize(
    img: "np.ndarray",
    target_h: int,
    target_w: int = -1,
) -> "np.ndarray":
    """resize + normalize to the model input format.

    Args:
        img: (H, W, 3) BGR
        target_h: target height
        target_w: target width; -1 means keep the aspect ratio

    Returns:
        (1, 3, target_h, target_w) or (1, 3, target_h, W')
    """
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    if target_w == -1:
        # Keep aspect ratio
        ratio = target_h / h
        new_w = int(w * ratio)
        resized = cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_LINEAR)
    else:
        resized = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    # BGR → RGB → CHW → normalize to [0,1]
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    rgb = rgb.astype(np.float32) / 255.0
    # HWC → CHW
    chw = np.transpose(rgb, (2, 0, 1))
    # Add batch dimension
    return np.expand_dims(chw, axis=0).astype(np.float32)


def _cls_preprocess(img: "np.ndarray") -> "np.ndarray":
    """Classification model preprocessing."""
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    ratio = _CLS_IMAGE_HEIGHT / h
    new_w = int(w * ratio)
    resized = cv2.resize(img, (new_w, _CLS_IMAGE_HEIGHT), interpolation=cv2.INTER_LINEAR)

    # If the width is insufficient, pad on the right
    if new_w < _CLS_IMAGE_WIDTH:
        padded = np.zeros((_CLS_IMAGE_HEIGHT, _CLS_IMAGE_WIDTH, 3), dtype=np.uint8)
        padded[:, :new_w, :] = resized
        resized = padded

    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    rgb = rgb.astype(np.float32) / 255.0
    chw = np.transpose(rgb, (2, 0, 1))
    # Mean/std normalization
    mean = np.array([0.485, 0.456, 0.406]).reshape(3, 1, 1)
    std = np.array([0.229, 0.224, 0.225]).reshape(3, 1, 1)
    chw = (chw - mean) / std
    return np.expand_dims(chw, axis=0).astype(np.float32)


# ============================================================
# OcrService
# ============================================================


class OcrService:
    """PP-OCRv6 OCR service (singleton, lazy model loading).

    Usage:
        svc = OcrService()
        results = svc.recognize("screenshot.png")
        # → [{"text": "你好", "confidence": 0.97, "box": [[x1,y1],...]}, ...]
    """

    _instance: Optional["OcrService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_size: str = "medium"):
        """Initialize the OCR service.

        Args:
            model_size: model size, tiny/small/medium, default medium
        """
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self._backend: str = _select_optimal_backend()
        self._model_size = model_size
        self._character_list: list[str] = []
        self._loaded = False
        self._load_error: Optional[str] = None

        # ONNX Runtime sessions (lazy loading)
        self._det_session: Any = None
        self._rec_session: Any = None
        self._cls_session: Any = None

        logger.info(
            f"OcrService initialized: backend={self._backend}, model_size={model_size}"
        )

    # ── Properties ──

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ── Public interface ──

    def recognize(self, image_path: str) -> list[dict[str, Any]]:
        """Full OCR pipeline: detection → classification → recognition.

        Args:
            image_path: image file path

        Returns:
            [{text, confidence, box}, ...]
        """
        import cv2
        import numpy as np

        self._ensure_models()

        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        # 1. Detect text boxes
        det_results = self.detect(image_path)

        if not det_results:
            return []

        # 2. Crop + classify + recognize each text box
        results = []
        rec_crops: list[tuple[int, np.ndarray]] = []  # (index, crop)

        for i, det in enumerate(det_results):
            box = det["box"]
            crop = _get_rotate_crop_image(img, box)

            # Optional orientation classification
            if self._cls_session is not None:
                cls_result = self._classify(crop)
                if cls_result["label"] == 1 and cls_result["confidence"] > _CLS_THRESH:
                    # Rotate 180°
                    crop = cv2.rotate(crop, cv2.ROTATE_180)

            rec_crops.append((i, crop))

        # Batch recognition
        rec_texts = self._recognize_batch(rec_crops)

        for i, det in enumerate(det_results):
            rec = rec_texts.get(i, {})
            results.append({
                "text": rec.get("text", ""),
                "confidence": rec.get("confidence", 0.0),
                "box": det["box"],
                "det_score": det["score"],
            })

        return results

    def detect(self, image_path: str) -> list[dict[str, Any]]:
        """Text detection only.

        Args:
            image_path: image file path

        Returns:
            [{box: [[x1,y1],...], score}, ...]
        """
        import cv2
        import numpy as np

        self._ensure_models()
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        orig_h, orig_w = img.shape[:2]

        # Preprocessing: resize to a multiple of 32 + ImageNet normalization
        input_tensor = self._det_preprocess(img)

        # Inference
        input_name = self._det_session.get_inputs()[0].name
        output_name = self._det_session.get_outputs()[0].name
        preds = self._det_session.run([output_name], {input_name: input_tensor})
        pred_map = preds[0].squeeze()  # (det_h, det_w)

        # Post-processing
        boxes = _db_post_process(pred_map, (orig_h, orig_w))
        return boxes

    def status(self) -> dict[str, Any]:
        """Return the service status."""
        return {
            "backend": self._backend,
            "model_size": self._model_size,
            "loaded": self._loaded,
            "load_error": self._load_error,
            "models_available": {
                "det": _model_path("det").exists(),
                "rec": _model_path("rec").exists(),
                "cls": _cls_model_path().exists(),
            },
        }

    # ── Internal methods ──

    def _det_preprocess(self, img: "np.ndarray") -> "np.ndarray":
        """Detection model preprocessing. Limit edge lengths per config, then align to a multiple of 32."""
        import cv2
        import numpy as np

        h, w = img.shape[:2]
        # Limit the size
        max_long_edge = OCR_MAX_LONG_EDGE
        max_short_edge = OCR_MAX_SHORT_EDGE
        if max(h, w) > max_long_edge:
            ratio = max_long_edge / max(h, w)
            h, w = int(h * ratio), int(w * ratio)
        if min(h, w) > max_short_edge:
            ratio = max_short_edge / min(h, w)
            h, w = int(h * ratio), int(w * ratio)
        # Align to a multiple of 32 (required by DBNet)
        new_h = int(np.ceil(h / 32) * 32)
        new_w = int(np.ceil(w / 32) * 32)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        rgb = rgb.astype(np.float32) / 255.0
        # ImageNet mean/std normalization
        mean = np.array([0.485, 0.456, 0.406]).reshape(3, 1, 1)
        std = np.array([0.229, 0.224, 0.225]).reshape(3, 1, 1)
        chw = np.transpose(rgb, (2, 0, 1))
        chw = (chw - mean) / std
        return np.expand_dims(chw, axis=0).astype(np.float32)

    def _classify(self, crop: "np.ndarray") -> dict[str, Any]:
        """Orientation classification: 0 = upright, 1 = 180° rotated."""
        if self._cls_session is None:
            return {"label": 0, "confidence": 0.0}

        input_tensor = _cls_preprocess(crop)
        input_name = self._cls_session.get_inputs()[0].name
        output_name = self._cls_session.get_outputs()[0].name
        preds = self._cls_session.run([output_name], {input_name: input_tensor})
        probs = preds[0].squeeze()  # (2,)

        import numpy as np
        label = int(np.argmax(probs))
        conf = float(probs[label])
        return {"label": label, "confidence": conf}

    def _recognize_batch(
        self, crops: list[tuple[int, "np.ndarray"]]
    ) -> dict[int, dict[str, Any]]:
        """Recognize text in batches."""
        import cv2
        import numpy as np

        if not crops:
            return {}

        results: dict[int, dict[str, Any]] = {}

        # Process in batches
        for batch_start in range(0, len(crops), _REC_BATCH_SIZE):
            batch = crops[batch_start: batch_start + _REC_BATCH_SIZE]
            batch_tensors = []
            batch_indices = []

            for idx, crop in batch:
                # Recognition preprocessing: resize to height 48, width proportional
                h, w = crop.shape[:2]
                ratio = _REC_IMAGE_HEIGHT / h
                new_w = int(w * ratio)
                resized = cv2.resize(
                    crop, (new_w, _REC_IMAGE_HEIGHT), interpolation=cv2.INTER_LINEAR
                )
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                rgb = rgb.astype(np.float32) / 255.0
                chw = np.transpose(rgb, (2, 0, 1))
                batch_tensors.append(chw)
                batch_indices.append(idx)

            # Find the widest to use as the batch width
            widths = [t.shape[2] for t in batch_tensors]
            max_w = max(widths)

            # Pad to the same width
            padded = []
            for t in batch_tensors:
                if t.shape[2] < max_w:
                    pad = np.zeros((3, _REC_IMAGE_HEIGHT, max_w - t.shape[2]),
                                   dtype=np.float32)
                    t = np.concatenate([t, pad], axis=2)
                padded.append(t)

            batch_input = np.stack(padded, axis=0).astype(np.float32)

            # Inference
            input_name = self._rec_session.get_inputs()[0].name
            output_name = self._rec_session.get_outputs()[0].name
            preds = self._rec_session.run(
                [output_name], {input_name: batch_input}
            )
            # preds[0] shape: (batch, W, num_classes)

            for j, out in enumerate(preds[0]):
                text, conf = _ctc_decode(out, self._character_list)
                orig_idx = batch_indices[j]
                results[orig_idx] = {"text": text, "confidence": round(conf, 4)}

        return results

    def _ensure_models(self):
        """Ensure the models are downloaded and loaded. Lazy loading; runs only on the first call."""
        if self._loaded:
            return
        if self._load_error:
            raise RuntimeError(f"Model loading failed: {self._load_error}")

        try:
            self._download_models_if_needed()
            self._load_sessions()
            self._loaded = True
            logger.info("OCR models loaded")
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"OCR model loading failed: {e}", exc_info=True)
            raise

    def _download_models_if_needed(self):
        """Download missing model files."""
        import cv2  # noqa: F401  # ensure opencv is available

        models_to_check = [
            ("det", _model_path("det")),
            ("rec", _model_path("rec")),
        ]

        for model_type, path in models_to_check:
            if path.exists():
                logger.debug(f"Model already exists: {path}")
                continue

            logger.info(f"Model {model_type} does not exist, starting download...")

            # Collect all single-file download sources and benchmark to pick the fastest first
            single_urls = [
                _MODEL_URLS.get(model_type),
                _MODEL_MIRROR_URLS.get(model_type),
                _MODEL_MODELSCOPE_URLS.get(model_type),
            ]
            single_urls = [u for u in single_urls if u]

            if len(single_urls) > 1:
                logger.info(f"{model_type}: benchmarking {len(single_urls)} mirror sources...")
                sorted_urls = _fastest_url(single_urls)
                if sorted_urls:
                    url = sorted_urls[0]
                    fallback = sorted_urls[1:]
                else:
                    url = single_urls[0]
                    fallback = single_urls[1:]
            elif single_urls:
                url = single_urls[0]
                fallback = []
            else:
                url = None
                fallback = []

            if url and _download_file(url, path, desc=f"PP-OCRv6_{model_type}", fallback_urls=fallback):
                continue

            # Fallback: download the tar package from Baidu PaddleX
            tar_url = _MODEL_TAR_URLS.get(model_type)
            if tar_url:
                dest_dir = _models_dir() / model_type
                if _download_tar_and_extract(
                    tar_url, dest_dir, desc=f"PP-OCRv6_{model_type}_tar"
                ):
                    continue

            raise RuntimeError(
                f"Unable to download model {model_type}. Please download it manually to {path}\n"
                f"  HuggingFace: {_MODEL_URLS.get(model_type, '')}\n"
                f"  PaddleX: {_MODEL_TAR_URLS.get(model_type, '')}"
            )

        # Download the classification model (optional; HuggingFace/Mirror only, ModelScope has no such model)
        cls_path = _cls_model_path()
        if not cls_path.exists():
            cls_url = _MODEL_URLS.get("cls")
            if cls_url:
                cls_mirror = _MODEL_MIRROR_URLS.get("cls")
                _download_file(cls_url, cls_path, desc="orientation classification model",
                               fallback_urls=[cls_mirror] if cls_mirror else None)
            else:
                logger.info("No download source available for the orientation classification model, skipping")

        # Load the character dictionary (prefer inference.yml, then fall back to ppocr_keys_v1.txt)
        self._character_list = _load_character_dict(_dict_path())
        logger.info(f"Character dictionary loaded: {len(self._character_list)} characters")

    def _load_sessions(self):
        """Load ONNX Runtime inference sessions."""
        import onnxruntime as ort

        det_path = str(_model_path("det"))
        rec_path = str(_model_path("rec"))
        cls_path = _cls_model_path()

        providers = ["CPUExecutionProvider"]
        if self._backend == "openvino":
            try:
                providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]

        self._det_session = ort.InferenceSession(det_path, providers=providers)
        self._rec_session = ort.InferenceSession(rec_path, providers=providers)

        if cls_path.exists():
            try:
                self._cls_session = ort.InferenceSession(cls_path, providers=providers)
                logger.info("Orientation classification model loaded")
            except Exception as e:
                logger.warning(f"Failed to load orientation classification model: {e}")
                self._cls_session = None

        # Print input/output information
        for name, sess in [
            ("det", self._det_session),
            ("rec", self._rec_session),
        ]:
            for inp in sess.get_inputs():
                logger.debug(f"{name} input: {inp.name} shape={inp.shape} type={inp.type}")
            for out in sess.get_outputs():
                logger.debug(f"{name} output: {out.name} shape={out.shape} type={out.type}")


# ── Factory function ──


def get_ocr_service(model_size: str = "medium") -> OcrService:
    """Get the OcrService singleton."""
    return OcrService(model_size=model_size)