"""
Benchmark the real upload-triggered FXplorer pipeline.

Unlike the earlier isolated stage benchmark, this script drives the same
backend entrypoint that the frontend uses when a user uploads a new dry file:

  POST /api/session/run_pipeline

That means the timing now includes the full request path the user waits for:
  1) upload hashing + save to uploads/
  2) temp YAML creation
  3) subprocess execution of:
       - fxplorer.pipeline.1_generate_samples
       - fxplorer.pipeline.2_embed_samples  (once per embedder)
       - fxplorer.pipeline.3_reduce_embeddings (once per embedder)
  4) backend reload of the new run_dir into memory

The benchmark also wraps the backend helper calls so it can still report
per-stage subprocess timings without deviating from production behavior.

Examples:
  # Benchmark the default upload flow with target_samples ~= 100
  python scripts/benchmark_cost.py

  # Benchmark a custom request shape across durations
  python scripts/benchmark_cost.py --durations 2 4 10 --target_samples 100 --n_repeats 3

  # Compare embedding on CPU vs GPU for the same upload flow
  python scripts/benchmark_cost.py --devices cpu cuda

  # Benchmark an exact frontend-style custom selection payload
  python scripts/benchmark_cost.py \
      --selected_fx eq:6 reverb \
      --exploration_mode chain \
      --sample_counts '{"": 1, "eq:6": 20, "reverb": 20, "eq:6,reverb": 60}'

Notes:
  - target_samples is only approximate for some configs (for example
    random_chain may overshoot to the next per-chain multiple). The script
    records the actual num_samples returned by the backend.
  - The device switch only affects embedding stages. Sample generation/render
    and dimensionality reduction remain CPU-bound in this pipeline.
  - First-run model downloads are not suppressed. If checkpoints are missing,
    that cold-start cost will be part of the measured request time.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


_BACKEND_MOD = None


def _get_backend_module():
    global _BACKEND_MOD
    if _BACKEND_MOD is None:
        import backend as backend_mod  # noqa: WPS433
        _BACKEND_MOD = backend_mod
    return _BACKEND_MOD


def _get_torchaudio():
    import torchaudio  # noqa: WPS433
    return torchaudio


def _get_torch():
    import torch  # noqa: WPS433
    return torch


def _make_trimmed_wav(src_path: Path, duration_s: float, out_path: Path) -> Path:
    """Write a trimmed copy of src_path to out_path (exactly duration_s seconds)."""
    torchaudio = _get_torchaudio()
    audio, sr = torchaudio.load(str(src_path))
    n_frames_want = int(duration_s * sr)
    n_frames_avail = audio.shape[-1]
    if n_frames_avail >= n_frames_want:
        trimmed = audio[:, :n_frames_want]
    else:
        repeats = int(np.ceil(n_frames_want / n_frames_avail))
        trimmed = audio.repeat(1, repeats)[:, :n_frames_want]
    torchaudio.save(str(out_path), trimmed, sr)
    return out_path


def _load_json_arg(raw: str | None, label: str):
    if raw is None:
        return None

    candidate = Path(raw)
    text = candidate.read_text() if candidate.exists() else raw
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON or a path to a JSON file") from exc


def _stage_label(mod_name: str, args: list[str]) -> str:
    if mod_name in {"fxplorer.pipeline.2_embed_samples", "fxplorer.pipeline.3_reduce_embeddings"}:
        if "--embedder" in args:
            idx = args.index("--embedder")
            if idx + 1 < len(args):
                return f"{mod_name}:{args[idx + 1]}"
    return mod_name


@contextmanager
def _embed_device_env(device: str):
    previous = {
        "CLAP_FORCE_CPU": os.environ.get("CLAP_FORCE_CPU"),
        "AFXREP_FORCE_CPU": os.environ.get("AFXREP_FORCE_CPU"),
    }
    try:
        if device == "cpu":
            os.environ["CLAP_FORCE_CPU"] = "1"
            os.environ["AFXREP_FORCE_CPU"] = "1"
        elif device == "cuda":
            os.environ.pop("CLAP_FORCE_CPU", None)
            os.environ.pop("AFXREP_FORCE_CPU", None)
        else:
            raise ValueError(f"Unknown embed device: {device}")
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class StageTrace:
    """Temporarily wrap backend helpers to record real stage timings."""

    def __init__(self):
        self.backend = None
        self.records: list[dict[str, Any]] = []
        self.temp_config_path: Path | None = None
        self._orig_run_module = None
        self._orig_make_temp_config = None
        self._orig_load_run_dir = None

    def __enter__(self):
        self.backend = _get_backend_module()
        self._orig_run_module = self.backend._run_module
        self._orig_make_temp_config = self.backend._make_temp_config
        self._orig_load_run_dir = self.backend.load_run_dir

        def timed_run_module(mod_name: str, args: list[str]):
            stage = _stage_label(mod_name, args)
            t0 = time.perf_counter()
            try:
                return self._orig_run_module(mod_name, args)
            finally:
                self.records.append({
                    "stage": stage,
                    "elapsed_s": time.perf_counter() - t0,
                })

        def timed_make_temp_config(*args, **kwargs):
            t0 = time.perf_counter()
            path = self._orig_make_temp_config(*args, **kwargs)
            self.temp_config_path = Path(path)
            self.records.append({
                "stage": "backend._make_temp_config",
                "elapsed_s": time.perf_counter() - t0,
            })
            return path

        def timed_load_run_dir(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return self._orig_load_run_dir(*args, **kwargs)
            finally:
                self.records.append({
                    "stage": "backend.load_run_dir",
                    "elapsed_s": time.perf_counter() - t0,
                })

        self.backend._run_module = timed_run_module
        self.backend._make_temp_config = timed_make_temp_config
        self.backend.load_run_dir = timed_load_run_dir
        return self

    def __exit__(self, exc_type, exc, tb):
        self.backend._run_module = self._orig_run_module
        self.backend._make_temp_config = self._orig_make_temp_config
        self.backend.load_run_dir = self._orig_load_run_dir


def _cache_digest(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _drop_cache_entry(digest: str):
    backend_mod = _get_backend_module()
    cache = backend_mod._load_upload_cache()
    if digest in cache:
        del cache[digest]
        backend_mod._save_upload_cache(cache)


def _remove_path(path: Path | None):
    if path is None or not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _cleanup_request_artifacts(digest: str, run_dir: Path | None, temp_cfg_path: Path | None):
    backend_mod = _get_backend_module()
    cache = backend_mod._load_upload_cache()
    cached_entry = cache.pop(digest, None)
    backend_mod._save_upload_cache(cache)

    dry_path = None
    if cached_entry:
        raw = cached_entry.get("dry_path")
        if raw:
            dry_path = Path(raw)

    _remove_path(run_dir)
    _remove_path(dry_path)
    _remove_path(temp_cfg_path)


def _build_request_fields(args, sample_counts, combinations) -> dict[str, str]:
    fields = {
        "config_id": args.config_id,
        "embed_modes": ",".join(args.embed_modes),
        "reduction_method": args.reduction_method,
    }
    if args.target_samples is not None:
        fields["target_samples"] = str(args.target_samples)
    if args.allowed_fx:
        fields["allowed_fx"] = ",".join(args.allowed_fx)
    if args.exploration_mode:
        fields["exploration_mode"] = args.exploration_mode
    if args.selected_fx:
        fields["selected_fx"] = json.dumps(args.selected_fx)
    if sample_counts is not None:
        fields["sample_counts"] = json.dumps(sample_counts)
    if combinations is not None:
        fields["combinations"] = json.dumps(combinations)
    return fields


def _aggregate_stage_runs(stage_runs: list[list[dict[str, Any]]]) -> tuple[list[str], dict[str, dict[str, float]]]:
    stage_order: list[str] = []
    for records in stage_runs:
        for record in records:
            stage = record["stage"]
            if stage not in stage_order:
                stage_order.append(stage)

    stage_stats = {}
    for stage in stage_order:
        values = [
            next((record["elapsed_s"] for record in records if record["stage"] == stage), 0.0)
            for records in stage_runs
        ]
        stage_stats[stage] = {
            "mean_s": float(np.mean(values)),
            "std_s": float(np.std(values)),
        }

    return stage_order, stage_stats


def bench_upload_request(
    wav_path: Path,
    n_repeats: int,
    request_fields: dict[str, str],
    cleanup: bool,
    embed_device: str,
):
    """POST the real upload endpoint repeatedly and summarize timings."""
    backend_mod = _get_backend_module()
    client = backend_mod.app.test_client()
    file_bytes = wav_path.read_bytes()
    digest = _cache_digest(file_bytes)

    total_times = []
    num_samples = []
    stage_runs = []
    repeat_payloads = []

    for rep_idx in range(n_repeats):
        _drop_cache_entry(digest)
        trace = None
        payload = None
        run_dir = None
        try:
            with _embed_device_env(embed_device):
                with StageTrace() as trace:
                    t0 = time.perf_counter()
                    resp = client.post(
                        "/api/session/run_pipeline",
                        data={
                            **request_fields,
                            "file": (io.BytesIO(file_bytes), wav_path.name),
                        },
                        content_type="multipart/form-data",
                    )
                    elapsed = time.perf_counter() - t0

            payload = resp.get_json(silent=True)
            if resp.status_code != 200:
                body = payload if payload is not None else resp.get_data(as_text=True)
                raise RuntimeError(f"HTTP {resp.status_code}: {body}")
            if payload.get("cache_hit"):
                raise RuntimeError("Benchmark hit upload cache; expected a forced cache miss.")

            run_dir_raw = payload.get("run_dir")
            run_dir = Path(run_dir_raw) if run_dir_raw else None

            total_times.append(elapsed)
            num_samples.append(int(payload.get("num_samples", -1)))
            stage_runs.append(trace.records)
            repeat_payloads.append({
                "repeat": rep_idx + 1,
                "elapsed_s": elapsed,
                "num_samples": int(payload.get("num_samples", -1)),
                "status": payload.get("status"),
            })
        finally:
            if cleanup:
                _cleanup_request_artifacts(
                    digest=digest,
                    run_dir=run_dir,
                    temp_cfg_path=trace.temp_config_path if trace is not None else None,
                )

    stage_order, stage_stats = _aggregate_stage_runs(stage_runs)
    mean_total = float(np.mean(total_times))
    mean_stage_sum = float(np.mean([sum(r["elapsed_s"] for r in records) for records in stage_runs]))

    torchaudio = _get_torchaudio()
    wav_info = torchaudio.info(str(wav_path))
    return {
        "embed_device": embed_device,
        "duration_s": float(wav_info.num_frames / wav_info.sample_rate),
        "n_repeats": n_repeats,
        "request_fields": request_fields,
        "num_samples": num_samples,
        "num_samples_unique": sorted(set(num_samples)),
        "mean_total_s": mean_total,
        "std_total_s": float(np.std(total_times)),
        "mean_stage_sum_s": mean_stage_sum,
        "mean_request_overhead_s": mean_total - mean_stage_sum,
        "stage_order": stage_order,
        "stage_stats": stage_stats,
        "repeats": repeat_payloads,
    }


def print_total_table(results: list[dict[str, Any]]):
    header = (
        f"{'Duration':>10}  {'Embed dev':>9}  {'Repeats':>7}  {'Actual pts':>10}  "
        f"{'Mean total (s)':>14}  {'Std (s)':>9}  "
        f"{'Stage sum (s)':>13}  {'Overhead (s)':>12}"
    )
    print("\nUpload Endpoint End-to-End Benchmark")
    print(header)
    print("-" * len(header))
    for r in results:
        actual = ",".join(str(n) for n in r["num_samples_unique"])
        print(
            f"{r['duration_s']:>9.1f}s"
            f"  {r['embed_device']:>9}"
            f"  {r['n_repeats']:>7}"
            f"  {actual:>10}"
            f"  {r['mean_total_s']:>14.3f}"
            f"  {r['std_total_s']:>9.3f}"
            f"  {r['mean_stage_sum_s']:>13.3f}"
            f"  {r['mean_request_overhead_s']:>12.3f}"
        )


def print_stage_tables(results: list[dict[str, Any]]):
    for r in results:
        print(f"\nStage Breakdown @ {r['duration_s']:.1f}s [{r['embed_device']}]")
        header = f"{'Stage':<42}  {'Mean (s)':>10}  {'Std (s)':>9}"
        print(header)
        print("-" * len(header))
        for stage in r["stage_order"]:
            stats = r["stage_stats"][stage]
            print(f"{stage:<42}  {stats['mean_s']:>10.3f}  {stats['std_s']:>9.3f}")


def _resolve_devices(requested_devices: list[str] | None) -> tuple[list[str], bool]:
    torch = _get_torch()
    cuda_available = torch.cuda.is_available()
    if requested_devices is None:
        return (["cuda"] if cuda_available else ["cpu"]), cuda_available

    devices = list(dict.fromkeys(requested_devices))
    if "cuda" in devices and not cuda_available:
        print("Warning: CUDA not available; skipping requested 'cuda' runs.", file=sys.stderr)
        devices = [device for device in devices if device != "cuda"]

    if not devices:
        raise ValueError("No runnable devices remain after filtering unavailable CUDA.")

    return devices, cuda_available


def main():
    parser = argparse.ArgumentParser(description="Benchmark FXplorer's real upload pipeline")
    parser.add_argument(
        "--dry_audio",
        type=Path,
        default=REPO_ROOT / "assets" / "2-Step Thump Beat 05.wav",
        help="Source dry audio file (trimmed to each duration before upload)",
    )
    parser.add_argument(
        "--durations",
        type=float,
        nargs="+",
        default=[2.0, 4.0, 10.0],
        help="Audio durations (seconds) to benchmark",
    )
    parser.add_argument(
        "--n_repeats",
        type=int,
        default=3,
        help="Number of end-to-end upload requests per duration (default: 3)",
    )
    parser.add_argument(
        "--config_id",
        default="random_chain",
        help="Backend config preset id to send to /api/session/run_pipeline",
    )
    parser.add_argument(
        "--target_samples",
        type=int,
        default=100,
        help="target_samples request field (default: 100)",
    )
    parser.add_argument(
        "--allowed_fx",
        nargs="+",
        default=None,
        help="Optional allowed_fx list passed to the backend",
    )
    parser.add_argument(
        "--exploration_mode",
        choices=["separate", "chain"],
        default=None,
        help="Optional custom-combo exploration_mode payload",
    )
    parser.add_argument(
        "--selected_fx",
        nargs="+",
        default=None,
        help="Optional selected_fx payload for frontend-style custom combo requests",
    )
    parser.add_argument(
        "--sample_counts",
        default=None,
        help="JSON string or JSON file path for frontend-style sample_counts payload",
    )
    parser.add_argument(
        "--combinations",
        default=None,
        help="JSON string or JSON file path for frontend-style combinations payload",
    )
    parser.add_argument(
        "--embed_modes",
        nargs="+",
        default=["afxrep", "clap"],
        help="Embedder modes to request (default: afxrep clap)",
    )
    parser.add_argument(
        "--devices",
        nargs="+",
        choices=["cpu", "cuda"],
        default=None,
        help="Embedding device modes to benchmark, e.g. --devices cpu cuda. "
             "This only affects embedding stages; render/reduction stay on CPU "
             "(default: cuda if available, else cpu)",
    )
    parser.add_argument(
        "--reduction_method",
        choices=["pca", "umap", "tsne"],
        default="pca",
    )
    parser.add_argument(
        "--keep_runs",
        action="store_true",
        help="Keep generated upload files, temp configs, and output run dirs",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "benchmark_results.json",
        help="Path to write benchmark summary JSON",
    )
    args = parser.parse_args()

    if not args.dry_audio.exists():
        print(f"Error: dry_audio not found: {args.dry_audio}", file=sys.stderr)
        sys.exit(1)
    if args.n_repeats < 1:
        print("Error: n_repeats must be >= 1", file=sys.stderr)
        sys.exit(1)
    if any(d <= 0 for d in args.durations):
        print("Error: durations must all be > 0", file=sys.stderr)
        sys.exit(1)

    try:
        sample_counts = _load_json_arg(args.sample_counts, "sample_counts")
        combinations = _load_json_arg(args.combinations, "combinations")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if sample_counts is not None and not isinstance(sample_counts, dict):
        print("Error: sample_counts must decode to a JSON object", file=sys.stderr)
        sys.exit(1)
    if combinations is not None and not isinstance(combinations, list):
        print("Error: combinations must decode to a JSON array", file=sys.stderr)
        sys.exit(1)

    try:
        _get_torchaudio()
        _get_backend_module()
        devices, cuda_available = _resolve_devices(args.devices)
    except ModuleNotFoundError as exc:
        print(f"Error: missing runtime dependency: {exc.name}", file=sys.stderr)
        print(
            "Install the FXplorer pipeline dependencies in the active environment "
            "(for example torch, torchaudio, and the backend requirements) before running this benchmark.",
            file=sys.stderr,
        )
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    request_fields = _build_request_fields(args, sample_counts=sample_counts, combinations=combinations)

    print(f"Source audio: {args.dry_audio}")
    print(f"Durations: {args.durations} s")
    print(f"Repeats: {args.n_repeats}")
    print(f"Config: {args.config_id}")
    print(f"Target samples: {args.target_samples}")
    print(f"Embed modes: {args.embed_modes}")
    print(f"Embed devices: {devices} (CUDA available: {cuda_available})")
    print(f"Reduction method: {args.reduction_method}")
    print(f"Cleanup artifacts: {not args.keep_runs}")
    if args.selected_fx:
        print(f"Selected FX: {args.selected_fx}")
    if sample_counts is not None:
        print(f"Sample counts: {sample_counts}")
    if combinations is not None:
        print(f"Combinations: {combinations}")

    tmp_dir = REPO_ROOT / "assets" / "benchmark_samples"
    tmp_dir.mkdir(exist_ok=True)

    trimmed = {}
    for dur in args.durations:
        out_wav = tmp_dir / f"audio_{dur:.1f}s.wav"
        _make_trimmed_wav(args.dry_audio, dur, out_wav)
        trimmed[dur] = out_wav
        print(f"Trimmed {dur:.1f}s -> {out_wav.name}")

    results = []
    for device in devices:
        for dur in args.durations:
            print(f"\nBenchmarking upload flow @ {dur:.1f}s [{device}] ...", flush=True)
            result = bench_upload_request(
                trimmed[dur],
                n_repeats=args.n_repeats,
                request_fields=request_fields,
                cleanup=not args.keep_runs,
                embed_device=device,
            )
            results.append(result)
            actual = ",".join(str(n) for n in result["num_samples_unique"])
            print(
                f"  actual_points={actual}  total={result['mean_total_s']:.3f}s ± {result['std_total_s']:.3f}  "
                f"overhead={result['mean_request_overhead_s']:.3f}s"
            )

    print_total_table(results)
    print_stage_tables(results)

    output = {
        "config": {
            "dry_audio": str(args.dry_audio),
            "durations": args.durations,
            "n_repeats": args.n_repeats,
            "config_id": args.config_id,
            "target_samples": args.target_samples,
            "allowed_fx": args.allowed_fx,
            "exploration_mode": args.exploration_mode,
            "selected_fx": args.selected_fx,
            "sample_counts": sample_counts,
            "combinations": combinations,
            "embed_modes": args.embed_modes,
            "devices": devices,
            "cuda_available": cuda_available,
            "reduction_method": args.reduction_method,
            "keep_runs": args.keep_runs,
        },
        "request_fields": request_fields,
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved -> {args.out}")


if __name__ == "__main__":
    main()
