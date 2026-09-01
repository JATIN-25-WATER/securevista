# Contributing to SecureVista

## Setup

```bash
git clone <repo-url>
cd securevista
cp .env.example .env
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Place test videos in the repo root (not committed): `test.mp4`, `test1.mp4`, `test3.mp4`.

## Branch workflow

1. Create a feature branch from `main`: `git checkout -b feature/your-change`
2. Run tests before opening a PR: `pytest tests/ -v`
3. Open a pull request against `main`
4. Request review from a teammate; do not push directly to `main` for shared features

## Phase ownership (current plan)

| Phase | Scope |
|---|---|
| 1 | Foundation — DB, auth, Docker ✅ |
| 2 | Video pipeline |
| 3 | Detection behaviours |
| 4 | Incident engine |
| 5 | React UI |
| 6 | Evidence and audit |

## Secrets

Never commit `.env`, database files, or evidence clips. Use `.env.example` for templates only.
