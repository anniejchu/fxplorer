# AGENTS.md - fxplorer

## Project Shape

- Python backend/package plus Svelte/Vite frontend.
- Python import package is `fxplorer/`; Flask API entrypoint is `backend.py`.
- Frontend lives in `frontend/` and uses Svelte, Vite, and Tone.js.
- Generated/local data directories include `_outputs/`, `uploads/`, `tmp_configs/`, `pretrained/`, `build/`, `frontend/dist/`, and `frontend/node_modules/`.

## Setup

- Python 3.10 CPython is expected.
- Install Python deps with `python -m pip install -r requirements.txt`.
- Install editable package with `python -m pip install -e .`.
- Install frontend deps with `cd frontend && npm install`.

## Run Commands

- Backend: `python -m backend`
- Backend with data: `python -m backend --run_dir <path> --dry assets/salsa_piano.wav`
- Frontend dev: `cd frontend && VITE_API_URL=http://127.0.0.1:5000/api npm run dev -- --host 127.0.0.1 --port 5173`
- Frontend build: `cd frontend && npm run build`

## Pipeline Commands

- Generate: `python -m fxplorer.pipeline.1_generate_samples fxplorer/configs/examples/random_chain.yaml`
- Embed: `python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder clap|afxrep`
- Reduce: `python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --embedder clap|afxrep --method pca`

## Verification

- No formal test/lint/typecheck config is currently present.
- Safe checks: `git status --short`, `python -m compileall -q backend.py fxplorer`, and `cd frontend && npm run build`.
- Avoid running full backend/pipeline casually: they may load/download large ML models and write output dirs.

## Repo Notes

- The repo should be named `fxplorer`; the import package is also `fxplorer`.
- Keep generated artifacts out of commits.
- Do not install system packages; FFmpeg is a documented external/system dependency.
