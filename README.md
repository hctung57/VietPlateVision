# VietPlateVision 2.0 - ANPR Web Dashboard

VietPlateVision was rebuilt as a web application with a dark-mode trading-dashboard style, optimized for dense data monitoring and real-time operations.

UI direction is inspired by OdinEye:
- https://github.com/hctung57/OdinEye

## 1) Key Features

- Dark-mode web dashboard with a 3-panel layout:
	- Left Sidebar: select input source and control jobs.
	- Main Data Table: live real-time detection feed.
	- Right Detail Panel: selected record details and plate crop image.
- Supports 4 input sources:
	- Static image.
	- Video file.
	- Camera stream URL (RTSP/HTTP).
	- Local webcam (camera index).
- Real-time feed output includes:
	- Detection timestamp (UTC).
	- Recognized license plate.
	- Confidence score.
	- Edge value = confidence - threshold (positive in green, negative in red).
	- Plate crop image streamed as data URL.
- Default mode is realtime-only (no DB/file persistence).
- Optional persistence via environment variables to store detection history in SQLite.
- Supports Docker and Docker Compose deployment.

## 2) Project Architecture

```text
app/
	main.py                 # FastAPI app + REST API
	detector.py             # Model loading + per-frame detection/OCR
	history_store.py        # History persistence module (optional)
	processing_manager.py   # Video/stream/webcam job manager
	realtime_hub.py         # WebSocket hub for frontend streaming
	templates/index.html    # Dashboard UI
	static/css/dashboard.css
	static/js/dashboard.js
training/
	configs/
		custom_data.yaml
		Letter_detect.yaml
	notebooks/
		License_plate_training.ipynb
		Letter_detection.ipynb
	README.md               # Detailed training guide
storage/
	uploads/                # Temporary uploaded files
lp_location.py            # Server entrypoint
Dockerfile
docker-compose.yml
requirements.txt
```

## 3) Prepare Model Weights

Place these 2 weight files in:

- `model/LP_detector.pt`
- `model/LP_ocr.pt`

The app reads exactly these two paths by default.

## 3.1) Training Folder Layout

Training assets are split into two clear groups:

- `training/notebooks/`: training notebooks.
- `training/configs/`: YAML files for dataset/training configs.

See detailed instructions at:

- `training/README.md`

## 4) Run Locally (without Docker)

### Step 1: Create Environment and Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Start Server

```bash
python3 lp_location.py
```

### Enable History Persistence (optional)

```bash
export ENABLE_HISTORY=true
export HISTORY_DB_PATH=storage/history.db
python3 lp_location.py
```

Environment variables:

- `ENABLE_HISTORY`: `true/false` (default: `false`).
- `HISTORY_DB_PATH`: SQLite path when history is enabled (default: `storage/history.db`).

Open in browser:

```text
http://localhost:8000
```

## 5) Run with Docker

### Build Image

```bash
docker build -t vietplatevision:latest .
```

### Run Container

```bash
docker run --rm -p 8000:8000 \
	-v $(pwd)/storage:/app/storage \
	-v $(pwd)/model:/app/model \
	--device /dev/video0:/dev/video0 \
	vietplatevision:latest
```

## 6) Run with Docker Compose

```bash
docker compose up --build
```

### Enable History with Docker Compose (optional)

```bash
ENABLE_HISTORY=true HISTORY_DB_PATH=storage/history.db docker compose up --build
```

After startup, open:

```text
http://localhost:8000
```

## 7) UI Usage Guide

1. Select source type in the left sidebar: Image, Video, Stream, or Webcam.
2. Configure the corresponding input.
3. Click process/start job.
4. Monitor job status in Runtime Jobs.
5. Monitor the live feed table and click a row to view details in the right panel.

## 8) API Quick Reference

- `POST /api/process/image`: upload image.
- `POST /api/process/video`: upload video + `sample_interval`.
- `POST /api/process/stream`: `stream_url`, `source_name`, `sample_interval`.
- `POST /api/process/webcam`: `camera_index`, `sample_interval`.
- `WS /ws/detections`: receive real-time detections (plate + crop base64).
- `GET /api/health`: service status + persistence mode.
- `GET /api/history?limit=300`: detection history when `ENABLE_HISTORY=true`.
- `GET /api/history/{id}`: detection detail when `ENABLE_HISTORY=true`.
- `GET /api/jobs`: list jobs.
- `POST /api/jobs/{job_id}/stop`: stop a running job.

## 9) Operational Notes

- On first run, `torch.hub` may download YOLOv5 resources, so startup can be slower.
- If webcam is needed in Docker, map the correct `/dev/video*` device.
- RTSP streaming requires proper network access between container and camera.

## 10) Future Improvements

- Add license plate whitelist/blacklist for real-time alerts.
- Export CSV by shift or by camera.
- Add full-frame snapshots and tracking IDs for better traceability.
