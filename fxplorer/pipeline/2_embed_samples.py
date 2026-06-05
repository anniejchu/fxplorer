"""
Load in-memory manifest with audio arrays, run embeddings (CLAP or AFX-Rep),
and update manifest with embeddings (all in-memory).

python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder afxrep
"""

from pathlib import Path
import json
import argparse
import numpy as np
from tqdm import tqdm
import torch
import os
import torchaudio
import pickle
from audiotools import AudioSignal

from fxplorer.helper import get_clap_model, preprocess_audio, ensure_afxrep_checkpoint
from st_ito.utils import load_param_model, get_param_embeds
from fxplorer.constants import AFX_REP_CKPT


# Load Embedder Models
def load_embedder(embedder_type: str):
    """
    Returns an object with a .encode(audio) method
    """

    if embedder_type == "clap":
        print("Loading CLAP model...")
        clap = get_clap_model(
            "laion_clap",
            clap_model="music_audioset_epoch_15_esc_90.14.pt",
            audio_model="HTSAT-base",
        )
        print("CLAP loaded.")

        class CLAPWrapper:
            def _to_audio_signal(self, audio_array: np.ndarray, sample_rate: int) -> AudioSignal:
                """Build AudioSignal in channels-first format without extra normalization."""
                if audio_array.ndim == 1:
                    audio_cf = audio_array
                elif audio_array.ndim == 2:
                    # Heuristic: if first dim looks like channels, keep it
                    if audio_array.shape[0] <= 4 and audio_array.shape[1] > 4:
                        audio_cf = audio_array
                    else:
                        # Assume samples-first; convert to channels-first
                        audio_cf = audio_array.T
                else:
                    raise ValueError(f"Audio array must be 1D or 2D, got shape {audio_array.shape}")
                return AudioSignal(audio_cf, sample_rate)

            def encode(self, audio_array, sample_rate):
                """Encode single audio array"""
                if isinstance(audio_array, np.ndarray):
                    sig = self._to_audio_signal(audio_array, sample_rate)
                else:
                    sig = preprocess_audio(audio_array)

                with torch.no_grad():
                    emb = clap.get_audio_embeddings(sig)
                return emb.cpu().numpy().squeeze()

            def encode_batch(self, audio_arrays, sample_rates):
                """Encode batch of audio arrays (much faster!)"""
                # AudioSignal batch cannot mix sample rates; fall back if needed.
                if len(set(sample_rates)) != 1:
                    return [self.encode(a, sr) for a, sr in zip(audio_arrays, sample_rates)]

                # Preprocess each signal individually (handles resampling)
                # Then batch the preprocessed tensors for model inference
                preprocessed_batch = []
                for audio_array in audio_arrays:
                    # Create AudioSignal from array
                    sig = self._to_audio_signal(audio_array, sample_rates[0])

                    # Preprocess (resample to 48kHz, convert to mono)
                    sig_preprocessed = clap.preprocess_audio(sig)

                    # Extract tensor [batch=1, channels=1, samples] -> squeeze to [samples]
                    preprocessed_batch.append(sig_preprocessed.samples.squeeze(1).squeeze(0))

                # Stack into batch [batch_size, samples]
                batch_tensor = torch.stack(preprocessed_batch, dim=0)

                # Run model directly on preprocessed batch (bypass get_audio_embeddings)
                with torch.no_grad():
                    batch_embs = clap.model.get_audio_embedding_from_data(x=batch_tensor, use_tensor=True)

                return [emb.cpu().numpy() for emb in batch_embs]

        return CLAPWrapper()

    elif embedder_type == "afxrep":
        print("Loading AFX-Rep model...")
        ensure_afxrep_checkpoint()
        force_cpu = os.getenv("AFXREP_FORCE_CPU", "0").strip().lower() in ("1", "true", "yes")
        use_gpu = torch.cuda.is_available() and not force_cpu
        try:
            model = load_param_model(
                ckpt_path=str(AFX_REP_CKPT),
                use_gpu=use_gpu,
            )
        except RuntimeError as err:
            if use_gpu and "out of memory" in str(err).lower():
                print("Warning: AFX-Rep CUDA OOM; retrying on CPU.")
                model = load_param_model(
                    ckpt_path=str(AFX_REP_CKPT),
                    use_gpu=False,
                )
            else:
                raise
        print("AFX-Rep loaded.")

        class AFXWrapper:
            def _to_channels_first(self, audio_array: np.ndarray) -> torch.Tensor:
                """Return audio as torch.Tensor [channels, samples]."""
                if audio_array.ndim == 1:
                    audio_cf = audio_array[None, :]
                elif audio_array.ndim == 2:
                    # Heuristic: if first dim looks like channels, keep it
                    if audio_array.shape[0] <= 4 and audio_array.shape[1] > 4:
                        audio_cf = audio_array
                    else:
                        audio_cf = audio_array.T
                else:
                    raise ValueError(f"Audio array must be 1D or 2D, got shape {audio_array.shape}")
                return torch.from_numpy(audio_cf).float()

            def encode(self, audio_array, sample_rate):
                """Encode single audio array"""
                # Convert numpy array to torch tensor
                if isinstance(audio_array, np.ndarray):
                    # audio_array is [num_samples, num_channels] or [num_samples]
                    audio = self._to_channels_first(audio_array)
                    audio = audio.unsqueeze(0)
                else:
                    audio, sample_rate = torchaudio.load(str(audio_array))
                    if audio.dim() == 2:
                        audio = audio.unsqueeze(0)
                    elif audio.dim() == 1:
                        audio = audio.unsqueeze(0).unsqueeze(0)

                with torch.no_grad():
                    emb_d = get_param_embeds(audio, model, sample_rate)
                mid = emb_d["mid"].cpu().numpy().squeeze()
                side = emb_d["side"].cpu().numpy().squeeze()
                return np.concatenate([mid, side])

            def encode_batch(self, audio_arrays, sample_rates):
                """Encode batch of audio arrays (much faster!)"""
                batch_tensors = []

                # Assume all same sample rate (same dry source)
                sr = sample_rates[0]

                # Resample individually on CPU to avoid OOM on GPU
                for audio_array in audio_arrays:
                    audio = self._to_channels_first(audio_array)

                    # Resample on CPU if needed (avoids huge GPU memory for batch resampling)
                    if sr != 48000:
                        audio = torchaudio.functional.resample(audio.cpu(), sr, 48000)

                    batch_tensors.append(audio)

                # Stack into batch [batch_size, channels, samples] - now at 48kHz
                batch = torch.stack(batch_tensors, dim=0)

                # Compute embeddings (no resampling needed, already 48kHz)
                with torch.no_grad():
                    emb_d = get_param_embeds(batch, model, 48000)

                # Extract and concatenate mid/side for each sample
                embeddings = []
                for i in range(batch.shape[0]):
                    mid = emb_d["mid"][i].cpu().numpy()
                    side = emb_d["side"][i].cpu().numpy()
                    embeddings.append(np.concatenate([mid, side]))

                return embeddings

        return AFXWrapper()

    else:
        raise ValueError(f"Unknown embedder: {embedder_type}")


# Embedding Loop
def embed_manifest_samples_inmem(
    manifest: list,
    embedder_type: str,
    batch_size: int = 32,
):
    """
    Run embeddings on in-memory audio arrays with batching for speed.
    Updates manifest with embeddings directly (no file I/O).

    Args:
        manifest: List of manifest items with 'audio' arrays
        embedder_type: 'clap' or 'afxrep'
        batch_size: Number of samples to process in parallel (default 32)
    """
    embedder = load_embedder(embedder_type)

    # Check if embedder supports batching
    has_batch_encode = hasattr(embedder, 'encode_batch')

    if has_batch_encode:
        # Batch processing (much faster!)
        for batch_start in tqdm(range(0, len(manifest), batch_size), desc=f"Embedding ({embedder_type})"):
            batch_end = min(batch_start + batch_size, len(manifest))
            batch_items = manifest[batch_start:batch_end]

            # Collect batch
            batch_audio = []
            batch_sr = []
            for item in batch_items:
                batch_audio.append(item["audio"])
                batch_sr.append(item["sample_rate"])

            # Compute embeddings in batch
            batch_embeddings = embedder.encode_batch(batch_audio, batch_sr)

            # Store results
            for idx, (item, emb) in enumerate(zip(batch_items, batch_embeddings)):
                if "embeddings" not in item:
                    item["embeddings"] = {}

                item["embeddings"][embedder_type] = {
                    "embedding_type": embedder_type,
                    "embedding": emb,
                    "embedding_dim": int(emb.shape[-1]),
                }

                if "index" not in item:
                    item["index"] = batch_start + idx

    else:
        # Fallback to per-sample processing (backward compatible)
        for idx, item in enumerate(tqdm(manifest, desc=f"Embedding ({embedder_type})")):
            # Get audio from memory
            audio_array = item["audio"]
            sample_rate = item["sample_rate"]

            # Compute embedding
            emb = embedder.encode(audio_array, sample_rate)

            # Create embeddings dict if it doesn't exist
            if "embeddings" not in item:
                item["embeddings"] = {}

            # Store embedding directly in manifest (in-memory)
            item["embeddings"][embedder_type] = {
                "embedding_type": embedder_type,
                "embedding": emb,  # Store embedding array directly
                "embedding_dim": int(emb.shape[-1]),
            }

            # Backfill index if missing
            if "index" not in item:
                item["index"] = idx

    print(f"\nEmbeddings computed ({embedder_type}): {len(manifest)} samples")
    return manifest


# Main
def main():
    """
    Load in-memory manifest, compute embeddings, and save updated manifest.
    All processing happens in-memory (no audio files loaded from disk).
    """
    parser = argparse.ArgumentParser("Embed generated samples (CLAP or AFX-Rep) - in-memory")
    parser.add_argument("run_dir", type=str, help="Path to run directory created by 1_generate_samples")
    parser.add_argument("--embedder", type=str, default="clap", choices=["clap", "afxrep"])

    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifests" / "manifest_inmem.pkl"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Could not find in-memory manifest: {manifest_path}")

    # Load manifest with audio arrays
    print(f"Loading in-memory manifest: {manifest_path}")
    with open(manifest_path, "rb") as f:
        manifest = pickle.load(f)

    print(f"Loaded {len(manifest)} samples from manifest")

    # Compute embeddings
    manifest = embed_manifest_samples_inmem(
        manifest=manifest,
        embedder_type=args.embedder,
    )

    # Save updated manifest
    with open(manifest_path, "wb") as f:
        pickle.dump(manifest, f)

    print(f"Updated manifest saved: {manifest_path}")


if __name__ == "__main__":
    main()
