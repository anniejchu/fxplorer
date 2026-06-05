"""Flask API backend for FXplorer.

Uses existing 3-stage pipeline as subprocesses:

  1) 1_generate_samples.py   (sample generation via pedalboard / FXChainGenerator)
  2) 2_embed_samples.py      (CLAP / AFx-Rep embeddings)
  3) 3_reduce_embeddings.py  (PCA  --> 2D coords.json)

Core capabilities:
- Runtime upload of a new dry source and pipeline recompute
- Runtime choice of FX-chain config (via YAML presets)
- Creation of a sample population (audio + manifest + embeddings + PCA coords)
- Text search (CLAP) and audio/ref search (AFx-Rep) over generated samples
- Ghost point projection (render edited params → embed → project to 2D)

The frontend (Tone.js / WebAudio) receives parameter sets and does real-time FX.

Typical startup:
    python -m backend \
        --run_dir _outputs/simple_random_cloud_20251118_160737_7253ac \ #optional
        --dry assets/salsa_piano.wav \ #optional

Then, at runtime optionally call /api/session/run_pipeline to generate a new run from an uploaded dry source + YAML config.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import torch
import torchaudio
import yaml
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from fxplorer.helper import get_clap_model, ensure_afxrep_checkpoint
from fxplorer.constants import (
    REPO_ROOT,
    OUTPUT_DIR_AFX,
    UPLOADS_DIR,
    TMP_CONFIG_DIR,
    AFX_REP_CKPT,
)
from fxplorer.applyfx.fx_generator import FXChainGenerator
from st_ito.utils import load_param_model, get_param_embeds
from audiotools import AudioSignal

app = Flask(__name__)
CORS(app)


# Paths / config presets

# Repository root
AFX_ROOT = REPO_ROOT

CONFIG_PRESETS = {
    # main sample-generation config
    "random_chain": {
        "path": AFX_ROOT / "fxplorer" / "configs" / "examples" / "random_chain.yaml",
        "label": "Random FX chains",
        "description": "Randomized 1-3 effect chains drawn from EQ, chorus, compressor, distortion, reverb.",
    },
    "eq6_default": {
        "path": AFX_ROOT / "fxplorer" / "configs" / "examples" / "eq6_default.yaml",
        "label": "EQ-6 random + sweeps (≈100 samples)",
        "description": "EQ-only random variants plus two sweeps to land near 100 outputs.",
    },
    "manual": {
        "path": AFX_ROOT / "fxplorer" / "configs" / "examples" / "manual.yaml",
        "label": "Manual FX recipes",
        "description": "Deterministic chains defined in the YAML with any parameter overrides applied.",
    },
    "sweep": {
        "path": AFX_ROOT / "fxplorer" / "configs" / "examples" / "sweep.yaml",
        "label": "Parameter sweeps",
        "description": "Sweeps a single parameter over a range of values for a fixed chain.",
    },
    "perceptual_groups": {
        "path": AFX_ROOT / "fxplorer" / "configs" / "examples" / "perceptual_groups.yaml",
        "label": "Perceptual groups",
        "description": "Seven macro categories (clean, bright, dark, space, motion, grit, transient).",
    },
}

UPLOAD_CACHE_PATH = UPLOADS_DIR / "upload_cache.json"
UPLOADS_DIR.mkdir(exist_ok=True, parents=True)
TMP_CONFIG_DIR.mkdir(exist_ok=True, parents=True)


# Global state (current active run)

RUN_DIR: Path | None = None
MANIFEST: List[Dict[str, Any]] | None = None

AVAILABLE_MODES: set[str] = set()
COORDS: Dict[str, List[Dict[str, Any]]] = {}
EMBEDDINGS: Dict[str, np.ndarray] = {}
PCA_SCALERS: Dict[str, Any] = {}
PCA_REDUCERS: Dict[str, Any] = {}
COORDS_MIN: Dict[str, np.ndarray] = {}
COORDS_SPAN: Dict[str, np.ndarray] = {}
PARAMS_LIST: List[Dict[str, Any]] | None = None

CLAP_MODEL = None
AFX_REP_MODEL = None
DRY_AUDIO_PATH: str | None = None
DEFAULT_MODE: str = "afxrep"
REDUCTION_METHOD: str = "pca"

FX_GENERATOR: FXChainGenerator | None = None
FX_GENERATOR_DRY: str | None = None


# Utility: run pipeline scripts via subprocess

def _run_module(mod_name: str, args: List[str]):
    """Helper to run `python -m <mod_name> args...`."""
    cmd = [sys.executable, "-m", mod_name] + args
    print(">>", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def _find_latest_run_dir() -> Path:
    """
    Use OUTPUT_DIR_AFX to find the most recently created run directory.
    (This matches how 1_generate_samples.py makes run dirs.)
    """
    root = Path(OUTPUT_DIR_AFX)
    candidates = [d for d in root.iterdir() if d.is_dir()]
    if not candidates:
        raise RuntimeError(f"No run directories found under {root}")
    latest = max(candidates, key=lambda d: d.stat().st_mtime)
    print(f"Latest run_dir inferred as: {latest}")
    return latest


def _make_temp_config(
    base_cfg_path: Path,
    dry_path: Path,
    experiment_name: str | None,
    target_samples: int | None = None,
    allowed_fx: list[str] | None = None,
    manual_chains_override: Dict[str, Any] | None = None,
    include_dry: bool = False,
) -> Path:
    """
    Load a YAML config, override audio.dry_audio_path and experiment_name,
    and write a temp YAML for this session.
    """
    with open(base_cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Basic overrides; you can add more knobs as you like
    cfg.setdefault("audio", {})
    cfg["audio"]["dry_audio_path"] = str(dry_path)

    if experiment_name:
        cfg["experiment_name"] = experiment_name
    else:
        cfg.setdefault("experiment_name", "run")

    if manual_chains_override is not None:
        cfg["manual_chains"] = manual_chains_override
        cfg["random_chains"] = {}
        cfg["param_sweeps"] = {}
        sg = cfg.setdefault("sample_generation", {})
        sg.setdefault("num_samples_per_manual_chain", 1)
        sg["num_samples_per_random_chain"] = 0
        sg["include_dry"] = bool(include_dry)
    else:
        # Optionally bump random sample count to hit a target (roughly)
        if target_samples and target_samples > 0:
            sg = cfg.setdefault("sample_generation", {})
            manual_cfg = cfg.get("manual_chains", {}) or {}
            sweep_cfg = cfg.get("param_sweeps", {}) or {}
            n_manual = sg.get("num_samples_per_manual_chain", 0)
            manual_total = len(manual_cfg) * n_manual
            sweep_total = sum(len(entry.get("values", [])) for entry in sweep_cfg.values())

            remaining = max(target_samples - manual_total - sweep_total, 1)
            num_random_chains = max(len(cfg.get("random_chains", {})), 1)
            per_chain = max(1, math.ceil(remaining / num_random_chains))
            sg["num_samples_per_random_chain"] = per_chain
            print(f"Config target_samples={target_samples}; num_samples_per_random_chain={per_chain}")

        # Optional override of allowed FX modules in random chains
        if allowed_fx:
            random_cfg = cfg.get("random_chains", {}) or {}
            for rc_name, entry in random_cfg.items():
                orig = entry.get("allowed_effect_types", [])
                entry["allowed_effect_types"] = [fx for fx in allowed_fx if (not orig or fx in orig)] or allowed_fx
                # If user picked only 1 or 2 FX, clamp chain complexity accordingly
                if len(allowed_fx) == 1:
                    entry["chain_complexity"] = 1
                elif len(allowed_fx) == 2:
                    entry["chain_complexity"] = min(entry.get("chain_complexity", 2), 2)
            cfg["random_chains"] = random_cfg

    session_id = uuid.uuid4().hex[:8]
    tmp_cfg_path = TMP_CONFIG_DIR / f"{cfg['experiment_name']}_{session_id}.yaml"
    with open(tmp_cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    print(f"Temp config written to: {tmp_cfg_path}")
    return tmp_cfg_path


def _safe_json_loads(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _generate_combinations(fx_list: List[str]) -> List[List[str]]:
    if not fx_list:
        return []
    combos = []
    n = len(fx_list)
    for i in range(1, 1 << n):
        combo = []
        for j in range(n):
            if i & (1 << j):
                combo.append(fx_list[j])
        combos.append(combo)
    combos.sort(key=len, reverse=True)
    return combos


def _build_manual_chains_from_selection(
    combinations: List[List[str]],
    sample_counts: Dict[str, Any],
    default_count: int = 20,
) -> Dict[str, Any]:
    manual = {}
    for idx, combo in enumerate(combinations):
        key = ",".join(combo)
        raw_count = sample_counts.get(key, default_count)
        try:
            count = int(raw_count)
        except Exception:
            count = default_count
        if count <= 0:
            continue
        safe_parts = [part.replace(":", "-") for part in combo]
        name = f"combo_{idx + 1}_{'__'.join(safe_parts)}"
        manual[name] = {
            "chain": combo,
            "description": f"custom combo: {key}",
            "num_samples": count,
            "apply_rand_params": True,
        }
    return manual


def _normalize_custom_spec(
    exploration_mode: str | None,
    selected_fx: List[str] | None,
    combinations: List[List[str]] | None,
    sample_counts: Dict[str, Any] | None,
) -> str | None:
    if not sample_counts:
        return None
    payload = {
        "exploration_mode": exploration_mode,
        "selected_fx": selected_fx or [],
        "combinations": combinations or [],
        "sample_counts": sample_counts,
    }
    return json.dumps(payload, sort_keys=True)


def run_full_pipeline_from_upload(
    dry_audio_path: Path,
    config_id: str = "random_chain",
    embed_modes: List[str] | None = None,
    target_samples: int | None = None,
    allowed_fx: list[str] | None = None,
    reduction_method: str = "pca",
    manual_chains_override: Dict[str, Any] | None = None,
    include_dry: bool = False,
) -> Path:
    """
    Orchestrate in-memory 3-stage pipeline for a new dry source.

    1) 1_generate_samples.py   → creates manifest_inmem.pkl with audio arrays
    2) 2_embed_samples.py      → adds embeddings to manifest (in-memory)
    3) 3_reduce_embeddings.py  → computes reduction coords from in-memory embeddings

    Returns the new run_dir.
    """
    if embed_modes is None:
        embed_modes = ["afxrep", "clap"]

    if config_id not in CONFIG_PRESETS:
        raise ValueError(f"Unknown config_id '{config_id}'. "
                         f"Available: {sorted(CONFIG_PRESETS)}")

    base_entry = CONFIG_PRESETS[config_id]
    base_cfg = base_entry["path"]
    if not base_cfg.exists():
        raise FileNotFoundError(f"Base config not found: {base_cfg}")

    # 1) Create temp config with overridden dry path
    temp_cfg = _make_temp_config(
        base_cfg,
        dry_audio_path,
        experiment_name=config_id,
        target_samples=target_samples,
        allowed_fx=allowed_fx,
        manual_chains_override=manual_chains_override,
        include_dry=include_dry,
    )

    print("\nStage 1: Generate samples (in-memory)")
    # 2) Run sample generation → creates manifest_inmem.pkl
    _run_module("fxplorer.pipeline.1_generate_samples", [str(temp_cfg)])

    # 3) Infer run_dir
    run_dir = _find_latest_run_dir()

    # 4) Embeddings for each mode (updates manifest_inmem.pkl)
    for mode in embed_modes:
        print(f"\nStage 2: Compute {mode.upper()} embeddings (in-memory)")
        _run_module(
            "fxplorer.pipeline.2_embed_samples",
            [str(run_dir), "--embedder", mode],
        )

    # 5) Reduction for each mode (reads from manifest_inmem.pkl)
    for mode in embed_modes:
        print(f"\nStage 3: {reduction_method.upper()} reduction for {mode.upper()} (in-memory)")
        _run_module(
            "fxplorer.pipeline.3_reduce_embeddings",
            [str(run_dir), "--method", reduction_method, "--embedder", mode],
        )

    print("\nIn-memory pipeline complete.")
    return run_dir


def _load_upload_cache() -> Dict[str, Any]:
    if not UPLOAD_CACHE_PATH.exists():
        return {}
    try:
        with open(UPLOAD_CACHE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_upload_cache(cache: Dict[str, Any]):
    try:
        with open(UPLOAD_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as err:
        print(f"<< Warning: failed to write upload cache: {err}")


# Loading existing run (used on startup & after new pipeline run)

def _load_manifest(run_dir: Path) -> List[Dict[str, Any]]:
    """Load manifest - prefer in-memory pickle, fall back to JSON"""
    m_inmem = run_dir / "manifests" / "manifest_inmem.pkl"
    m1 = run_dir / "manifests" / "manifest_with_embeddings.json"
    m2 = run_dir / "manifests" / "manifest.json"

    if m_inmem.exists():
        print(f"Loading in-memory manifest: {m_inmem}")
        with open(m_inmem, "rb") as f:
            return pickle.load(f)
    else:
        # Fall back to JSON (old format)
        manifest_path = m1 if m1.exists() else m2
        with open(manifest_path, "r") as f:
            return json.load(f)


def _try_load_mode(run_dir: Path, mode: str, method: str) -> bool:
    """
    Load coords.json, PCA model, coords_min/span, and embeddings for a given mode.
    Returns True if successful.
    """
    global COORDS, EMBEDDINGS, PCA_SCALERS, PCA_REDUCERS, PARAMS_LIST, MANIFEST
    global COORDS_MIN, COORDS_SPAN

    base = run_dir / method / mode

    coords_path = base / "coords.json"
    model_path = base / f"{method}_model.pkl"
    coords_min_path = base / "coords_min.npy"
    coords_span_path = base / "coords_span.npy"

    if not coords_path.exists() or not model_path.exists():
        print(f"<<< Skipping mode '{mode}': {method.upper()} outputs not found in {base}.")
        return False

    with open(coords_path, "r") as f:
        COORDS[mode] = json.load(f)

    if coords_min_path.exists() and coords_span_path.exists():
        COORDS_MIN[mode] = np.load(coords_min_path)
        COORDS_SPAN[mode] = np.load(coords_span_path)
    else:
        xs = np.array([p["x"] for p in COORDS[mode]], dtype=np.float32)
        ys = np.array([p["y"] for p in COORDS[mode]], dtype=np.float32)
        COORDS_MIN[mode] = np.array([xs.min(), ys.min()], dtype=np.float32)
        COORDS_SPAN[mode] = np.array(
            [max(xs.max() - xs.min(), 1e-6), max(ys.max() - ys.min(), 1e-6)],
            dtype=np.float32,
        )

    # load PCA scaler/model
    with open(model_path, "rb") as f:
        model = pickle.load(f)
        PCA_SCALERS[mode] = model["scaler"]
        PCA_REDUCERS[mode] = model["reducer"]

    # embeddings from manifest
    embeddings = []
    params_list = []

    for item in MANIFEST:
        emb_info = item.get("embeddings", {}).get(mode)
        if emb_info is None:
            print(f"<< Manifest entry missing embeddings for mode '{mode}', aborting this mode.")
            return False

        # Try to get embedding from memory first (new format)
        if "embedding" in emb_info:
            emb = emb_info["embedding"]
        # Fall back to loading from file (old format)
        elif "embedding_path" in emb_info:
            emb_path = Path(emb_info["embedding_path"])
            if not emb_path.exists():
                print(f"<< Embedding file missing for mode '{mode}': {emb_path}")
                return False
            emb = np.load(emb_path)
        else:
            print(f"<< Embedding info missing both 'embedding' and 'embedding_path' for mode '{mode}'")
            return False

        embeddings.append(emb)
        params_list.append(item["params"])

    EMBEDDINGS[mode] = np.stack(embeddings)
    if PARAMS_LIST is None:
        PARAMS_LIST = params_list

    print(f"Loaded mode '{mode}': {EMBEDDINGS[mode].shape[0]} embeddings")
    return True


def load_run_dir(run_dir: Path, default_mode: str = "afxrep", reduction_method: str = "pca"):
    """
    Populate global state (MANIFEST, EMBEDDINGS, COORDS, PCA models, etc.)
    from an existing pipeline run_dir.
    """
    global RUN_DIR, MANIFEST, AVAILABLE_MODES, DEFAULT_MODE, REDUCTION_METHOD, PARAMS_LIST

    RUN_DIR = run_dir
    MANIFEST = _load_manifest(run_dir)
    AVAILABLE_MODES.clear()

    print(f"Loading run dir: {run_dir}")
    print(f"Entries in manifest: {len(MANIFEST)}")

    methods_to_try = [reduction_method] + [m for m in ("pca", "umap", "tsne") if m != reduction_method]
    loaded = False
    for method in methods_to_try:
        COORDS.clear()
        EMBEDDINGS.clear()
        PCA_SCALERS.clear()
        PCA_REDUCERS.clear()
        COORDS_MIN.clear()
        COORDS_SPAN.clear()
        AVAILABLE_MODES.clear()
        PARAMS_LIST = None

        for mode in ("clap", "afxrep"):
            ok = _try_load_mode(run_dir, mode, method)
            if ok:
                AVAILABLE_MODES.add(mode)

        if AVAILABLE_MODES:
            REDUCTION_METHOD = method
            loaded = True
            break

    if not loaded:
        raise RuntimeError("No valid modes (clap/afxrep) could be loaded.")

    if default_mode in AVAILABLE_MODES:
        DEFAULT_MODE = default_mode
    else:
        DEFAULT_MODE = sorted(AVAILABLE_MODES)[0]
        print(f" >> Requested default_mode '{default_mode}' not available; using '{DEFAULT_MODE}' instead.")

    print(f"Modes available: {sorted(AVAILABLE_MODES)}")
    print(f"Default mode: {DEFAULT_MODE}")


# Embedding helpers (for search)

def load_models():
    """Load CLAP + AFx-Rep once."""
    global CLAP_MODEL, AFX_REP_MODEL

    print("Loading CLAP…")
    CLAP_MODEL = get_clap_model(
        "laion_clap",
        clap_model="music_audioset_epoch_15_esc_90.14.pt",
        audio_model="HTSAT-base",
    )
    print("LAION-CLAP loaded :)")

    print("Loading AFx-Rep…")
    ensure_afxrep_checkpoint()
    AFX_REP_MODEL = load_param_model(
        ckpt_path=str(AFX_REP_CKPT),
        use_gpu=torch.cuda.is_available(),
    )
    print("AFx-Rep loaded :)")


def clap_text_embed(query: str) -> np.ndarray:
    text_emb = CLAP_MODEL.get_text_embeddings([query])
    return text_emb.detach().cpu().numpy().squeeze()


def afxrep_audio_embed_from_filestorage(file_storage) -> np.ndarray:
    """
    Compute AFx-Rep embedding from an uploaded audio file (FileStorage).
    """
    audio, sr = torchaudio.load(file_storage.stream)

    if audio.dim() == 1:
        audio = audio.unsqueeze(0).unsqueeze(0)
    elif audio.dim() == 2:
        audio = audio.unsqueeze(0)

    with torch.no_grad():
        emb_dict = get_param_embeds(audio, AFX_REP_MODEL, sr)

    mid_emb = emb_dict["mid"].cpu().numpy().squeeze()
    side_emb = emb_dict["side"].cpu().numpy().squeeze()
    combined = np.concatenate([mid_emb, side_emb])
    return combined


def _audio_to_signal(audio: np.ndarray, sample_rate: int) -> AudioSignal:
    if audio.ndim == 1:
        audio_cf = audio
    elif audio.ndim == 2:
        if audio.shape[0] <= 4 and audio.shape[1] > 4:
            audio_cf = audio
        else:
            audio_cf = audio.T
    else:
        raise ValueError(f"Audio array must be 1D or 2D, got shape {audio.shape}")
    return AudioSignal(audio_cf, sample_rate)


def _embed_audio_for_mode(mode: str, audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if mode == "clap":
        if CLAP_MODEL is None:
            raise ValueError("CLAP model not loaded")
        sig = _audio_to_signal(audio, sample_rate)
        with torch.no_grad():
            emb = CLAP_MODEL.get_audio_embeddings(sig)
        return emb.detach().cpu().numpy().squeeze()
    if mode == "afxrep":
        if AFX_REP_MODEL is None:
            raise ValueError("AFx-Rep model not loaded")
        if audio.ndim == 1:
            audio_cf = audio[None, :]
        elif audio.ndim == 2:
            audio_cf = audio if audio.shape[0] <= 4 and audio.shape[1] > 4 else audio.T
        else:
            raise ValueError(f"Audio array must be 1D or 2D, got shape {audio.shape}")
        audio_tensor = torch.from_numpy(audio_cf).float().unsqueeze(0)
        with torch.no_grad():
            emb_dict = get_param_embeds(audio_tensor, AFX_REP_MODEL, sample_rate)
        mid_emb = emb_dict["mid"].cpu().numpy().squeeze()
        side_emb = emb_dict["side"].cpu().numpy().squeeze()
        return np.concatenate([mid_emb, side_emb])
    raise ValueError(f"mode '{mode}' not available")


def get_fx_generator() -> FXChainGenerator:
    global FX_GENERATOR, FX_GENERATOR_DRY
    if not DRY_AUDIO_PATH:
        raise ValueError("dry audio not configured")
    if FX_GENERATOR is None or FX_GENERATOR_DRY != DRY_AUDIO_PATH:
        FX_GENERATOR = FXChainGenerator(
            dry_audio_path=DRY_AUDIO_PATH,
            normalize_dry=True,
            target_lufs=-14,
            normalize_output=True,
        )
        FX_GENERATOR_DRY = DRY_AUDIO_PATH
    return FX_GENERATOR


def cosine_search(mode: str, query_emb: np.ndarray, k: int = 10):
    """
    Cosine similarity search in EMBEDDINGS[mode] with query_emb.
    Returns list of {idx, similarity}.
    """
    if mode not in EMBEDDINGS:
        raise ValueError(f"Mode '{mode}' not loaded")

    E = EMBEDDINGS[mode]
    q = query_emb

    q_norm = np.linalg.norm(q) + 1e-8
    E_norm = np.linalg.norm(E, axis=1) + 1e-8
    sims = (E @ q) / (E_norm * q_norm)

    idxs = np.argsort(-sims)
    results = [
        {"idx": int(i), "similarity": float(sims[i])}
        for i in idxs[:k]
    ]
    return results


def project_embedding_to_norm(mode: str, emb: np.ndarray) -> tuple[float, float]:
    """Project a high-D embedding into the mode's normalized 2D space."""
    if mode not in PCA_SCALERS or mode not in PCA_REDUCERS:
        raise ValueError(f"mode '{mode}' missing PCA reducers")

    coords_min = COORDS_MIN[mode]
    coords_span = COORDS_SPAN[mode]
    coords_span_safe = np.where(coords_span == 0, 1.0, coords_span)

    reducer = PCA_REDUCERS.get(mode)
    if reducer is None:
        raise ValueError(f"mode '{mode}' missing reducer")
    if not hasattr(reducer, "transform"):
        raise ValueError(f"mode '{mode}' reducer does not support transform")
    scaler = PCA_SCALERS.get(mode)
    if scaler is not None:
        expected_dim = getattr(scaler, "n_features_in_", None)
        if expected_dim is not None and emb.shape[-1] != expected_dim:
            raise ValueError(
                f"embedding dim {emb.shape[-1]} != expected {expected_dim} for mode '{mode}'"
            )
        Z = scaler.transform(emb.reshape(1, -1))
    else:
        Z = emb.reshape(1, -1)
    XY = reducer.transform(Z).squeeze()
    coords_norm = (XY - coords_min) / coords_span_safe
    x_norm = float(coords_norm[0])
    y_norm = float(coords_norm[1])
    return x_norm, y_norm


# API ROUTES

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "num_samples": len(MANIFEST) if MANIFEST is not None else 0,
        "available_modes": sorted(list(AVAILABLE_MODES)),
        "default_mode": DEFAULT_MODE,
        "run_dir": str(RUN_DIR) if RUN_DIR is not None else None,
    })


@app.route("/api/modes")
def api_modes():
    return jsonify({
        "modes": sorted(list(AVAILABLE_MODES)),
        "default": DEFAULT_MODE,
    })


@app.route("/api/configs")
def api_configs():
    """
    List available YAML configs for generation (FX chain presets, etc.)
    """
    items = []
    for cid, entry in CONFIG_PRESETS.items():
        path = entry["path"]
        items.append({
            "id": cid,
            "path": str(path),
            "exists": path.exists(),
            "label": entry.get("label", cid),
            "description": entry.get("description", ""),
        })
    return jsonify({"configs": items})


@app.route("/api/coords")
def api_coords():
    """
    GET /api/coords?mode=clap or mode=afxrep
    Returns current 2D scatter coords (normalized 0..1).
    """
    mode = request.args.get("mode", DEFAULT_MODE)
    if mode not in AVAILABLE_MODES:
        return jsonify({"error": f"mode '{mode}' not available"}), 400
    return jsonify(COORDS[mode])


@app.route("/api/manifest")
def api_manifest():
    """Return manifest metadata without audio/embedding arrays (not JSON serializable)"""
    if MANIFEST is None:
        return jsonify([])

    def sanitize_json(obj):
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, dict):
            return {k: sanitize_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize_json(v) for v in obj]
        return obj

    # Strip out numpy arrays (audio, embeddings) for JSON serialization
    manifest_json = []
    for item in MANIFEST:
        item_copy = {k: v for k, v in item.items() if k not in ("audio", "embeddings")}
        # Add metadata about what was stripped
        if "audio" in item:
            item_copy["audio_shape"] = list(item["audio"].shape)
            item_copy["audio_dtype"] = str(item["audio"].dtype)
        if "embeddings" in item:
            item_copy["embeddings_info"] = {
                emb_type: {"dim": emb_data["embedding_dim"]}
                for emb_type, emb_data in item["embeddings"].items()
            }
        manifest_json.append(sanitize_json(item_copy))

    return jsonify(manifest_json)


@app.route("/api/sample/<int:idx>")
def api_sample(idx: int):
    """
    GET /api/sample/12?mode=clap
    Returns metadata + params + coords for a sample.
    """
    if MANIFEST is None or idx < 0 or idx >= len(MANIFEST):
        return jsonify({"error": "invalid index"}), 400

    mode = request.args.get("mode", DEFAULT_MODE)
    if mode not in AVAILABLE_MODES:
        return jsonify({"error": f"mode '{mode}' not available"}), 400

    item = MANIFEST[idx]
    coord = COORDS[mode][idx]

    def sanitize_json(obj):
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, dict):
            return {k: sanitize_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize_json(v) for v in obj]
        return obj

    return jsonify(sanitize_json({
        "index": idx,
        "id": item.get("params", {}).get("uuid"),
        "type": item.get("type"),
        "name": item.get("name"),
        "mode": mode,
        "coords": [coord["x"], coord["y"]],
        "params": item["params"].get("plugins", {}),
        "audio_url": f"/api/audio/{idx}",
    }))


@app.route("/api/audio/<int:idx>")
def api_audio(idx: int):
    """Serve audio - generate WAV on-the-fly from in-memory array"""
    if MANIFEST is None or idx < 0 or idx >= len(MANIFEST):
        return jsonify({"error": "invalid index"}), 400

    item = MANIFEST[idx]

    # Check if we have in-memory audio
    if "audio" in item:
        # Generate WAV from in-memory audio array
        import io
        import soundfile as sf

        audio_array = item["audio"]
        sample_rate = item.get("sample_rate", 44100)

        # Ensure samples-first shape for soundfile (samples, channels)
        if hasattr(audio_array, "ndim"):
            if audio_array.ndim == 2 and audio_array.shape[0] <= 4 and audio_array.shape[1] > 4:
                audio_array = audio_array.T
            elif audio_array.ndim == 1:
                audio_array = audio_array[:, None]

        # Create BytesIO buffer
        wav_buffer = io.BytesIO()

        # Write WAV to buffer (soundfile expects channels-last: [samples, channels])
        sf.write(wav_buffer, audio_array, sample_rate, format="WAV", subtype="PCM_16")

        # Seek to beginning
        wav_buffer.seek(0)

        return send_file(
            wav_buffer,
            mimetype="audio/wav",
            as_attachment=False,
            download_name=f"sample_{idx}.wav"
        )

    # Fall back to file path (old format)
    elif "audio_path" in item:
        wav_path = Path(item["audio_path"])
        if not wav_path.exists():
            return jsonify({"error": "file not found"}), 404
        return send_file(wav_path, mimetype="audio/wav")

    else:
        return jsonify({"error": "no audio data available"}), 500


@app.route("/api/dry")
def api_dry():
    if DRY_AUDIO_PATH is None:
        return jsonify({"error": "no dry path configured"}), 500
    return send_file(DRY_AUDIO_PATH, mimetype="audio/wav")


@app.route("/api/dry_info")
def api_dry_info():
    if DRY_AUDIO_PATH is None:
        return jsonify({"error": "no dry path configured"}), 500
    try:
        audio, sample_rate = torchaudio.load(DRY_AUDIO_PATH)
        audio = audio.float()
        peak = float(audio.abs().max().item()) if audio.numel() else 0.0
        rms = float(audio.pow(2).mean().sqrt().item()) if audio.numel() else 0.0
    except Exception as exc:
        return jsonify({"error": f"failed to read dry audio: {exc}"}), 500

    return jsonify({
        "dry_path": str(DRY_AUDIO_PATH),
        "sample_rate": int(sample_rate),
        "rms": rms,
        "peak": peak,
    })


# Unified search (CLAP text + AFx-Rep audio/ref)

@app.route("/api/search", methods=["POST"])
def api_search():
    """
    Unified search endpoint.

    JSON body – CLAP text search or AFx-Rep ref search:

      CLAP:
        {
          "mode": "clap",
          "query": "warm shimmering reverb",
          "k": 15
        }

      AFx-Rep (reference index):
        {
          "mode": "afxrep",
          "ref_idx": 12,
          "k": 10
        }

      AFx-Rep (embedding directly):
        {
          "mode": "afxrep",
          "embedding": [...],
          "k": 10
        }

    Multipart / form – AFx-Rep audio search:

      POST /api/search?mode=afxrep
      Content-Type: multipart/form-data
      fields:
        file: uploaded WAV/MP3/etc.
        k: 10 (optional)
    """

    # Multipart audio upload for AFx-Rep
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        mode = request.args.get("mode", "afxrep")
        if mode != "afxrep":
            return jsonify({"error": "multipart search only supported for mode='afxrep'"}), 400
        if "file" not in request.files:
            return jsonify({"error": "missing file"}), 400
        if "afxrep" not in AVAILABLE_MODES:
            return jsonify({"error": "mode 'afxrep' not available"}), 400

        file = request.files["file"]
        k = int(request.form.get("k", 10))

        try:
            query_emb = afxrep_audio_embed_from_filestorage(file)
            results = cosine_search("afxrep", query_emb, k=k)
            return jsonify({
                "mode": "afxrep",
                "from": "audio_upload",
                "results": results,
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # JSON body
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", DEFAULT_MODE)
    k = int(data.get("k", 10))

    if mode not in AVAILABLE_MODES:
        return jsonify({"error": f"mode '{mode}' not available"}), 400

    if mode == "clap":
        query = data.get("query")
        if not query:
            return jsonify({"error": "missing 'query' for CLAP text search"}), 400
        try:
            text_emb = clap_text_embed(query)
            results = cosine_search("clap", text_emb, k=k)
            return jsonify({
                "mode": "clap",
                "query": query,
                "results": results,
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    if mode == "afxrep":
        if "afxrep" not in AVAILABLE_MODES:
            return jsonify({"error": "mode 'afxrep' not available"}), 400

        ref_idx = data.get("ref_idx")
        emb_list = data.get("embedding")

        if ref_idx is None and emb_list is None:
            return jsonify({"error": "need 'ref_idx' or 'embedding' for afxrep search"}), 400

        try:
            if ref_idx is not None:
                ref_idx = int(ref_idx)
                if ref_idx < 0 or ref_idx >= EMBEDDINGS["afxrep"].shape[0]:
                    return jsonify({"error": "invalid ref_idx"}), 400
                query_emb = EMBEDDINGS["afxrep"][ref_idx]
                src = "ref_idx"
            else:
                query_emb = np.array(emb_list, dtype=np.float32)
                src = "embedding"

            results = cosine_search("afxrep", query_emb, k=k)
            return jsonify({
                "mode": "afxrep",
                "from": src,
                "results": results,
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": f"unhandled mode '{mode}'"}), 400


@app.route("/api/ghost_point", methods=["POST"])
def api_ghost_point():
    """
    Render edited params, embed audio, and project to 2D for accurate ghost point.

    JSON body:
      {
        "mode": "clap" | "afxrep",  # optional, default = DEFAULT_MODE
        "params": { "chain": [...], "plugins": {...}, ... }
      }
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", DEFAULT_MODE)
    params = data.get("params")

    if mode not in AVAILABLE_MODES:
        return jsonify({"error": f"mode '{mode}' not available"}), 400
    if not params:
        return jsonify({"error": "missing 'params'"}), 400
    if "chain" not in params or "plugins" not in params:
        return jsonify({"error": "params must include 'chain' and 'plugins'"}), 400

    try:
        gen = get_fx_generator()
        normalize_output = params.get("normalize_output", None)
        if isinstance(normalize_output, bool):
            audio = gen.render_audio(params, normalize_output=normalize_output)
        else:
            audio = gen.render_audio(params)
        emb = _embed_audio_for_mode(mode, audio, gen.sample_rate)
        x_norm, y_norm = project_embedding_to_norm(mode, emb)
        return jsonify({"mode": mode, "x": float(x_norm), "y": float(y_norm)})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/text_point", methods=["POST"])
def api_text_point():
    """
    Embed free-form text with CLAP and project it into the CLAP 2D space.

    JSON body:
      {
        "text": "warm roomy piano",
        "mode": "clap",
        "k": 5  # optional nearest-neighbor count
      }
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text") or data.get("query")
    mode = data.get("mode", "clap")
    k = int(data.get("k", 5))

    if not text or not text.strip():
        return jsonify({"error": "missing 'text'"}), 400
    text = text.strip()

    if mode != "clap":
        return jsonify({"error": "text projection currently only supports mode='clap'"}), 400
    if mode not in AVAILABLE_MODES:
        return jsonify({"error": f"mode '{mode}' not available"}), 400

    try:
        emb = clap_text_embed(text)
        x_norm, y_norm = project_embedding_to_norm(mode, emb)
        neighbors = cosine_search(mode, emb, k=k) if k > 0 else []

        return jsonify({
            "mode": mode,
            "text": text,
            "coords": {"x": x_norm, "y": y_norm},
            "nearest": neighbors,
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# Session: upload + full pipeline run

@app.route("/api/session/run_pipeline", methods=["POST"])
def api_session_run_pipeline():
    """
    High-level orchestration endpoint:

    Multipart/form-data:
      file: dry audio file (required)
      config_id: one of CONFIG_PRESETS keys (optional; default "random_chain")
      embed_modes: comma-separated list "afxrep,clap" (optional)
      reduction_method: "pca", "umap", or "tsne" (optional; default "pca")
      target_samples: approximate number of samples to generate (optional; default config value)
      allowed_fx: comma-separated list of FX module ids to allow (optional; overrides random_chains.allowed_effect_types)
      exploration_mode: "separate" | "chain" (optional; custom combos mode)
      sample_counts: JSON dict mapping combo keys to counts (optional; custom combos mode)
      selected_fx: JSON list of FX ids (optional; custom combos mode)
      combinations: JSON list of FX-id lists (optional; custom combos mode)

    Steps:
      1) Save dry audio to uploads/
      2) Create temp YAML config with dry path override
      3) Run 1_generate_samples.py
      4) Run 2_embed_samples.py for each embedder
      5) Run 3_reduce_embeddings.py for each embedder (PCA/UMAP)
      6) Reload globals for the new run
    """
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    file = request.files["file"]
    config_id = request.form.get("config_id", "random_chain")
    embed_modes_str = request.form.get("embed_modes", "afxrep,clap")
    embed_modes = [m.strip() for m in embed_modes_str.split(",") if m.strip()]
    embed_modes_norm = sorted(embed_modes)
    reduction_method = request.form.get("reduction_method", "pca").strip().lower()
    target_samples_str = request.form.get("target_samples")
    exploration_mode = request.form.get("exploration_mode")
    sample_counts_raw = request.form.get("sample_counts")
    selected_fx_raw = request.form.get("selected_fx")
    combinations_raw = request.form.get("combinations")
    allowed_fx_str = request.form.get("allowed_fx")
    allowed_fx = [m.strip() for m in allowed_fx_str.split(",") if m.strip()] if allowed_fx_str else None
    allowed_fx_norm = sorted(allowed_fx) if allowed_fx else None
    if reduction_method not in ("pca", "umap", "tsne"):
        return jsonify({"error": "reduction_method must be 'pca', 'umap', or 'tsne'"}), 400

    try:
        target_samples = int(target_samples_str) if target_samples_str else None
    except ValueError:
        return jsonify({"error": "target_samples must be an integer"}), 400

    sample_counts = _safe_json_loads(sample_counts_raw, None)
    selected_fx = _safe_json_loads(selected_fx_raw, None)
    combinations = _safe_json_loads(combinations_raw, None)

    custom_spec = _normalize_custom_spec(exploration_mode, selected_fx, combinations, sample_counts)

    global DRY_AUDIO_PATH

    # Hash uploaded file for dedupe so identical uploads/configs reuse the cached run.
    try:
        file_bytes = file.read()
    except Exception as err:
        return jsonify({"error": f"failed to read uploaded file: {err}"}), 400
    file.stream.seek(0)
    digest = hashlib.sha256(file_bytes).hexdigest()
    upload_cache = _load_upload_cache()
    cached_entry = upload_cache.get(digest)
    if cached_entry:
        # If the exact hash+config combo already ran, skip the expensive pipeline.
        matches_config = (
            cached_entry.get("config_id") == config_id and
            cached_entry.get("embed_modes") == embed_modes_norm and
            cached_entry.get("allowed_fx") == allowed_fx_norm and
            cached_entry.get("target_samples") == target_samples and
            cached_entry.get("reduction_method") == reduction_method and
            cached_entry.get("custom_spec") == custom_spec
        )
        cached_run_dir = Path(cached_entry.get("run_dir", ""))
        cached_dry_path = Path(cached_entry.get("dry_path", ""))
        if matches_config and cached_run_dir.exists() and cached_dry_path.exists():
            DRY_AUDIO_PATH = str(cached_dry_path)
            default_mode = cached_entry.get("default_mode", embed_modes[0] if embed_modes else "afxrep")
            load_run_dir(cached_run_dir, default_mode=default_mode, reduction_method=reduction_method)
            return jsonify({
                "status": "cached",
                "run_dir": str(cached_run_dir),
                "available_modes": sorted(list(AVAILABLE_MODES)),
                "default_mode": DEFAULT_MODE,
                "reduction_method": REDUCTION_METHOD,
                "num_samples": len(MANIFEST),
                "target_samples": target_samples,
                "session_id": cached_entry.get("session_id"),
                "cache_hit": True,
            })

    # Save dry audio
    session_id = uuid.uuid4().hex[:8]
    dry_path = UPLOADS_DIR / f"dry_{session_id}.wav"
    file.save(dry_path)
    DRY_AUDIO_PATH = str(dry_path.resolve())
    print(f"Saved uploaded dry audio to: {dry_path}")

    try:
        manual_chains_override = None
        include_dry = False
        if isinstance(sample_counts, dict):
            combos = combinations
            if not combos:
                if selected_fx:
                    if exploration_mode == "chain":
                        combos = _generate_combinations(selected_fx)
                    else:
                        combos = [[fx] for fx in selected_fx]
                else:
                    combos = [key.split(",") for key in sample_counts.keys() if key]
            if combos:
                manual_chains_override = _build_manual_chains_from_selection(combos, sample_counts)
                include_dry = True

        run_dir = run_full_pipeline_from_upload(
            dry_path,
            config_id=config_id,
            embed_modes=embed_modes,
            target_samples=target_samples,
            allowed_fx=allowed_fx,
            reduction_method=reduction_method,
            manual_chains_override=manual_chains_override,
            include_dry=include_dry,
        )

        # After pipeline, reload this run as current
        load_run_dir(run_dir, default_mode=embed_modes[0] if embed_modes else "afxrep", reduction_method=reduction_method)

        upload_cache[digest] = {
            # Persist enough metadata to skip re-running this exact request later.
            "dry_path": str(dry_path.resolve()),
            "run_dir": str(run_dir),
            "config_id": config_id,
            "embed_modes": embed_modes_norm,
            "allowed_fx": allowed_fx_norm,
            "target_samples": target_samples,
            "reduction_method": reduction_method,
            "custom_spec": custom_spec,
            "default_mode": DEFAULT_MODE,
            "session_id": session_id,
        }
        _save_upload_cache(upload_cache)

        return jsonify({
            "status": "ok",
            "run_dir": str(run_dir),
            "available_modes": sorted(list(AVAILABLE_MODES)),
            "default_mode": DEFAULT_MODE,
            "reduction_method": REDUCTION_METHOD,
            "num_samples": len(MANIFEST),
            "target_samples": target_samples,
            "session_id": session_id,
            "cache_hit": False,
        })
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"pipeline subprocess failed: {e}"}), 500
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# Boot

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", type=str, default=None,
                        help="Optional existing run_dir to attach to; skip to start empty "
                             "and wait for /api/session/run_pipeline uploads.")
    parser.add_argument("--default_mode", type=str, default="afxrep",
                        choices=["clap", "afxrep"],
                        help="Which embedder space to treat as default")
    parser.add_argument("--reduction_method", type=str, default="pca",
                        choices=["pca", "umap", "tsne"],
                        help="Which reduction method to load (pca, umap, or tsne)")
    parser.add_argument("--dry", type=str, default=None,
                        help="Path to dry audio file to serve at /api/dry")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)

    args = parser.parse_args()

    if args.dry:
        DRY_AUDIO_PATH = str(Path(args.dry).expanduser().resolve())

    print("Loading models…")
    load_models()

    if args.run_dir:
        print("Loading initial run…")
        load_run_dir(Path(args.run_dir), default_mode=args.default_mode, reduction_method=args.reduction_method)
    else:
        print("No initial run supplied; awaiting uploads via /api/session/run_pipeline.")

    print(f"API ready at http://{args.host}:{args.port}")
    print(f"Modes: {sorted(AVAILABLE_MODES)} (default={DEFAULT_MODE})")
    if MANIFEST is not None:
        print(f"Samples: {len(MANIFEST)}")
    else:
        print("Samples: <none yet> (generate via upload)")

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
