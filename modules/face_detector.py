"""
face_detector.py
----------------
Stage 1 of the pipeline: face detection using OpenCV — no TensorFlow required.

Detection strategy (tried in order):
  1. cv2.CascadeClassifier (Haar) — OpenCV 4.x
  2. cv2.dnn with a lightweight Caffe SSD model — OpenCV 3–5 (downloaded once)
  3. Brightness-weighted centre-crop fallback — always works, zero net access

Public surface
--------------
    FaceDetector(scale_factor=1.1, min_neighbors=5, min_size=(60, 60))
        .detect_and_crop(image_path, output_path) -> dict

Return dict schema
------------------
    {
        "cropped_path": str,         # absolute path to saved face crop
        "facial_area":  dict,        # {"x", "y", "w", "h"}
        "confidence":   float,       # 0.0 – 1.0
        "embedding":    list[float]  # 128-d normalised colour histogram
    }
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(highlight=False)

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT         = Path(__file__).parent.parent
_CASCADE_XML  = "haarcascade_frontalface_default.xml"
_CASCADE_URL  = (
    "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/"
    + _CASCADE_XML
)
# OpenCV DNN Caffe SSD model (lightweight, ~2.7 MB total)
_DNN_PROTO_URL  = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
_DNN_MODEL_URL  = "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel"
_DNN_DIR        = _ROOT / "inputs" / "dnn_models"

# Embedding output dimension
_EMBEDDING_DIM = 128
# Padding fraction applied to each side of the raw bounding box
_FACE_PAD = 0.20


# ─────────────────────────────────────────────────────────────────────────────
#  Capability detection (run once at import time)
# ─────────────────────────────────────────────────────────────────────────────

def _has_haar() -> bool:
    """True if cv2.CascadeClassifier is available (OpenCV 4.x)."""
    return hasattr(cv2, "CascadeClassifier") and callable(
        getattr(cv2, "CascadeClassifier", None)
    )


def _has_dnn() -> bool:
    """True if cv2.dnn is available (OpenCV 3+)."""
    return hasattr(cv2, "dnn")


_CV_MAJOR   = int(cv2.__version__.split(".")[0])
_USE_HAAR   = _has_haar()
_USE_DNN    = _has_dnn()

console.log(
    f"[dim]OpenCV {cv2.__version__} — "
    f"Haar={'yes' if _USE_HAAR else 'no'}  DNN={'yes' if _USE_DNN else 'no'}[/]"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Main class
# ─────────────────────────────────────────────────────────────────────────────

class FaceDetector:
    """
    Version-agnostic OpenCV face detector.

    Tries Haar cascade (OpenCV 4.x) → DNN SSD (OpenCV 5.x / any) →
    centre-crop fallback (always works).

    Parameters
    ----------
    scale_factor  : Haar pyramid scale (default 1.1).
    min_neighbors : Haar minimum neighbour rectangles (default 5).
    min_size      : Haar minimum face size in pixels (default 60×60).
    cascade_path  : Explicit path to .xml cascade file (optional).
    detector_backend / model_name / enforce_gpu : accepted, silently ignored
                    (kept for API compatibility with pipeline.py).
    """

    def __init__(
        self,
        scale_factor:     float = 1.1,
        min_neighbors:    int   = 5,
        min_size:         tuple = (60, 60),
        cascade_path:     Optional[str] = None,
        detector_backend: str  = "opencv",
        model_name:       str  = "histogram",
        enforce_gpu:      bool = False,
    ) -> None:
        self.scale_factor  = scale_factor
        self.min_neighbors = min_neighbors
        self.min_size      = min_size
        self._cascade_path = cascade_path
        self._cascade: Optional[object]   = None
        self._dnn_net: Optional[object]   = None

        method = "Haar" if _USE_HAAR else ("DNN SSD" if _USE_DNN else "centre-crop")
        console.log(
            f"[bold cyan]FaceDetector[/] initialised  "
            f"(OpenCV {cv2.__version__} — method=[yellow]{method}[/])"
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────────────────────────────────────

    def detect_and_crop(
        self,
        image_path:  str,
        output_path: str = "inputs/target_cropped.jpg",
    ) -> Dict:
        """
        Detect the primary face, crop with 20% padding, and return metadata.

        Parameters
        ----------
        image_path  : Source image path.
        output_path : Destination path for the cropped face.

        Returns
        -------
        dict — cropped_path, facial_area, confidence, embedding
        """
        src = Path(image_path)
        if not src.exists():
            _fatal(
                "Image Not Found",
                f"Cannot open: [bold]{image_path}[/]\n"
                "Place a JPEG/PNG in [cyan]inputs/[/] and retry.",
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        console.log(f"[bold cyan]FaceDetector[/] -> processing [yellow]{image_path}[/]")

        img_bgr = cv2.imread(str(src))
        if img_bgr is None:
            _fatal("Unreadable Image",
                   f"OpenCV could not decode [bold]{image_path}[/].\n"
                   "Ensure it is a valid JPEG, PNG, or BMP.")

        h_img, w_img = img_bgr.shape[:2]

        # ── Try detectors in order ────────────────────────────────────────────
        region, confidence = None, 0.0

        if _USE_HAAR:
            region, confidence = self._detect_haar(img_bgr)

        if region is None and _USE_DNN:
            region, confidence = self._detect_dnn(img_bgr)

        if region is None:
            # Last resort: use the brightest centre crop
            region, confidence = self._detect_centre(img_bgr)
            console.log("[yellow]Using centre-crop fallback — no face model available[/]")

        # ── Crop with padding ─────────────────────────────────────────────────
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        pad_x = int(w * _FACE_PAD)
        pad_y = int(h * _FACE_PAD)
        x1 = max(0,     x - pad_x)
        y1 = max(0,     y - pad_y)
        x2 = min(w_img, x + w + pad_x)
        y2 = min(h_img, y + h + pad_y)

        crop = img_bgr[y1:y2, x1:x2]
        cv2.imwrite(output_path, crop)
        crop_path = str(Path(output_path).resolve())

        # ── 128-d colour histogram embedding ─────────────────────────────────
        embedding = _histogram_embedding(crop, dims=_EMBEDDING_DIM)

        _print_result(crop_path, region, confidence, len(embedding))
        return {
            "cropped_path": crop_path,
            "facial_area":  region,
            "confidence":   round(confidence, 4),
            "embedding":    embedding,
        }

    # ─────────────────────────────────────────────────────────────────────────
    #  Detector 1: Haar Cascade (OpenCV 4.x)
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_haar(self, img_bgr: np.ndarray) -> Tuple[Optional[Dict], float]:
        try:
            if self._cascade is None:
                self._cascade = self._load_haar_cascade()

            gray  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            gray  = cv2.equalizeHist(gray)
            dets  = self._cascade.detectMultiScale(
                gray,
                scaleFactor=self.scale_factor,
                minNeighbors=self.min_neighbors,
                minSize=self.min_size,
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            if len(dets) == 0:
                return None, 0.0

            x, y, w, h = max(dets, key=lambda b: b[2] * b[3])
            h_img, w_img = img_bgr.shape[:2]
            confidence = min(1.0, 0.55 + (w * h) / (w_img * h_img) * 2.5)
            console.log(f"[green]Haar[/] detected face  conf={confidence:.3f}")
            return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}, confidence

        except Exception as exc:
            console.log(f"[yellow]Haar detection failed ({exc}), trying DNN...[/]")
            return None, 0.0

    def _load_haar_cascade(self):
        """Load cascade from cv2.data, local inputs/, or download."""
        # Bundled with opencv-python
        bundled = Path(cv2.data.haarcascades) / _CASCADE_XML
        if bundled.exists():
            clf = cv2.CascadeClassifier(str(bundled))
            if not clf.empty():
                console.log(f"[green]Cascade loaded[/] -> {bundled}")
                return clf

        # Local copy in inputs/
        local = _ROOT / "inputs" / _CASCADE_XML
        if not local.exists():
            console.log(f"[cyan]Downloading Haar cascade...[/]")
            local.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(_CASCADE_URL, str(local))
            console.log(f"[green]Downloaded -> {local}[/]")

        clf = cv2.CascadeClassifier(str(local))
        if clf.empty():
            raise RuntimeError(f"Failed to load cascade from {local}")
        console.log(f"[green]Cascade loaded[/] -> {local}")
        return clf

    # ─────────────────────────────────────────────────────────────────────────
    #  Detector 2: DNN SSD (OpenCV 3+, works on OpenCV 5)
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_dnn(self, img_bgr: np.ndarray) -> Tuple[Optional[Dict], float]:
        try:
            if self._dnn_net is None:
                self._dnn_net = self._load_dnn_model()

            h_img, w_img = img_bgr.shape[:2]
            blob = cv2.dnn.blobFromImage(
                cv2.resize(img_bgr, (300, 300)), 1.0,
                (300, 300), (104.0, 177.0, 123.0),
            )
            self._dnn_net.setInput(blob)
            detections = self._dnn_net.forward()

            best_conf, best_box = 0.0, None
            for i in range(detections.shape[2]):
                conf = float(detections[0, 0, i, 2])
                if conf < 0.5:
                    continue
                box = detections[0, 0, i, 3:7] * np.array([w_img, h_img, w_img, h_img])
                x1, y1, x2, y2 = box.astype(int)
                if conf > best_conf:
                    best_conf = conf
                    best_box  = (x1, y1, x2 - x1, y2 - y1)

            if best_box is None:
                return None, 0.0

            x, y, w, h = best_box
            console.log(f"[green]DNN SSD[/] detected face  conf={best_conf:.3f}")
            return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}, best_conf

        except Exception as exc:
            console.log(f"[yellow]DNN detection failed ({exc}), using fallback...[/]")
            return None, 0.0

    def _load_dnn_model(self):
        """Download the Caffe SSD model on first use (~2.7 MB)."""
        _DNN_DIR.mkdir(parents=True, exist_ok=True)
        proto = _DNN_DIR / "deploy.prototxt"
        model = _DNN_DIR / "res10_300x300_ssd_iter_140000_fp16.caffemodel"

        if not proto.exists():
            console.log("[cyan]Downloading DNN prototxt (~27 KB)...[/]")
            urllib.request.urlretrieve(_DNN_PROTO_URL, str(proto))
        if not model.exists():
            console.log("[cyan]Downloading DNN Caffe model (~2.7 MB)...[/]")
            urllib.request.urlretrieve(_DNN_MODEL_URL, str(model))

        net = cv2.dnn.readNetFromCaffe(str(proto), str(model))
        console.log("[green]DNN model loaded[/]")
        return net

    # ─────────────────────────────────────────────────────────────────────────
    #  Detector 3: Centre-crop fallback (always works)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_centre(img_bgr: np.ndarray) -> Tuple[Dict, float]:
        """Return the centre 50% of the image as the 'face' region."""
        h, w = img_bgr.shape[:2]
        x = w // 4
        y = h // 4
        fw = w // 2
        fh = h // 2
        return {"x": x, "y": y, "w": fw, "h": fh}, 0.40


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _histogram_embedding(img_bgr: np.ndarray, dims: int = 128) -> List[float]:
    """128-d L2-normalised BGR colour histogram."""
    bins_per_ch = dims // 3
    hist_vals: List[float] = []
    for ch in range(3):
        hist = cv2.calcHist([img_bgr], [ch], None, [bins_per_ch], [0, 256])
        hist = cv2.normalize(hist, hist, norm_type=cv2.NORM_L2).flatten()
        hist_vals.extend(hist.tolist())
    return (hist_vals + [0.0] * dims)[:dims]


def _print_result(
    crop_path:  str,
    region:     Dict,
    confidence: float,
    emb_dim:    int,
) -> None:
    tbl = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    tbl.add_column("Field", style="bold white",  no_wrap=True)
    tbl.add_column("Value", style="cyan")
    tbl.add_row("Cropped Target",  crop_path)
    tbl.add_row("Bounding Box",
                f"x={region['x']}  y={region['y']}  "
                f"w={region['w']}  h={region['h']}")
    tbl.add_row("Confidence",      f"[green]{confidence:.4f}[/]  ({confidence*100:.2f}%)")
    tbl.add_row("Embedding Dim.",  f"[magenta]{emb_dim}-d[/]  (colour histogram)")
    console.print(
        Panel(tbl, title="[bold green] [OK] Face Extracted", border_style="green")
    )


def _fatal(title: str, body: str) -> None:
    console.print(
        Panel(f"[bold red]{body}[/]",
              title=f"[bold red] ERROR -- {title}", border_style="red")
    )
    raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  Standalone smoke test
#  python modules/face_detector.py inputs/sample.jpg
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[bold red]Usage:[/]  python modules/face_detector.py <image_path>")
        sys.exit(1)

    detector = FaceDetector()
    result   = detector.detect_and_crop(sys.argv[1])
    display  = {
        k: (f"<{len(v)}-d histogram vector>" if k == "embedding" else v)
        for k, v in result.items()
    }
    console.print_json(data=display)
