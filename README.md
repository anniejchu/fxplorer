<h1 align="center">FXplorer</h1>

This repo provides a web interface for exploring sonic variations of an input sound in a 2D space. Given a dry input, the system generates N audio FX variants, embeds them using LAION-CLAP or AFx-Rep models, projects them to 2D, and lets users audition, search semantically, interpolate between two variants, edit, and export the results live in the browser.

## FXplorer: A Map-Based Interface for Exploratory Audio Effect Design
Read the paper [here](https://anniejchu.github.io/fxplorer/)! Accepted to **NIME 2026**.

## Pipeline Overview

Three-stage offline pipeline --> Flask backend --> Svelte/Tone.js frontend.

1. **Generate** — Pedalboard renders FX variants from a dry source (13+ effect types, chain combos, VST support)
2. **Embed** — LAION-CLAP (text+audio) or AFx-Rep (FX-specific) embeddings
3. **Reduce** — PCA or UMAP projects to 2D coordinates for visualization

The frontend streams audio via Tone.js (no re-renders from server), supports text and audio similarity search, perceptual parameter interpolation, and live FX editing with edit-ghost projection back into 2D space.

See [ARCHITECTURE.md](ARCHITECTURE.md) for implementation details and [USAGE.md](USAGE.md) for interaction guide and keyboard shortcuts.

## Requirements

- Python 3.10 (via cpython)
- Node.js 18, 20, or 22+ (tested with Node.js 20.19.0)
- npm 8+ (tested with npm 10.8.2, included with Node.js)
- FFmpeg 4-8, installed with conda or your system package manager
- Embedding Models: LAION-CLAP and `st-ito` (installed automatically via `requirements.txt`)

## Setup

```bash
git clone https://github.com/anniejchu/fxplorer.git
cd fxplorer
conda create -y -n fxplorer -c conda-forge "python=3.10.*=*_cpython" pip "ffmpeg>=4,<9"
conda activate fxplorer
python -c "import platform; assert platform.python_implementation() == 'CPython'"
python -m pip install --src "$CONDA_PREFIX/src" -r requirements.txt
python -m pip install -e .
```

Install the frontend:

```bash
cd frontend
npm ci
cd ..
```

Model weights download into `pretrained/` on first use.

## Quick Start

Start the backend in one terminal:

```bash
conda activate fxplorer
cd fxplorer
python -m backend
```

Start the frontend in a second terminal:

```bash
cd fxplorer/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://127.0.0.1:5173` when the browser is on the same machine.

On first run, backend may take a few minutes to set up/download models, app will open when API is ready.

Use the Upload panel to generate a variant
population (or attach the backend to an existing run with `--run_dir <path>`).

## Offline Pipeline

Example configs are in `fxplorer/configs/examples/` (`random_chain.yaml`, `eq6_default.yaml`, `manual.yaml`, `perceptual_groups.yaml`, `sweep.yaml`). Sampling can be guided by perceptual profiles (bounded ranges for musically meaningful sounds) or fully random, controlled per-run via `profile_random_ratio` in the config.

```bash
python -m fxplorer.pipeline.1_generate_samples fxplorer/configs/examples/random_chain.yaml
python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder clap
python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder afxrep
python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --embedder clap --method pca
python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --embedder afxrep --method pca
```

Outputs write to `_outputs/<experiment>_<timestamp>_<id>/`.

## Key Dependencies

- **LAION-CLAP** — Wu et al., "Large-Scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation," ICASSP 2023.
- **AFx-Rep / st-ito** — Steinmetz et al., "ST-ITO: Controlling audio effects for style transfer
with inference-time optimization," ISMIR 2024. [arXiv:2410.21233](https://arxiv.org/abs/2410.21233)
- **Pedalboard** — Spotify. [github.com/spotify/pedalboard](https://github.com/spotify/pedalboard)
- **Tone.js** — Web Audio framework for browser-side FX playback.

## Cite this
```bibtex
@inproceedings{chu2026fxplorer,
    title= {FXplorer: A Map-Based Interface for Exploratory Audio Effect Design}, 
    author= {Annie Chu and Jason Brent Smith and Bryan Pardo},
    booktitle = {Proceedings of the International Conference on New Interfaces for Musical Expression},
    year = {2026},
}
```
