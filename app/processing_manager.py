from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from threading import Lock
from threading import Thread
from typing import Any
from typing import Callable
from uuid import uuid4

import cv2
import numpy as np

from app.detector import LicensePlateRecognizer


@dataclass
class JobStatus:
    """Describe status for a video/stream/webcam processing job; example: JobStatus(job_id='abc', source_type='video', source_name='sample.mp4', status='running', processed_frames=240, detections=12, error='')."""

    job_id: str
    source_type: str
    source_name: str
    status: str
    processed_frames: int
    detections: int
    error: str


class ProcessingManager:
    """Manage asynchronous jobs for video/stream/webcam processing; example: manager = ProcessingManager(recognizer, on_detection=print)."""

    def __init__(
        self,
        recognizer: LicensePlateRecognizer,
        on_detection: Callable[[dict[str, Any]], None],
    ) -> None:
        self.recognizer: LicensePlateRecognizer = recognizer
        self.on_detection: Callable[[dict[str, Any]], None] = on_detection
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock: Lock = Lock()

    def process_image_bytes(self, image_bytes: bytes, source_name: str) -> list[dict[str, Any]]:
        """Process image bytes and return realtime detection payloads; example: items = manager.process_image_bytes(image_bytes=data, source_name='demo.jpg')."""

        image_array: np.ndarray[Any, Any] = np.frombuffer(image_bytes, dtype=np.uint8)
        image: Any = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Không decode được ảnh upload")

        detections = self.recognizer.detect_on_frame(frame=image, frame_index=0)
        payload_items: list[dict[str, Any]] = []
        for detection in detections:
            payload: dict[str, Any] = {
                "timestamp": detection.timestamp,
                "source_type": "image",
                "source_name": source_name,
                "plate_text": detection.plate_text,
                "confidence": detection.confidence,
                "edge": detection.edge,
                "crop_data_url": detection.crop_data_url,
                "frame_index": detection.frame_index,
            }
            self.on_detection(payload)
            payload_items.append(payload)
        return payload_items

    def start_video_job(self, video_path: Path, source_name: str, sample_interval: int = 5) -> str:
        """Start a processing job for uploaded video; example: job_id = manager.start_video_job(Path('storage/uploads/input.mp4'), source_name='input.mp4')."""

        return self._start_capture_job(
            capture_source=str(video_path),
            source_type="video",
            source_name=source_name,
            sample_interval=sample_interval,
            delete_source_on_finish=True,
        )

    def start_stream_job(self, stream_url: str, source_name: str, sample_interval: int = 5) -> str:
        """Start a processing job for camera stream URL; example: job_id = manager.start_stream_job('rtsp://...', source_name='Gate-Cam')."""

        return self._start_capture_job(
            capture_source=stream_url,
            source_type="stream",
            source_name=source_name,
            sample_interval=sample_interval,
            delete_source_on_finish=False,
        )

    def start_webcam_job(self, camera_index: int, sample_interval: int = 5) -> str:
        """Start a processing job for local webcam; example: job_id = manager.start_webcam_job(camera_index=0)."""

        return self._start_capture_job(
            capture_source=camera_index,
            source_type="webcam",
            source_name=f"webcam-{camera_index}",
            sample_interval=sample_interval,
            delete_source_on_finish=False,
        )

    def stop_job(self, job_id: str) -> bool:
        """Stop a running job by id; example: stopped = manager.stop_job(job_id)."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job["stop_event"].set()
            return True

    def list_jobs(self) -> list[JobStatus]:
        """Return current jobs; example: jobs = manager.list_jobs()."""

        with self._lock:
            statuses: list[JobStatus] = []
            for _, job in self._jobs.items():
                statuses.append(
                    JobStatus(
                        job_id=str(job["job_id"]),
                        source_type=str(job["source_type"]),
                        source_name=str(job["source_name"]),
                        status=str(job["status"]),
                        processed_frames=int(job["processed_frames"]),
                        detections=int(job["detections"]),
                        error=str(job["error"]),
                    )
                )
            return statuses

    def _start_capture_job(
        self,
        capture_source: str | int,
        source_type: str,
        source_name: str,
        sample_interval: int,
        delete_source_on_finish: bool,
    ) -> str:
        """Create and start a worker thread for capture source processing; example: job_id = self._start_capture_job(capture_source='video.mp4', source_type='video', source_name='video.mp4', sample_interval=5)."""

        normalized_interval: int = max(1, sample_interval)
        job_id: str = uuid4().hex
        stop_event: Event = Event()

        job_payload: dict[str, Any] = {
            "job_id": job_id,
            "source_type": source_type,
            "source_name": source_name,
            "status": "running",
            "processed_frames": 0,
            "detections": 0,
            "error": "",
            "capture_source": capture_source,
            "delete_source_on_finish": delete_source_on_finish,
            "stop_event": stop_event,
            "thread": None,
        }

        worker: Thread = Thread(
            target=self._run_capture_job,
            args=(job_id, capture_source, source_type, source_name, normalized_interval, delete_source_on_finish),
            daemon=True,
        )
        job_payload["thread"] = worker

        with self._lock:
            self._jobs[job_id] = job_payload
        worker.start()

        return job_id

    def _run_capture_job(
        self,
        job_id: str,
        capture_source: str | int,
        source_type: str,
        source_name: str,
        sample_interval: int,
        delete_source_on_finish: bool,
    ) -> None:
        """Run frame-reading loop and stream realtime detections; example: self._run_capture_job(job_id, 'video.mp4', 'video', 'video.mp4', 5)."""

        capture = cv2.VideoCapture(capture_source)
        if not capture.isOpened():
            self._set_error(job_id=job_id, message=f"Không mở được nguồn: {capture_source}")
            return

        frame_index: int = -1
        try:
            while True:
                with self._lock:
                    stop_event: Event = self._jobs[job_id]["stop_event"]
                if stop_event.is_set():
                    self._set_status(job_id=job_id, status="stopped")
                    break

                grabbed: bool
                frame: Any
                grabbed, frame = capture.read()
                if not grabbed:
                    self._set_status(job_id=job_id, status="finished")
                    break

                frame_index += 1
                if frame_index % sample_interval != 0:
                    self._increment_processed_frames(job_id=job_id)
                    continue

                detections = self.recognizer.detect_on_frame(frame=frame, frame_index=frame_index)
                for detection in detections:
                    payload: dict[str, Any] = {
                        "timestamp": detection.timestamp,
                        "source_type": source_type,
                        "source_name": source_name,
                        "plate_text": detection.plate_text,
                        "confidence": detection.confidence,
                        "edge": detection.edge,
                        "crop_data_url": detection.crop_data_url,
                        "frame_index": detection.frame_index,
                    }
                    self.on_detection(payload)
                    self._increment_detection_count(job_id=job_id)

                self._increment_processed_frames(job_id=job_id)
        except Exception as error:  # noqa: BLE001
            self._set_error(job_id=job_id, message=str(error))
        finally:
            capture.release()
            if delete_source_on_finish and isinstance(capture_source, str):
                source_path: Path = Path(capture_source)
                if source_path.exists():
                    try:
                        source_path.unlink()
                    except OSError:
                        # Ignore temp-file cleanup failures to avoid interrupting the main flow.
                        pass

    def _set_status(self, job_id: str, status: str) -> None:
        """Update job status; example: self._set_status(job_id, status='finished')."""

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = status

    def _set_error(self, job_id: str, message: str) -> None:
        """Mark a job as failed and store error message; example: self._set_error(job_id, message='Cannot open camera')."""

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "error"
                self._jobs[job_id]["error"] = message

    def _increment_processed_frames(self, job_id: str) -> None:
        """Increase processed frame counter; example: self._increment_processed_frames(job_id)."""

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["processed_frames"] += 1

    def _increment_detection_count(self, job_id: str) -> None:
        """Increase detection counter for a job; example: self._increment_detection_count(job_id)."""

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["detections"] += 1
