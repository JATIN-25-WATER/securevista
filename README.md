# SecureVista

AI-augmented campus security surveillance system. Detects behavioural events (loitering, restricted zone entry, after-hours presence) using video feeds. Generates structured incidents. Supports a human operator response workflow.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLite, SQLAlchemy, Alembic, JWT |
| Video / Detection | OpenCV, YOLOv8n (person class 0 only) |
| Frontend | React 18 + Vite, Tailwind CSS |
| Infra | Docker + docker-compose |

## Quick Start

```bash
# 1. Copy env template
cp .env.example .env
# Edit JWT_SECRET in .env

# 2. Start everything
docker compose up --build

# Backend API: http://localhost:8000
# Frontend:    http://localhost:3000
# API docs:    http://localhost:8000/docs
```

## Default Credentials (development only)

| Username | Password | Role |
|---|---|---|
| admin | admin123 | admin |
| operator | op123 | operator |
| responder | resp123 | responder |

> **Change all passwords before any deployment.**

## Development (without Docker)

```bash
# Create and activate virtualenv
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # Linux/Mac

# Install deps
pip install -r requirements.txt

# Run backend
uvicorn backend.main:app --reload --port 8000

# Run tests
pytest tests/ -v
```

## Project Structure

```
backend/          FastAPI app, DB models, detection engine
frontend/         React + Vite UI (5 views)
modules/          Video analysis modules (kept from original)
tests/            pytest test suite
docs/             Model passport, scoring formula
docker-compose.yml
Dockerfile.backend
Dockerfile.frontend
requirements.txt
```

## Build Phases

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Done | DB schema, FastAPI skeleton, JWT auth, Docker |
| 2 | 🔲 Next | Multi-source video pipeline (VideoSource, SourceManager) |
| 3 | 🔲 | Detection behaviours (zone entry, after-hours, loitering) |
| 4 | 🔲 | Incident engine (scoring, dedup, lifecycle state machine) |
| 5 | 🔲 | UI — 5 views (React + Tailwind) |
| 6 | 🔲 | Evidence packaging and hash-chained audit log |

## Privacy & Governance

- Detects **person class only** (COCO class 0). No face recognition, no identity matching.
- All alerts are human-reviewed. No automated enforcement.
- See `docs/model_passport.md` for full model governance documentation.
