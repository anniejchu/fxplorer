"""
Generate in-memory FX sample manifests from a YAML config.
"""

import argparse
import json
from pathlib import Path
import yaml
from datetime import datetime
import pickle 
from fxplorer.applyfx.fx_generator import FXChainGenerator
from fxplorer.helper import make_run_dir, set_nested
from fxplorer.constants import OUTPUT_DIR_AFX


# Utilities
def load_yaml(path: Path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# Plugin ID resolution
def resolve_plugin_id(requested_id: str, params: dict):
    """
    YAML might specify `eq`, but the actual plugin is like `eq_6_0`.
    We match by prefix.
    """
    # exact
    if requested_id in params["plugins"]:
        return requested_id

    # prefix match
    for actual_pid in params["plugins"]:
        if actual_pid.startswith(requested_id):
            return actual_pid

    raise ValueError(f"Could not match override plugin id '{requested_id}' "
                     f"to any plugin: {list(params['plugins'])}")


# Manual chains
def generate_manual_chains(gen: FXChainGenerator, cfg, outdir: Path, manifest: list):
    """Generate manual chains - audio kept in memory"""
    manual_cfg = cfg.get("manual_chains", {})
    n_per_chain = cfg["sample_generation"].get("num_samples_per_manual_chain", 1)
    profile_random_ratio = cfg.get("sample_generation", {}).get("profile_random_ratio", 0.25)

    def resolve_override_value(raw_value):
        if isinstance(raw_value, dict) and "min" in raw_value and "max" in raw_value:
            return gen.rand_uniform(float(raw_value["min"]), float(raw_value["max"]))
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
            return gen.rand_uniform(float(raw_value[0]), float(raw_value[1]))
        return raw_value

    for chain_name, entry in manual_cfg.items():
        chain_spec = entry["chain"]
        description = entry.get("description", "")
        overrides = entry.get("param_overrides", {})
        n_for_chain = int(entry.get("num_samples", n_per_chain))
        apply_rand_params = bool(entry.get("apply_rand_params", True))

        print(f"\nManual chain {chain_name}: {chain_spec}")

        if n_for_chain <= 0:
            continue

        use_profiles = (
            apply_rand_params
            and len(chain_spec) == 1
            and not overrides
        )

        if use_profiles:
            samples = gen.generate_samples_with_profiles(
                chain_spec[0],
                n_for_chain,
                random_ratio=profile_random_ratio,
            )
            for i, (board, params) in enumerate(samples):
                audio = gen.render_audio(board)
                manifest.append({
                    "type": "manual",
                    "name": chain_name,
                    "index": i,
                    "description": description,
                    "chain": chain_spec,
                    "param_overrides": overrides,
                    "audio": audio, # stored in-memory
                    "sample_rate": gen.sample_rate,
                    "params": params,
                })
            continue

        for i in range(n_for_chain):

            # Build deterministically
            board, params = gen.build_chain(
                chain_spec=chain_spec,
                apply_rand_params=apply_rand_params
            )

            # Apply overrides
            for requested_id, param_dict in overrides.items():
                pid = resolve_plugin_id(requested_id, params)

                for dotted_key, val in param_dict.items():
                    set_nested(params["plugins"][pid], dotted_key, resolve_override_value(val))

            # Rebuild DSP with overridden params
            board = gen.reconstruct_board_from_params(params)

            # Render audio - keep in memory
            audio = gen.render_audio(board)

            manifest.append({
                "type": "manual",
                "name": chain_name,
                "index": i,
                "description": description,
                "chain": chain_spec,
                "param_overrides": overrides,
                "audio": audio, # stored in-memory
                "sample_rate": gen.sample_rate,
                "params": params,
            })


# Random chains

def generate_random_chains(gen:FXChainGenerator, cfg, outdir, manifest):
    """Generate random chains - audio kept in memory"""
    random_cfg = cfg.get("random_chains", {})
    n_per_chain = cfg["sample_generation"].get("num_samples_per_random_chain", 1)

    for name, entry in random_cfg.items():
        description = entry.get("description", "")
        chain_complexity = entry["chain_complexity"]
        allowed_fx = entry["allowed_effect_types"]

        print(f"\nRandom chain {name}: allowed={allowed_fx}")

        for i in range(n_per_chain):
            board, params = gen.generate_random_chain(
                chain_complexity=chain_complexity,
                allowed_effect_types=allowed_fx
            )

            # Render audio - keep in memory
            audio = gen.render_audio(board)

            manifest.append({
                "type": "random",
                "name": name,
                "index": i,
                "description": description,
                "chain_complexity": chain_complexity,
                "allowed_effect_types": allowed_fx,
                "audio": audio,  # store in-memory
                "sample_rate": gen.sample_rate,
                "params": params,
            })


# Parameter sweeps
def generate_param_sweeps(gen:FXChainGenerator, cfg, outdir, manifest):
    """Generate parameter sweeps - audio kept in memory"""
    sweeps = cfg.get("param_sweeps", {})

    for sweep_name, entry in sweeps.items():
        chain_spec = entry["chain_spec"]
        fx_mod = entry["fx_mod_to_sweep"]
        param_key = entry["param_to_sweep"]
        values = entry["values"]

        print(f"\nSweep {sweep_name}: {fx_mod}.{param_key}")

        sweep_results = gen.generate_param_sweep(
            chain_spec=chain_spec,
            fx_mod_to_sweep=fx_mod,
            param_to_sweep=param_key,
            values=values,
            normalize_output=gen.normalize_output,
            global_mix=1.0,
        )

        for i, item in enumerate(sweep_results):
            params = item["params"]
            audio = item["audio"]  # Already rendered by generate_param_sweep
            value = values[i]

            manifest.append({
                "type": "sweep",
                "name": sweep_name,
                "fx_mod_to_sweep": fx_mod,
                "param": param_key,
                "value": value,
                "audio": audio,  # store in-memory
                "sample_rate": gen.sample_rate,
                "params": params,
            })

def main():
    """
    Generate samples using in-memory pipeline.
    Audio arrays are stored directly in the manifest (no WAV files saved).
    This manifest can then be passed to 2_embed_samples.py for embedding.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--dry-audio", type=str, default=None,
                        help="Override audio.dry_audio_path from the config YAML")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Override output root directory (default: _outputs/)")
    parser.add_argument("--num-samples", type=int, default=None,
                        help="Override num_samples_per_random_chain in sample_generation")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))

    if args.dry_audio:
        cfg.setdefault("audio", {})["dry_audio_path"] = args.dry_audio
    if args.num_samples is not None:
        cfg.setdefault("sample_generation", {})["num_samples_per_random_chain"] = args.num_samples

    output_root = Path(args.output_dir) if args.output_dir else OUTPUT_DIR_AFX
    run_dir = make_run_dir(output_root, cfg.get("experiment_name", "run"))
    manifest_dir = run_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    gen = FXChainGenerator(
        dry_audio_path=cfg["audio"]["dry_audio_path"],
        normalize_dry=cfg["audio"].get("normalize_dry", True),
        target_lufs=cfg["audio"].get("target_lufs", -14),
        normalize_mode=cfg["audio"].get("normalize_mode", "rms"),
        normalize_output=cfg["audio"].get("normalize_output", True),
        rng_seed=cfg.get("seed", None),
    )

    manifest = []

    if cfg.get("sample_generation", {}).get("include_dry", False):
        params = gen.build_chain([], apply_rand_params=False)[1]
        manifest.append({
            "type": "dry",
            "name": "dry",
            "index": 0,
            "chain": [],
            "audio": gen.dry_audio,
            "sample_rate": gen.sample_rate,
            "params": params,
            "is_dry": True,
        })

    print("\nManual chains")
    generate_manual_chains(gen, cfg, None, manifest)

    print("\nRandom chains")
    generate_random_chains(gen, cfg, None, manifest)

    print("\nParameter sweeps")
    generate_param_sweeps(gen, cfg, None, manifest)

    # Save manifest with in-memory audio arrays
    # Note: numpy arrays need custom JSON encoding
    print(f"\nGenerated {len(manifest)} samples in memory.")
    print(f"Total audio data: ~{sum(item['audio'].nbytes for item in manifest) / 1e6:.1f} MB")

    # Save as pickle to preserve numpy arrays
    manifest_path = manifest_dir / "manifest_inmem.pkl"
    with open(manifest_path, "wb") as f:
        pickle.dump(manifest, f)
    print(f"Manifest saved (pickle): {manifest_path}")

    # Also save metadata-only JSON for reference
    manifest_meta = []
    for i, item in enumerate(manifest):
        meta = {k: v for k, v in item.items() if k not in ('audio',)}
        meta['index'] = i
        meta['audio_shape'] = item['audio'].shape
        meta['audio_dtype'] = str(item['audio'].dtype)
        manifest_meta.append(meta)

    save_json(manifest_dir / "manifest_meta.json", manifest_meta)
    print(f"Metadata saved (JSON): {manifest_dir / 'manifest_meta.json'}")


if __name__ == "__main__":
    main()
