from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import torch

from function import helper
from function import utils_rotate


@dataclass(frozen=True)
class PlateDetection:
    """Store one detected license plate result; example: PlateDetection(plate_text='51A-12345', confidence=0.91, edge=0.41, crop_data_url='data:image/jpeg;base64,...', frame_index=10, timestamp='2026-04-11T12:00:00Z')."""

    plate_text: str
    confidence: float
    edge: float
    crop_data_url: str
    frame_index: int
    timestamp: str


class LicensePlateRecognizer:
    """Recognize license plates from image frames using YOLOv5 detector and OCR models; example: recognizer = LicensePlateRecognizer(Path('model/LP_detector.pt'), Path('model/LP_ocr.pt'))."""

    def __init__(self, detector_weight_path: Path, ocr_weight_path: Path) -> None:
        self.detector_weight_path: Path = detector_weight_path
        self.ocr_weight_path: Path = ocr_weight_path
        # Lazy loading: models are loaded on first use, not at initialization
        self.detector_model: Any | None = None
        self.ocr_model: Any | None = None
        self._models_loaded: bool = False

    def _load_models(self) -> tuple[Any, Any]:
        """Load local custom YOLOv5 models on demand; example: detector_model, ocr_model = self._load_models()."""

        if not self.detector_weight_path.exists():
            raise FileNotFoundError(f"Detector weight file not found: {self.detector_weight_path}")
        if not self.ocr_weight_path.exists():
            raise FileNotFoundError(f"OCR weight file not found: {self.ocr_weight_path}")

        print(f"Loading detector model from {self.detector_weight_path}...")
        detector_model: Any = torch.hub.load(
            "ultralytics/yolov5",
            "custom",
            path=str(self.detector_weight_path),
            force_reload=False,
        )
        print(f"Loading OCR model from {self.ocr_weight_path}...")
        ocr_model: Any = torch.hub.load(
            "ultralytics/yolov5",
            "custom",
            path=str(self.ocr_weight_path),
            force_reload=False,
        )
        self._models_loaded = True
        return detector_model, ocr_model

    def _ensure_models_loaded(self) -> None:
        """Ensure models are loaded before use (lazy loading pattern)."""
        if not self._models_loaded:
            self.detector_model, self.ocr_model = self._load_models()

    def detect_on_frame(self, frame: Any, frame_index: int, confidence_threshold: float = 0.2) -> list[PlateDetection]:
        """Detect license plates on a single frame; example: detections = recognizer.detect_on_frame(frame=image, frame_index=0)."""

        # Ensure models are loaded before processing
        self._ensure_models_loaded()

        predictions: Any = self.detector_model(frame)
        normalized_boxes = predictions.xyxyn[0][:, :-1]

        frame_height: int = int(frame.shape[0])
        frame_width: int = int(frame.shape[1])
        detections: list[PlateDetection] = []

        for index in range(len(normalized_boxes)):
            row = normalized_boxes[index]
            confidence: float = float(row[4])
            if confidence < confidence_threshold:
                continue

            left: int = max(0, int(float(row[0]) * frame_width))
            top: int = max(0, int(float(row[1]) * frame_height))
            right: int = min(frame_width, int(float(row[2]) * frame_width))
            bottom: int = min(frame_height, int(float(row[3]) * frame_height))

            if right <= left or bottom <= top:
                continue

            plate_crop = frame[top:bottom, left:right]
            plate_text: str = self._read_plate_text(plate_crop)
            if plate_text == "unknown":
                continue

            crop_data_url: str = self._encode_crop_to_data_url(plate_crop)
            edge: float = confidence - confidence_threshold
            timestamp: str = datetime.now(timezone.utc).isoformat(timespec="seconds")

            detections.append(
                PlateDetection(
                    plate_text=plate_text,
                    confidence=confidence,
                    edge=edge,
                    crop_data_url=crop_data_url,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )
        return detections

    def _read_plate_text(self, plate_crop: Any) -> str:
        """Read plate text from a cropped plate image; example: plate_text = self._read_plate_text(plate_crop)."""

        for change_contrast in range(0, 2):
            for center_threshold in range(0, 2):
                rotated_crop = utils_rotate.deskew(plate_crop, change_contrast, center_threshold)
                plate_text: str = str(helper.read_plate(self.ocr_model, rotated_crop))
                if plate_text != "unknown":
                    return plate_text
        return "unknown"

    def _encode_crop_to_data_url(self, crop_image: Any) -> str:
        """Encode crop image to a data URL for direct streaming; example: data_url = self._encode_crop_to_data_url(crop_image)."""

        # Use JPEG to reduce bandwidth for realtime frontend streaming.
        success: bool
        encoded_buffer: Any
        success, encoded_buffer = cv2.imencode(".jpg", crop_image)
        if not success:
            return ""

        encoded_bytes: bytes = bytes(encoded_buffer)
        base64_bytes: bytes = base64.b64encode(encoded_bytes)
        base64_text: str = base64_bytes.decode("utf-8")
        return f"data:image/jpeg;base64,{base64_text}"
