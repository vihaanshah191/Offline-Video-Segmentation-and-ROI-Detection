# Installation Guide

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ (3.12 recommended) | Backend runtime. |
| Node.js | 20+ (22 recommended) | Frontend build. |
| FFmpeg | any recent | Fast clip cutting (OpenCV fallback exists). |
| Docker | 24+ | Optional, for the containerised stack. |

Check FFmpeg is available:

```bash
ffmpeg -version
```

On Debian/Ubuntu: `sudo apt-get install -y ffmpeg`.
On macOS: `brew install ffmpeg`.

---

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt    # runtime deps (includes Ultralytics/torch)
# or, for a lighter install without object detection:
#   pip install fastapi "uvicorn[standard]" python-multipart pydantic \
#     pydantic-settings SQLAlchemy opencv-python-headless numpy reportlab

cp .env.example .env               # adjust settings if desired
uvicorn app.main:app --reload --port 8000
```

The API is now on <http://localhost:8000> with interactive docs at `/docs`.

### Object detection weights

The first analysis with object detection enabled will download the YOLOv11
`yolo11n.pt` weights automatically (needs internet once). To pre-download:

```bash
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
```

If weights or `ultralytics` cannot be loaded, object detection disables itself
and the rest of the pipeline continues unaffected.

---

## Frontend

```bash
cd frontend
npm install
cp .env.example .env               # optional
npm run dev                        # http://localhost:5173
```

The dev server proxies `/api` and `/storage` to the backend
(`VITE_PROXY_TARGET`, default `http://localhost:8000`).

Production build:

```bash
npm run build      # outputs to frontend/dist
npm run preview    # preview the production build
```

---

## Verifying the install

```bash
# Backend tests
cd backend && pip install -r requirements-dev.txt && pytest

# Generate and analyse a sample video end-to-end
python ../scripts/generate_sample_video.py ../sample_data/sample_exam_hall.mp4
```

Then open the dashboard, upload the sample, and click **Analyze**.
