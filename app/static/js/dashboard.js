const statusText = document.getElementById("status-text");
const historyBody = document.getElementById("history-body");
const detailCard = document.getElementById("detail-card");
const jobsList = document.getElementById("jobs-list");
let detectionSocket = null;

function setStatus(message) {
    statusText.textContent = message;
}

function formatValue(value, digits = 3) {
    return Number(value).toFixed(digits);
}

function edgeClass(value) {
    return Number(value) >= 0 ? "value-positive" : "value-negative";
}

function switchPanel(sourceType) {
    const tabs = document.querySelectorAll(".source-tab");
    const panels = document.querySelectorAll(".control-panel");

    tabs.forEach((button) => {
        button.classList.toggle("active", button.dataset.source === sourceType);
    });

    panels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.panel === sourceType);
    });
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.detail || payload.message || "Request failed");
    }
    return payload;
}

function renderDetail(item) {
    detailCard.innerHTML = `
        <img src="${item.crop_data_url}" alt="plate crop" />
        <div class="detail-grid">
            <div><strong>Plate:</strong> ${item.plate_text}</div>
            <div><strong>Time:</strong> ${item.timestamp}</div>
            <div><strong>Source:</strong> ${item.source_type} / ${item.source_name}</div>
            <div><strong>Confidence:</strong> ${formatValue(item.confidence)}</div>
            <div><strong>Edge:</strong> <span class="${edgeClass(item.edge)}">${formatValue(item.edge)}</span></div>
            <div><strong>Frame:</strong> ${item.frame_index}</div>
        </div>
    `;
}

function createHistoryRow(item) {
    const row = document.createElement("tr");
    row.innerHTML = `
        <td>${item.timestamp}</td>
        <td>${item.source_type}:${item.source_name}</td>
        <td>${item.plate_text}</td>
        <td>${formatValue(item.confidence)}</td>
        <td class="${edgeClass(item.edge)}">${formatValue(item.edge)}</td>
        <td><img class="crop-thumb" src="${item.crop_data_url}" alt="crop" /></td>
    `;

    row.addEventListener("click", () => {
        document.querySelectorAll("#history-body tr").forEach((node) => node.classList.remove("selected"));
        row.classList.add("selected");
        renderDetail(item);
    });

    return row;
}

function addRealtimeDetection(item) {
    const row = createHistoryRow(item);
    historyBody.prepend(row);

    const maxRows = 300;
    while (historyBody.children.length > maxRows) {
        historyBody.removeChild(historyBody.lastElementChild);
    }
}

function connectRealtimeSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socketUrl = `${protocol}//${window.location.host}/ws/detections`;
    detectionSocket = new WebSocket(socketUrl);

    detectionSocket.onopen = () => {
        setStatus("Realtime connected");
    };

    detectionSocket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        addRealtimeDetection(payload);
    };

    detectionSocket.onclose = () => {
        setStatus("Realtime disconnected. Reconnecting...");
        setTimeout(connectRealtimeSocket, 1500);
    };

    detectionSocket.onerror = () => {
        setStatus("Realtime socket error");
    };
}

async function refreshJobs() {
    const payload = await requestJson("/api/jobs");
    jobsList.innerHTML = "";

    payload.items.forEach((job) => {
        const row = document.createElement("div");
        row.className = "job-row";
        row.innerHTML = `
            <div><strong>${job.source_type}</strong> - ${job.source_name}</div>
            <div>Status: ${job.status}</div>
            <div>Frames: ${job.processed_frames} | Hits: ${job.detections}</div>
            <div class="value-negative">${job.error || ""}</div>
            <button data-stop-id="${job.job_id}">Stop</button>
        `;
        jobsList.appendChild(row);
    });

    document.querySelectorAll("button[data-stop-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            try {
                const jobId = button.dataset.stopId;
                await requestJson(`/api/jobs/${jobId}/stop`, { method: "POST" });
                setStatus(`Stop requested for job ${jobId}`);
                await refreshJobs();
            } catch (error) {
                setStatus(error.message);
            }
        });
    });
}

async function submitImage() {
    const fileInput = document.getElementById("image-file");
    if (!fileInput.files || fileInput.files.length === 0) {
        setStatus("Please select image file");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    setStatus("Processing image...");
    const payload = await requestJson("/api/process/image", {
        method: "POST",
        body: formData,
    });
    setStatus(`${payload.message}: ${payload.total} detections`);
}

async function submitVideo() {
    const fileInput = document.getElementById("video-file");
    const intervalInput = document.getElementById("video-interval");

    if (!fileInput.files || fileInput.files.length === 0) {
        setStatus("Please select video file");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("sample_interval", intervalInput.value || "5");

    setStatus("Starting video job...");
    const payload = await requestJson("/api/process/video", {
        method: "POST",
        body: formData,
    });
    setStatus(`Video job started: ${payload.job_id}`);
    await refreshJobs();
}

async function submitStream() {
    const urlInput = document.getElementById("stream-url");
    const nameInput = document.getElementById("stream-name");
    const intervalInput = document.getElementById("stream-interval");

    const formData = new FormData();
    formData.append("stream_url", urlInput.value);
    formData.append("source_name", nameInput.value || "stream-camera");
    formData.append("sample_interval", intervalInput.value || "5");

    setStatus("Starting stream job...");
    const payload = await requestJson("/api/process/stream", {
        method: "POST",
        body: formData,
    });
    setStatus(`Stream job started: ${payload.job_id}`);
    await refreshJobs();
}

async function submitWebcam() {
    const indexInput = document.getElementById("webcam-index");
    const intervalInput = document.getElementById("webcam-interval");

    const formData = new FormData();
    formData.append("camera_index", indexInput.value || "0");
    formData.append("sample_interval", intervalInput.value || "5");

    setStatus("Starting webcam job...");
    const payload = await requestJson("/api/process/webcam", {
        method: "POST",
        body: formData,
    });
    setStatus(`Webcam job started: ${payload.job_id}`);
    await refreshJobs();
}

function registerEvents() {
    document.querySelectorAll(".source-tab").forEach((button) => {
        button.addEventListener("click", () => {
            switchPanel(button.dataset.source);
        });
    });

    document.getElementById("refresh-button").addEventListener("click", async () => {
        try {
            await refreshJobs();
            setStatus("Jobs refreshed");
        } catch (error) {
            setStatus(error.message);
        }
    });

    document.getElementById("image-submit").addEventListener("click", async () => {
        try {
            await submitImage();
        } catch (error) {
            setStatus(error.message);
        }
    });

    document.getElementById("video-submit").addEventListener("click", async () => {
        try {
            await submitVideo();
        } catch (error) {
            setStatus(error.message);
        }
    });

    document.getElementById("stream-submit").addEventListener("click", async () => {
        try {
            await submitStream();
        } catch (error) {
            setStatus(error.message);
        }
    });

    document.getElementById("webcam-submit").addEventListener("click", async () => {
        try {
            await submitWebcam();
        } catch (error) {
            setStatus(error.message);
        }
    });
}

async function bootstrap() {
    registerEvents();
    connectRealtimeSocket();
    await refreshJobs();
    setInterval(async () => {
        try {
            await refreshJobs();
        } catch (error) {
            setStatus(error.message);
        }
    }, 3000);
}

bootstrap();
