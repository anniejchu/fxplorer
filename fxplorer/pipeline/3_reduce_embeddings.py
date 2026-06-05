"""
python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --method pca

Loads manifest with embeddings, applies PCA or UMAP, and writes:
 - <method>_embeddings.npy
 - <method>_embeddings_norm.npy
 - <method>_model.pkl
 - coords.json (web-ready list of points)
"""

import json
import pickle
from pathlib import Path
import argparse

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

try:
    # Prefer umap-learn's implementation even if another "umap" module exists.
    try:
        from umap import umap_ as umap_module
    except Exception:
        import umap as umap_module
    UMAP_AVAILABLE = hasattr(umap_module, "UMAP")
except ImportError:
    umap_module = None
    UMAP_AVAILABLE = False
    print("UMAP not installed. Install with: pip install umap-learn")


def load_json(path: Path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


# dimensionality reduction routines
def run_pca(embeddings, dims):
    """Standardized PCA."""
    scaler = StandardScaler()
    Z = scaler.fit_transform(embeddings)

    reducer = PCA(n_components=dims)
    Z_red = reducer.fit_transform(Z)

    explained = np.sum(reducer.explained_variance_ratio_)
    print(f"PCA explained variance ({dims}D): {explained:.3f}")

    return Z_red, scaler, reducer


def run_umap(embeddings, dims, n_neighbors=15, min_dist=0.1):
    """UMAP reduction (nonlinear)."""

    if not UMAP_AVAILABLE:
        raise RuntimeError("UMAP requested but umap-learn is not installed.")

    scaler = StandardScaler()
    Z = scaler.fit_transform(embeddings)

    reducer = umap_module.UMAP(
        n_components=dims,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric="euclidean",
        random_state=42,
    )

    Z_red = reducer.fit_transform(Z)
    print(f"UMAP completed; shape {Z_red.shape}")

    return Z_red, scaler, reducer


def run_tsne(embeddings, dims, perplexity=30.0, learning_rate="auto"):
    """t-SNE reduction (nonlinear)."""
    if dims not in (2, 3):
        raise ValueError("t-SNE supports dims=2 or dims=3")

    reducer = TSNE(
        n_components=dims,
        perplexity=perplexity,
        learning_rate=learning_rate,
        init="pca",
        random_state=42,
    )
    Z_red = reducer.fit_transform(embeddings)
    print(f"t-SNE completed; shape {Z_red.shape}")
    return Z_red, None, reducer


# Run reduction on manifest embeddings (IN MEMORY)
def run_reduction_inmem(manifest: list, method: str = "pca", dims: int = 2, umap_neighbors: int = 15, umap_min_dist: float = 0.1, embedder_type: str = None, tsne_perplexity: float = 30.0):
    """
    Run dimensionality reduction on in-memory embeddings.
    """
    embeddings = []
    entries = []

    for item in manifest:
        # Get embedding from in-memory structure
        if "embeddings" in item:
            # If embedder_type specified, use that one
            if embedder_type and embedder_type in item["embeddings"]:
                emb_info = item["embeddings"][embedder_type]
                emb = emb_info["embedding"]  # Get from memory, not file
            # Otherwise use the first available embedder
            else:
                # Get first available embedder
                emb_info = next(iter(item["embeddings"].values()))
                emb = emb_info["embedding"]  # Get from memory, not file
        # Fall back to old flat structure (backward compatibility)
        elif "embedding" in item:
            emb = np.array(item["embedding"], dtype=np.float32)
        else:
            raise ValueError(f"Manifest entry missing embeddings: {item}")

        embeddings.append(emb)
        entries.append(item)

    embeddings = np.stack(embeddings)
    print(f"Loaded {len(embeddings)} embeddings (dim={embeddings.shape[1]})")

    # Choose method
    method = method.lower()
    if method == "pca":
        coords, scaler, reducer = run_pca(embeddings, dims)

    elif method == "umap":
        coords, scaler, reducer = run_umap(
            embeddings,
            dims=dims,
            n_neighbors=umap_neighbors,
            min_dist=umap_min_dist,
        )
    elif method == "tsne":
        coords, scaler, reducer = run_tsne(
            embeddings,
            dims=dims,
            perplexity=tsne_perplexity,
        )

    else:
        raise ValueError(f"Unknown reduction method: {method}")

    return entries, coords, scaler, reducer, method

def write_outputs(outdir: Path, entries, coords, scaler, reducer, method_name):
    """Save PCA/UMAP/t-SNE outputs to disk for backend to load."""
    outdir.mkdir(parents=True, exist_ok=True)

    # Save raw reduced embeddings
    np.save(outdir / f"{method_name}_embeddings.npy", coords)

    # Save min/span for each axis so a frontend can consistently normalize coords to e.g. [0, 1] across runs.
    coords_min = coords.min(axis=0)
    coords_max = coords.max(axis=0)
    coords_span = coords_max - coords_min

    # Avoid zero-span divisions on degenerate axes
    coords_span_safe = np.where(coords_span == 0, 1.0, coords_span)

    np.save(outdir / "coords_min.npy", coords_min)
    np.save(outdir / "coords_span.npy", coords_span_safe)

    # Also save a convenience normalized copy (0..1) of the reduced embeddings
    coords_norm = (coords - coords_min) / coords_span_safe
    np.save(outdir / f"{method_name}_embeddings_norm.npy", coords_norm)

    # Save the scaler + reducer model
    with open(outdir / f"{method_name}_model.pkl", "wb") as f:
        pickle.dump({"scaler": scaler, "reducer": reducer}, f)

    # Prepare JSON for web use (using normed coords)
    web_list = []
    for i, (item, (x, y)) in enumerate(zip(entries, coords_norm)):
        item_id = item.get("params", {}).get("uuid")
        web_list.append({
            "id": item_id,
            "index": i,  # Important for backend to retrieve audio
            "type": item.get("type"),
            "name": item.get("name"),
            "x": float(x),
            "y": float(y),
        })

    save_json(outdir / "coords.json", web_list)
    print(f"Saved coords.json ({len(web_list)} points)")

def main():
    """
    Load in-memory manifest with embeddings, run PCA/UMAP, save coords + models.
    """
    parser = argparse.ArgumentParser("Reduce embeddings (PCA or UMAP) - in-memory")
    parser.add_argument("run_dir", type=str, help="Path to run directory with manifest_inmem.pkl")
    parser.add_argument("--method", type=str, default="tsne",
                        choices=["pca", "umap", "tsne"], help="Reduction method")
    parser.add_argument("--embedder", type=str, default=None,
                        choices=["clap", "afxrep"], help="Which embedder to use (if multiple available)")
    parser.add_argument("--dims", type=int, default=2)
    parser.add_argument("--neighbors", type=int, default=15,
                        help="UMAP: number of neighbors")
    parser.add_argument("--min_dist", type=float, default=0.1,
                        help="UMAP: minimum distance")
    parser.add_argument("--perplexity", type=float, default=30.0,
                        help="t-SNE: perplexity (ignored for PCA/UMAP)")

    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifests" / "manifest_inmem.pkl"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Could not find in-memory manifest: {manifest_path}")

    # Load manifest with embeddings
    print(f"Loading in-memory manifest: {manifest_path}")
    with open(manifest_path, "rb") as f:
        manifest = pickle.load(f)

    print(f"Loaded {len(manifest)} samples")

    # Output directory: method/embedder_type
    embedder_dir = args.embedder or "default"
    outdir = run_dir / args.method / embedder_dir

    entries, coords, scaler, reducer, method_name = run_reduction_inmem(
        manifest,
        method=args.method,
        dims=args.dims,
        umap_neighbors=args.neighbors,
        umap_min_dist=args.min_dist,
        embedder_type=args.embedder,
        tsne_perplexity=args.perplexity,
    )

    write_outputs(outdir, entries, coords, scaler, reducer, method_name)

    print(f"\n{args.method.upper()} completed. Outputs stored in {outdir}")


if __name__ == "__main__":
    main()
