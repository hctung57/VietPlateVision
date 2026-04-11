from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request
from fastapi import UploadFile
from fastapi import WebSocket
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import AppConfig
from app.detector import LicensePlateRecognizer
from app.history_store import DetectionRecord
from app.history_store import HistoryStore
from app.processing_manager import ProcessingManager
from app.processing_manager import JobStatus
from app.realtime_hub import RealtimeHub


BASE_DIR: Path = Path(__file__).resolve().parent.parent
STATIC_DIR: Path = BASE_DIR / "app" / "static"
TEMPLATE_DIR: Path = BASE_DIR / "app" / "templates"
UPLOAD_DIR: Path = BASE_DIR / "storage" / "uploads"
MODEL_DIR: Path = BASE_DIR / "model"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
config: AppConfig = AppConfig.from_environment()

realtime_hub = RealtimeHub()
recognizer = LicensePlateRecognizer(
    detector_weight_path=MODEL_DIR / "LP_detector.pt",
    ocr_weight_path=MODEL_DIR / "LP_ocr.pt",
)
history_store: HistoryStore | None = None
if config.enable_history:
    # Initialize DB connection only when persistence is enabled via environment variables.
    history_store = HistoryStore(database_path=BASE_DIR / config.history_db_path)


def publish_detection(payload: dict[str, Any]) -> None:
    """Push one detection payload to websocket clients in realtime; example: publish_detection(payload)."""

    realtime_hub.broadcast_from_thread(payload)
    if history_store is not None:
        history_store.insert_detection(
            timestamp=str(payload["timestamp"]),
            source_type=str(payload["source_type"]),
            source_name=str(payload["source_name"]),
            plate_text=str(payload["plate_text"]),
            confidence=float(payload["confidence"]),
            edge=float(payload["edge"]),
            crop_path=str(payload["crop_data_url"]),
            frame_index=int(payload["frame_index"]),
        )


processing_manager = ProcessingManager(recognizer=recognizer, on_detection=publish_detection)

app = FastAPI(title="VietPlateVision Dashboard", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.on_event("startup")
async def on_startup() -> None:
    """Assign the running event loop to realtime hub at startup; example: await on_startup()."""

    realtime_hub.set_event_loop(asyncio.get_running_loop())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main dashboard page; example: open http://localhost:8000/."""

    return templates.TemplateResponse(name="index.html", context={"request": request})


@app.get("/api/health")
async def health_check() -> JSONResponse:
    """Return service health and persistence mode; example: GET /api/health."""

    return JSONResponse(
        content={
            "status": "ok",
            "history_enabled": history_store is not None,
        }
    )


@app.websocket("/ws/detections")
async def websocket_detections(websocket: WebSocket) -> None:
    """Open websocket channel for realtime frontend detections; example: ws://localhost:8000/ws/detections."""

    await realtime_hub.websocket_handler(websocket)


@app.get("/api/history")
async def get_history(limit: int = 200) -> JSONResponse:
    """Return detection history when persistence is enabled; example: GET /api/history?limit=100."""

    if history_store is None:
        raise HTTPException(status_code=503, detail="History persistence đang tắt (ENABLE_HISTORY=false)")

    limited_rows: list[DetectionRecord] = history_store.list_detections(limit=max(1, min(limit, 2000)))
    payload: list[dict[str, Any]] = []
    for row in limited_rows:
        serialized_row: dict[str, Any] = HistoryStore.serialize(row)
        serialized_row["crop_data_url"] = serialized_row.pop("crop_path")
        payload.append(serialized_row)
    return JSONResponse(content={"items": payload})


@app.get("/api/history/{detection_id}")
async def get_history_item(detection_id: int) -> JSONResponse:
    """Return one detection record when persistence is enabled; example: GET /api/history/10."""

    if history_store is None:
        raise HTTPException(status_code=503, detail="History persistence đang tắt (ENABLE_HISTORY=false)")

    record: DetectionRecord | None = history_store.get_detection(detection_id=detection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi detect")

    payload: dict[str, Any] = HistoryStore.serialize(record)
    payload["crop_data_url"] = payload.pop("crop_path")
    return JSONResponse(content={"item": payload})


@app.get("/api/jobs")
async def list_jobs() -> JSONResponse:
    """Return current status of processing jobs; example: GET /api/jobs."""

    jobs: list[JobStatus] = processing_manager.list_jobs()
    payload: list[dict[str, Any]] = [
        {
            "job_id": job.job_id,
            "source_type": job.source_type,
            "source_name": job.source_name,
            "status": job.status,
            "processed_frames": job.processed_frames,
            "detections": job.detections,
            "error": job.error,
        }
        for job in jobs
    ]
    return JSONResponse(content={"items": payload})


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str) -> JSONResponse:
    """Stop a running job; example: POST /api/jobs/<job_id>/stop."""

    stopped: bool = processing_manager.stop_job(job_id=job_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    return JSONResponse(content={"message": "Đã gửi yêu cầu dừng job", "job_id": job_id})


@app.post("/api/process/image")
async def process_image(file: UploadFile = File(...)) -> JSONResponse:
    """Process uploaded image and stream realtime detections; example: POST /api/process/image with multipart file."""

    if file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="Thiếu tên file ảnh")

    content: bytes = await file.read()
    detections: list[dict[str, Any]] = processing_manager.process_image_bytes(image_bytes=content, source_name=file.filename)
    return JSONResponse(
        content={
            "message": "Đã xử lý ảnh",
            "source_type": "image",
            "source_name": file.filename,
            "detections": detections,
            "total": len(detections),
        }
    )


@app.post("/api/process/video")
async def process_video(
    file: UploadFile = File(...),
    sample_interval: int = Form(5),
) -> JSONResponse:
    """Start a background job for uploaded video; example: POST /api/process/video with video file and sample_interval."""

    if file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="Thiếu tên file video")

    safe_filename: str = Path(file.filename).name
    target_path: Path = UPLOAD_DIR / f"{uuid4().hex}_{safe_filename}"
    content: bytes = await file.read()
    target_path.write_bytes(content)

    job_id: str = processing_manager.start_video_job(
        video_path=target_path,
        source_name=file.filename,
        sample_interval=sample_interval,
    )
    return JSONResponse(
        content={
            "message": "Đã khởi chạy job video",
            "job_id": job_id,
            "source_type": "video",
            "source_name": file.filename,
        }
    )


@app.post("/api/process/stream")
async def process_stream(
    stream_url: str = Form(...),
    source_name: str = Form("stream-camera"),
    sample_interval: int = Form(5),
) -> JSONResponse:
    """Start a background job for camera stream URL; example: POST /api/process/stream with stream_url=rtsp://..."""

    cleaned_url: str = stream_url.strip()
    if cleaned_url == "":
        raise HTTPException(status_code=400, detail="stream_url không hợp lệ")

    job_id: str = processing_manager.start_stream_job(
        stream_url=cleaned_url,
        source_name=source_name,
        sample_interval=sample_interval,
    )
    return JSONResponse(
        content={
            "message": "Đã khởi chạy job stream",
            "job_id": job_id,
            "source_type": "stream",
            "source_name": source_name,
        }
    )


@app.post("/api/process/webcam")
async def process_webcam(
    camera_index: int = Form(0),
    sample_interval: int = Form(5),
) -> JSONResponse:
    """Start a background job for local webcam; example: POST /api/process/webcam with camera_index=0."""

    job_id: str = processing_manager.start_webcam_job(
        camera_index=camera_index,
        sample_interval=sample_interval,
    )
    return JSONResponse(
        content={
            "message": "Đã khởi chạy job webcam",
            "job_id": job_id,
            "source_type": "webcam",
            "source_name": f"webcam-{camera_index}",
        }
    )
