"""
Pedalboard-based FX chain generator for:
- Offline sample generation (for CLAP / AFx-Rep embedding, PCA spaces, etc.)
- Human-readable JSON parameter dumps
- Optional VST3/AU/LV2 plugins via pedalboard.load_plugin
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import uuid
from datetime import datetime

import numpy as np
import soundfile as sf
from pedalboard import (
    Pedalboard,
    Gain, #including gain but not really using bc we are normalizing
    Distortion,
    Compressor,
    Limiter,
    NoiseGate,
    Chorus,
    Phaser,
    Delay,
    Reverb,
    PeakFilter,
    HighpassFilter,
    LowpassFilter,
)
from pedalboard import load_plugin
from pedalboard.io import AudioFile

from fxplorer.helper import normalize_lufs, set_all_seeds, set_nested
from fxplorer.constants import ASSETS_DIR, OUTPUT_DIR
from fxplorer.helper import make_run_dir#, set_all_seeds
from fxplorer.applyfx.fx_profiles import get_fx_profiles  


# Types / Constants
EffectType = str  # e.g. "gain", "eq:3", "reverb", "vst:my_comp"

DEFAULT_EFFECT_TYPES: List[EffectType] = [
    "gain",
    "eq:6",  # 6-band parametric
    "compressor",
    "reverb",
    "distortion",
    "highpass",
    "lowpass",
    "delay",
    "chorus",
    "phaser",
    "limiter",
    "gate",
]

class FXChainGenerator:
    """
    High-level API for generating and rendering FX chains with Pedalboard.

    Example:

        gen = FXChainGenerator(
            dry_audio_path="salsa_piano.wav",
            normalize_dry=True,
            target_lufs=-14.0,
            rng_seed=42,
        )

        # Manual chain
        board, params = gen.build_chain(
            chain_spec=["gain", "eq:3", "reverb"],
            apply_rand_params=True,
        )
        audio = gen.render_audio(board)
        gen.save_audio(audio, "manual_chain.wav")

        # Random chain
        board2, params2 = gen.generate_random_chain(
            chain_complexity="medium",
            allowed_effect_types=["gain", "eq:3", "compressor", "reverb"],
        )
        audio2 = gen.render_audio(board2)
        gen.save_audio(audio2, "random_chain.wav")

        # Param sweep
        sweep = gen.generate_param_sweep(
            chain_spec=["gain", "eq:3", "reverb"],
            fx_mod_to_sweep="gain",
            param_to_sweep="gain_db",
            values=[-6.0, 0.0, 6.0],
        )
    """

    # Construction / Audio load
    def __init__(
        self,
        dry_audio_path: Union[str, Path],
        base_effect_types: Optional[Sequence[EffectType]] = None,
        normalize_dry: bool = True,
        target_lufs: float = -14.0,
        normalize_mode: str = "rms",
        normalize_output: bool = False,  # Preserve loudness differences for perceptual exploration
        rng_seed: Optional[int] = None,
    ):
        dry_audio_path = Path(dry_audio_path)
        if not dry_audio_path.exists():
            raise FileNotFoundError(f"Dry audio not found: {dry_audio_path}")

        self.dry_audio_path = dry_audio_path
        self.normalize_dry = bool(normalize_dry)
        self.normalize_output = bool(normalize_output)
        self.normalize_mode = str(normalize_mode).lower()
        self.target_lufs = float(target_lufs)

        # Effect palette
        self.base_effect_types: List[EffectType] = (
            list(base_effect_types) if base_effect_types is not None else DEFAULT_EFFECT_TYPES
        )

        # VST registry: label -> plugin path
        self.vst_registry: Dict[str, str] = {}

        # RNG
        if rng_seed is not None:
            set_all_seeds(rng_seed)
        self.rng = np.random.default_rng(rng_seed)

        # Profile sampling state
        self.use_profile_sampling = False  # Enable for guided exploration
        self.profile_override = None  # Current profile params to use

        # Load dry audio once
        print(f"[FXChainGenerator] Loading dry audio from {dry_audio_path}...")
        with AudioFile(str(dry_audio_path), "r") as f:
            audio = f.read(f.frames)  # shape [num_samples, num_channels]
            self.sample_rate = f.samplerate

        # Ensure float32 from the start (avoids repeated copies later)
        if audio.dtype != np.float32:
            audio = audio.astype("float32")

        # Normalize dry audio if requested
        if self.normalize_dry:
            audio = self._normalize_audio(audio, label="dry")

        self.dry_audio = audio
        print(
            f"Loaded dry audio: shape={self.dry_audio.shape}, sr={self.sample_rate}, "
            f"normalize_dry={self.normalize_dry}"
        )

    # Utilities

    def rand_uniform(self, low: float, high: float) -> float:
        """Deterministic uniform sampler, using self.rng."""
        return float(self.rng.uniform(low, high))

    def _normalize_audio(self, audio: np.ndarray, label: str = "output") -> np.ndarray:
        """
        Normalize audio using the configured mode.
        - "rms": scale to target RMS derived from target_lufs (dBFS)
        - "lufs": use LUFS normalization
        """
        mode = self.normalize_mode
        if mode == "lufs":
            print(f"Normalizing {label} audio to ~{self.target_lufs} LUFS...")
            return normalize_lufs(audio, self.sample_rate, self.target_lufs)
        if mode == "rms":
            target_rms = float(10 ** (self.target_lufs / 20.0))
            rms = float(np.sqrt(np.mean(np.square(audio))))
            if rms <= 1e-9:
                return audio
            scale = min(target_rms / rms, 10.0)
            return audio * scale
        return audio

    def _rand_choice(self, options: Sequence[Any]) -> Any:
        """Deterministic choice helper."""
        return options[int(self.rng.integers(0, len(options)))]

    def _sample_range(self, bounds: Union[Tuple[float, float], float], param_name: str = None) -> float:
        """
        Sample from a (min, max) range or return a fixed value.

        If profile_override is set and contains this param, use profile bounds instead.
        """
        # Check for profile override
        if self.profile_override and param_name:
            if param_name in self.profile_override:
                bounds = self.profile_override[param_name]
            elif param_name.startswith("bands."):
                parts = param_name.split(".", 2)
                if len(parts) == 3 and parts[1].isdigit():
                    wildcard_key = f"bands.*.{parts[2]}"
                    if wildcard_key in self.profile_override:
                        bounds = self.profile_override[wildcard_key]

        if isinstance(bounds, (int, float)):
            return float(bounds)
        return self.rand_uniform(float(bounds[0]), float(bounds[1]))

    def _sample_log_range(self, bounds: Union[Tuple[float, float], float], param_name: str = None) -> float:
        """
        Sample uniformly in log space for perceptual coverage.

        If profile_override is set and contains this param, use profile bounds instead.
        """
        # Check for profile override
        if self.profile_override and param_name:
            if param_name in self.profile_override:
                bounds = self.profile_override[param_name]
            elif param_name.startswith("bands."):
                parts = param_name.split(".", 2)
                if len(parts) == 3 and parts[1].isdigit():
                    wildcard_key = f"bands.*.{parts[2]}"
                    if wildcard_key in self.profile_override:
                        bounds = self.profile_override[wildcard_key]

        if isinstance(bounds, (int, float)):
            return float(bounds)
        low, high = float(bounds[0]), float(bounds[1])
        low = max(low, 1e-6)
        high = max(high, low * 1.001)
        return float(np.exp(self.rng.uniform(np.log(low), np.log(high))))

    def _sample_profile(self, profiles: Sequence[Dict[str, Tuple[float, float]]]) -> Dict[str, float]:
        """Pick a profile and sample all keys inside."""
        profile = self._rand_choice(list(profiles))
        return {k: self._sample_range(v) for k, v in profile.items()}

    def _use_profile(self, probability: float = 0.75) -> bool:
        """Return True to sample from a profile vs free-range sampling."""
        return bool(self.rng.random() < probability)

    # VST / external plugins

    def register_vst(self, label: str, plugin_path: Union[str, Path]) -> None:
        """
        Register a VST3 / AU / LV2 plugin with a short label.

        After registration you can use "vst:<label>" as an effect type.

        Example:
            gen.register_vst("nice_comp", "/path/to/NiceComp.vst3")
            board, params = gen.build_chain(["gain", "vst:nice_comp", "reverb"])
        """
        plugin_path = Path(plugin_path)
        if not plugin_path.exists():
            raise FileNotFoundError(f"VST plugin not found: {plugin_path}")

        self.vst_registry[label] = str(plugin_path)
        print(f"Registered VST '{label}': {plugin_path}")

    # Public chain APIs

    def generate_samples_with_profiles(
        self,
        fx_type: str,
        num_samples: int,
        random_ratio: float = 0.3,
    ) -> List[Tuple[Pedalboard, Dict[str, Any]]]:
        """
        Generate multiple samples for a single FX with intelligent profile sampling.

        70% of samples use guided profiles (e.g., subtle/classic/leslie chorus),
        30% use random exploration to discover unexpected variations.

        Args:
            fx_type: Effect type like "chorus", "reverb", etc.
            num_samples: Total number of samples to generate
            random_ratio: Fraction of random samples (default 0.3 = 30%)

        Returns:
            List of (board, params_dict) tuples
        """
        from fxplorer.applyfx.fx_profiles import sample_from_profiles

        results = []
        profile_samples = sample_from_profiles(fx_type, num_samples, self.rng, random_ratio)

        if not profile_samples:
            # No profiles defined, fall back to pure random
            print(f"[FXChainGenerator] No profiles for '{fx_type}', using random sampling")
            for _ in range(num_samples):
                board, params = self.build_chain([fx_type], apply_rand_params=True)
                results.append((board, params))
            return results

        # Generate samples using profile guidance
        for profile_name, profile_params in profile_samples:
            if profile_name is None:
                # Random sample
                self.profile_override = None
            else:
                # Guided sample
                self.profile_override = profile_params

            board, params = self.build_chain([fx_type], apply_rand_params=True)
            results.append((board, params))

        # Reset override
        self.profile_override = None
        return results

    def generate_random_chain(
        self,
        chain_complexity: int = 1, #str = "medium",
        allowed_effect_types: Optional[Sequence[EffectType]] = None,
        allow_repeats: bool = False,
    ) -> Tuple[Pedalboard, Dict[str, Any]]:
        """
        Sample a random FX chain from a palette.

        Args:
            chain_complexity: int - num of FX in chain
            allowed_effect_types:
                optional subset of effect types to use.
                If None, uses self.base_effect_types.

            allow_repeats:
                if True, an effect type may appear multiple times.

        Returns:
            (board, params_dict)
        """
        # Case 1: integer => exact number of FX
        if isinstance(chain_complexity, int):
            n_min = chain_complexity
            n_max = chain_complexity

        # Case 2: dict => {min: X, max: Y}
        elif isinstance(chain_complexity, dict):
            try:
                n_min = int(chain_complexity.get("min", 1))
                n_max = int(chain_complexity.get("max", n_min))
            except Exception:
                raise ValueError(f"chain_complexity dict must contain integer min/max, got: {chain_complexity}")

        n_fx = int(self.rng.integers(n_min, n_max + 1))

        palette = list(allowed_effect_types) if allowed_effect_types else self.base_effect_types
        if not palette:
            raise ValueError("No effect types available to build a chain.")

        if allow_repeats:
            effect_types = list(self.rng.choice(palette, size=n_fx, replace=True))
        else:
            n_fx = min(n_fx, len(palette))
            effect_types = list(self.rng.choice(palette, size=n_fx, replace=False))

        return self.build_chain(chain_spec=effect_types, apply_rand_params=True)

    def build_chain(
        self,
        chain_spec: Sequence[EffectType],
        apply_rand_params: bool = True,
        param_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Pedalboard, Dict[str, Any]]:
        """
        Build a Pedalboard from a chain specification.

        Args:
            chain_spec:
                e.g. ["gain", "eq:3", "reverb"]
                Also supports "vst:label" if registered.

            apply_rand_params:
                if True, random params are sampled.
                if False, defaults are used (except param_overrides).

            param_overrides:
                optional dict mapping plugin_id -> param dict to override the
                random/default values. plugin_id is the "id" field in the
                chain spec (e.g., "gain_0", "eq_1", "vst_nice_comp_2", etc.)

        Returns:
            (board, params_dict) where params_dict has the form:

                {
                  "uuid": "...",
                  "dry_path": "...",
                  "sample_rate": 44100,
                  "target_lufs": -14.0,
                  "normalize_dry": true,
                  "normalize_output": true,
                  "timestamp": "...",
                  "chain": [
                    {"id": "gain_0", "type": "gain"},
                    {"id": "eq_1",   "type": "eq:3"},
                    {"id": "reverb_2","type": "reverb"}
                  ],
                  "plugins": {
                    "gain_0":   {...},
                    "eq_1":     {...},
                    "reverb_2": {...}
                  }
                }
        """
        effects: List[Any] = []
        chain_meta: List[Dict[str, Any]] = []
        plugins_params: Dict[str, Dict[str, Any]] = {}

        for idx, eff_type in enumerate(chain_spec):
            plugin_id = f"{eff_type.replace(':', '_')}_{idx}"

            plugin_objs, base_params = self._create_plugin(
                eff_type=eff_type,
                plugin_id=plugin_id,
                apply_rand_params=apply_rand_params,
            )

            # Apply overrides if present
            if param_overrides and plugin_id in param_overrides:
                base_params.update(param_overrides[plugin_id])

            # Add underlying plugin instances to board
            effects.extend(plugin_objs)

            chain_meta.append({"id": plugin_id, "type": eff_type})
            plugins_params[plugin_id] = base_params

        board = Pedalboard(effects)

        params_dict: Dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "dry_path": str(self.dry_audio_path),
            "sample_rate": self.sample_rate,
            "target_lufs": self.target_lufs,
            "normalize_mode": self.normalize_mode,
            "normalize_dry": self.normalize_dry,
            "normalize_output": self.normalize_output,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "chain": chain_meta,
            "plugins": plugins_params,
        }

        return board, params_dict

    # Rendering / export
    def render_audio(
        self,
        board_or_params: Union[Pedalboard, Dict[str, Any]],
        normalize_output: Optional[bool] = None,
        global_mix: float = 1.0,
    ) -> np.ndarray:
        """
        Render processed audio for a given board or params dict.

        Args:
            board_or_params:
                - Pedalboard instance, or
                - params dict as returned by build_chain / generate_random_chain

            normalize_output:
                if None, uses self.normalize_output.
                if True, normalizes processed audio to self.target_lufs.

            global_mix:
                wet/dry balance for the entire chain (0 = fully dry, 1 = fully wet).

        Returns:
            audio: numpy array [num_samples, num_channels], float32
        """
        if isinstance(board_or_params, Pedalboard):
            board = board_or_params
            params = None
        else:
            params = board_or_params
            board = self.reconstruct_board_from_params(params)

        # Apply FX
        wet = board(self.dry_audio, self.sample_rate)

        # Ensure float32 without unnecessary copies
        if wet.dtype != np.float32:
            wet = wet.astype("float32")

        # Global wet/dry mix
        mix = float(np.clip(global_mix, 0.0, 1.0))

        if mix == 1.0:
            # Fully wet - no need to copy dry audio
            audio = wet
        else:
            # Need dry audio for mixing
            dry = self.dry_audio if self.dry_audio.dtype == np.float32 else self.dry_audio.astype("float32")
            audio = (1.0 - mix) * dry + mix * wet

        # Optional LUFS normalize output
        if normalize_output is None:
            normalize_output = self.normalize_output

        if normalize_output:
            audio = self._normalize_audio(audio)

        # Ensure output is float32 (only copy if needed)
        if audio.dtype != np.float32:
            audio = audio.astype("float32")

        return audio

    def save_audio(self, audio: np.ndarray, path: Union[str, Path]) -> None:
        """
        Convenience helper to write a processed audio file as WAV.

        Args:
            audio: numpy [num_samples, num_channels]
            path: output file path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio.T, self.sample_rate) #sf expects (samples, channels)
        print(f"Wrote {path}")

    # Param sweep helper

    def generate_param_sweep(
        self,
        chain_spec: Sequence[EffectType],
        fx_mod_to_sweep: str,
        param_to_sweep: str,
        values: Sequence[Any],
        apply_rand_params_base: bool = True,
        global_mix: float = 1.0,
        normalize_output: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate a set of rendered samples from a param sweep.

        This is meant for CLAP / AFx-Rep dataset creation.

        Args:
            chain_spec:
                e.g. ["gain", "eq:3", "reverb"]

            fx_mod_to_sweep:
                FX module whose params you want to sweep, e.g. "gain" or "eq:3".

            param_to_sweep:
                key inside the plugin param dict to modify, e.g. "gain_db",
                "band_freq_hz", "room_size", etc.

            values:
                sequence of values to sweep over.

            apply_rand_params_base:
                if True, base params are random; we then override param_to_sweep per value.

            global_mix:
                global wet/dry mix for render_audio.

            normalize_output:
                override output normalization behavior (None -> generator default).

        Returns:
            List of dicts, each containing:
                {
                    "audio": np.ndarray,
                    "params": params_dict,
                    "sweep_value": value,
                    "sweep_param": param_to_sweep,
                }
        """
        base_board, base_params = self.build_chain(
            chain_spec=chain_spec,
            apply_rand_params=apply_rand_params_base,
        )

        results: List[Dict[str, Any]] = []

        # Find plugin_ids whose "type" matches fx_mod_to_sweep
        plugin_ids = [
            item["id"]
            for item in base_params["chain"]
            if item["type"] == fx_mod_to_sweep
        ]
        if not plugin_ids:
            print(
                f"[generate_param_sweep] Warning: no plugins of type '{fx_mod_to_sweep}' "
                f"in chain_spec={chain_spec}"
            )

        # Count total board plugins vs logical chain length
        num_logical_plugins = len(base_params["chain"])
        num_board_plugins = len(base_board)

        if num_board_plugins != num_logical_plugins:
            for v in values:
                # Deep-ish copy of params
                params_copy = {
                    **base_params,
                    "plugins": {k: dict(val) for k, val in base_params["plugins"].items()},
                }

                # Override param on all matching plugins
                for pid in plugin_ids:
                    set_nested(params_copy["plugins"][pid], param_to_sweep, v)

                # Reconstruct board from modified params
                audio = self.render_audio(
                    board_or_params=params_copy,
                    normalize_output=normalize_output,
                    global_mix=global_mix,
                )

                results.append(
                    {
                        "audio": audio,
                        "params": params_copy,
                        "sweep_value": v,
                        "sweep_param": param_to_sweep,
                    }
                )
        else:
            # faster 1:1 mapping, safe to modify board in-place
            board = base_board

            for v in values:
                # Directly modify the plugin parameter(s) in the board
                for pid in plugin_ids:
                    # Find the board plugin index from chain metadata
                    chain_idx = next(i for i, item in enumerate(base_params["chain"]) if item["id"] == pid)
                    plugin = board[chain_idx]

                    # Set parameter directly on the Pedalboard plugin object
                    if "." in param_to_sweep:
                        # Nested param - not supported in fast path, would need custom logic
                        raise ValueError(
                            f"Nested param '{param_to_sweep}' not supported in fast sweep path. "
                            f"Use simple params like 'gain_db' or 'threshold_db'."
                        )
                    else:
                        # Simple param like "gain_db"
                        setattr(plugin, param_to_sweep, v)

                # Render with the modified board (no reconstruction needed!)
                audio = self.render_audio(
                    board_or_params=board,
                    normalize_output=normalize_output,
                    global_mix=global_mix,
                )

                # Build params dict for this value (lightweight copy)
                params_copy = {
                    **base_params,
                    "plugins": {k: dict(val) for k, val in base_params["plugins"].items()},
                }
                # Update the params dict to reflect the new value
                for pid in plugin_ids:
                    set_nested(params_copy["plugins"][pid], param_to_sweep, v)

                results.append(
                    {
                        "audio": audio,
                        "params": params_copy,
                        "sweep_value": v,
                        "sweep_param": param_to_sweep,
                    }
                )

        return results

    # Reconstruct from params
    def reconstruct_board_from_params(self, params: Dict[str, Any]) -> Pedalboard:
        """
        Rebuild a Pedalboard from a params dict.

        Assumes the dict has the schema produced by build_chain / generate_random_chain.
        """
        if "chain" not in params or "plugins" not in params:
            raise ValueError(
                "Params dict must contain 'chain' and 'plugins' keys to reconstruct."
            )

        effects: List[Any] = []
        for chain_item in params["chain"]:
            plugin_id = chain_item["id"]
            eff_type = chain_item["type"]
            p = params["plugins"].get(plugin_id, {})

            plugin_objs = self._create_plugin_from_params(
                eff_type=eff_type,
                plugin_id=plugin_id,
                p=p,
            )
            effects.extend(plugin_objs)

        return Pedalboard(effects)

    # Internal factory: random/default plugin creation
    def _create_plugin(
        self,
        eff_type: EffectType,
        plugin_id: str,
        apply_rand_params: bool,
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Create one logical plugin *group* and its parameter dict.

        eff_type examples:
            - "gain"
            - "highpass"
            - "lowpass"
            - "eq:3" (3 parametric bands)
            - "vst:my_label"

        Returns:
            (plugin_objs, params_dict)

            plugin_objs: list of underlying Pedalboard plugins that correspond
                         to this logical plugin. For most effects this has len=1;
                         for "eq:3" it will be 3 PeakFilter instances.

            params_dict: parameters for this logical plugin group.
        """
        # VST plugins
        if eff_type.startswith("vst:"):
            label = eff_type.split(":", 1)[1]
            if label not in self.vst_registry:
                raise ValueError(
                    f"VST label '{label}' not registered. "
                    f"Call register_vst('{label}', '/path/to/plugin.vst3') first."
                )
            path = self.vst_registry[label]
            plugin = load_plugin(path)
            params = {
                "plugin_path": path,
                "label": label,
                # Additional VST automation parameters could go here later.
            }
            return [plugin], params

        # Gain
        if eff_type == "gain":
            if apply_rand_params:
                # Simple uniform sampling - gain is straightforward
                gain_db = self._sample_range((-24.0, 24.0), param_name="gain_db")
            else:
                gain_db = 0.0
            plugin = Gain(gain_db=gain_db)
            params = {"gain_db": gain_db}
            return [plugin], params

        # Highpass / lowpass
        if eff_type == "highpass":
            if apply_rand_params:
                # Log-scale for perceptual coverage: rumble removal → thinness → telephone
                cutoff = self._sample_log_range((20.0, 8000.0), param_name="cutoff_hz")  # Expanded upper range for extreme thinness
            else:
                cutoff = 1000.0
            plugin = HighpassFilter(cutoff_frequency_hz=cutoff)
            params = {"type": "highpass", "cutoff_hz": cutoff}
            return [plugin], params

        if eff_type == "lowpass":
            if apply_rand_params:
                # Log-scale: darkness → warmth → air
                cutoff = self._sample_log_range((200.0, 18000.0), param_name="cutoff_hz")  # Expanded lower for extreme muffling
            else:
                cutoff = 5000.0
            plugin = LowpassFilter(cutoff_frequency_hz=cutoff)
            params = {"type": "lowpass", "cutoff_hz": cutoff}
            return [plugin], params

        # Parametric EQ: eq:1 .. eq:6
        if eff_type.startswith("eq:"):
            try:
                n_bands = int(eff_type.split(":", 1)[1])
            except Exception:
                raise ValueError(f"Invalid eq spec: '{eff_type}', expected 'eq:N'.")

            n_bands = max(1, min(n_bands, 6))  # clamp 1–6

            bands: List[Dict[str, float]] = []
            plugins: List[Any] = []

            # All possible frequency regions (NOT locked per band)
            freq_ranges = [
                (60, 250),  # low
                (250, 1000),  # low-mid
                (1000, 4000),  # mid
                (4000, 8000),  # high-mid
                (8000, 12000),  # presence
                (12000, 18000),  # air
            ]

            if apply_rand_params:
                # !! Shuffle frequency ranges so bands aren't locked to regions
                # This allows hi-shelf (all bands above 8kHz), mid-scoop, etc.
                available_ranges = list(freq_ranges)
                self.rng.shuffle(available_ranges)

                # Diverse gain/Q combinations (uniform sampling for maximum coverage)
                for i in range(n_bands):
                    fmin, fmax = available_ranges[i % len(available_ranges)]
                    freq = self._sample_log_range((fmin, fmax))

                    # Full gain range: -15 to +15 dB (safe with limiting, audible differences)
                    gain = self._sample_range(
                        (-15.0, 15.0),
                        param_name=f"bands.{i}.gain_db",
                    )

                    # Full Q range: 0.2 (very broad) to 8.0 (surgical)
                    # Favor musical range (0.5-3.0) but include extremes
                    if self.rng.random() < 0.7:  # 70% musical
                        q = self._sample_range(
                            (0.5, 3.0),
                            param_name=f"bands.{i}.q",
                        )
                    else:  # 30% extremes
                        q = self._sample_range(
                            (0.2, 8.0),
                            param_name=f"bands.{i}.q",
                        )

                    pf = PeakFilter(
                        cutoff_frequency_hz=freq,
                        gain_db=gain,
                        q=q,
                    )
                    plugins.append(pf)
                    bands.append({
                        "freq_hz": freq,
                        "gain_db": gain,
                        "q": q,
                    })
            else:
                # Default: neutral EQ
                for i in range(n_bands):
                    fmin, fmax = freq_ranges[i % len(freq_ranges)]
                    freq = (fmin * fmax) ** 0.5  # geometric mean
                    pf = PeakFilter(cutoff_frequency_hz=freq, gain_db=0.0, q=1.0)
                    plugins.append(pf)
                    bands.append({"freq_hz": freq, "gain_db": 0.0, "q": 1.0})

            sorted_bands = sorted(bands, key=lambda band: band["freq_hz"])
            params = {
                "num_bands": n_bands,
                "bands": sorted_bands,
            }
            return plugins, params

        # Distortion
        if eff_type == "distortion":
            if apply_rand_params:
                # Full range: 0 (clean) to 40dB (heavy saturation)
                # Tanh waveshaping inherently limits peaks, safe
                drive_db = self._sample_range((0.0, 40.0), "drive_db")
            else:
                drive_db = 12.0
            plugin = Distortion(drive_db=drive_db)
            params = {"drive_db": drive_db}
            return [plugin], params

        # Compressor
        if eff_type == "compressor":
            if apply_rand_params:
                # Research-backed ranges for maximum sonic diversity
                # Threshold: -60dB (parallel compression) to -1dB (glue/limiting)
                threshold = self._sample_range((-60.0, -1.0), "threshold_db")

                # Ratio: 1.2:1 (subtle) to 20:1 (limiting)
                # Higher ratios more likely with lower thresholds (musical coherence)
                if threshold < -30:
                    ratio = self._sample_range((2.0, 12.0), "ratio")  # Moderate to heavy
                elif threshold < -10:
                    ratio = self._sample_range((1.5, 8.0), "ratio")  # Light to heavy
                else:
                    ratio = self._sample_range((1.2, 4.0), "ratio")  # Glue/limiting range

                # Attack: 0.01ms (instant) to 120ms (slow, preserves transients)
                # Log-scale for perceptual uniformity
                attack = self._sample_log_range((0.01, 120.0), "attack_ms")

                # Release: 10ms (fast pumping) to 1000ms (smooth)
                release = self._sample_log_range((10.0, 1000.0), "release_ms")
            else:
                threshold, ratio, attack, release = -15.0, 4.0, 5.0, 150.0

            plugin = Compressor(
                threshold_db=threshold,
                ratio=ratio,
                attack_ms=attack,
                release_ms=release,
            )
            params = {
                "threshold_db": threshold,
                "ratio": ratio,
                "attack_ms": attack,
                "release_ms": release,
            }
            return [plugin], params

        # Limiter
        if eff_type == "limiter":
            if apply_rand_params:
                # Threshold: -12dB (gentle ceiling) to -0.5dB (brick wall)
                threshold = self._sample_range((-12.0, -0.5), "threshold_db")

                # Release: 10ms (fast/pumpy) to 200ms (smooth/transparent)
                release = self._sample_log_range((10.0, 200.0), "release_ms")
            else:
                threshold, release = -6.0, 50.0

            plugin = Limiter(threshold_db=threshold, release_ms=release)
            params = {"threshold_db": threshold, "release_ms": release}
            return [plugin], params

        # Noise gate
        if eff_type == "gate":
            if apply_rand_params:
                # Threshold: -70dB (subtle) to -10dB (aggressive chopping)
                threshold = self._sample_range((-70.0, -10.0), "threshold_db")

                # Ratio: 2:1 (gentle expansion) to 30:1 (hard gate/stutter)
                ratio = self._sample_range((2.0, 30.0), "ratio")

                # Attack: 0.1ms (instant) to 20ms (smooth)
                attack = self._sample_log_range((0.1, 20.0), "attack_ms")

                # Release: 10ms (choppy) to 800ms (smooth tail)
                release = self._sample_log_range((10.0, 800.0), "release_ms")
            else:
                threshold, ratio, attack, release = -40.0, 4.0, 5.0, 100.0

            plugin = NoiseGate(
                threshold_db=threshold,
                ratio=ratio,
                attack_ms=attack,
                release_ms=release,
            )
            params = {
                "threshold_db": threshold,
                "ratio": ratio,
                "attack_ms": attack,
                "release_ms": release,
            }
            return [plugin], params

        # Chorus
        if eff_type == "chorus":
            if apply_rand_params:
                # Rate: 0.05Hz (static doubling) to 10Hz (fast warble/vibrato)
                # Log-scale for perceptual spacing
                rate = self._sample_log_range((0.05, 10.0), "rate_hz")

                # Depth: 0.05 (subtle width) to 1.0 (extreme pitch modulation)
                depth = self._sample_range((0.05, 1.0), "depth")

                # Centre delay: 3ms (chorus) to 20ms (Tone.js nominal max)
                # Log-scale: short delays = tight, long = lush
                # Fixed: Was 1-25ms, but 1ms caused flanger-like metallic ringing
                centre_delay = self._sample_log_range((3.0, 20.0), "centre_delay_ms")

                # Feedback: 0.0 (no resonance) to 0.95 (strong chorus)
                feedback = self._sample_range((0.0, 0.95), "feedback")

                # Mix: 0.1 (subtle) to 1.0 (dominant)
                mix = self._sample_range((0.1, 1.0), "mix")
            else:
                rate, depth, centre_delay, feedback, mix = 1.5, 0.5, 7.0, 0.3, 0.5

            plugin = Chorus(
                rate_hz=rate,
                depth=depth,
                centre_delay_ms=centre_delay,
                feedback=feedback,
                mix=mix,
            )
            params = {
                "rate_hz": rate,
                "depth": depth,
                "centre_delay_ms": centre_delay,
                "feedback": feedback,
                "mix": mix,
            }
            return [plugin], params

        # Phaser
        if eff_type == "phaser":
            if apply_rand_params:
                # Rate: 0.01Hz (slow ambient sweep) to 12Hz (fast wobble)
                rate = self._sample_log_range((0.01, 12.0), "rate_hz")

                # Depth: 0.05 (subtle notch) to 1.0 (dramatic sweep)
                depth = self._sample_range((0.05, 1.0), "depth")

                # Centre frequency: 80Hz (bass phaser) to 6000Hz (airy/bright)
                # Log-scale for perceptual coverage
                centre_freq = self._sample_log_range((80.0, 6000.0), "centre_frequency_hz")

                # Feedback: 0.0 (gentle) to 0.75 (resonant)
                # Values above ~0.75 can cause sharp resonant peaks in Tone.js
                feedback = self._sample_range((0.0, 0.75), "feedback")

                # Mix: 0.1 (subtle) to 0.95 (dominant)
                mix = self._sample_range((0.1, 0.95), "mix")
            else:
                rate, depth, centre_freq, feedback, mix = 1.0, 0.5, 800.0, 0.0, 0.5

            plugin = Phaser(
                rate_hz=rate,
                depth=depth,
                centre_frequency_hz=centre_freq,
                feedback=feedback,
                mix=mix,
            )
            params = {
                "rate_hz": rate,
                "depth": depth,
                "centre_frequency_hz": centre_freq,
                "feedback": feedback,
                "mix": mix,
            }
            return [plugin], params

        # Delay
        if eff_type == "delay":
            if apply_rand_params:
                # Delay time: 1ms (Haas effect) to 1.0s (long ambient)
                # Log-scale: short = stereo widening, long = rhythmic echo
                # Covers Haas, slap, eighth-note, quarter-note, and long-tail echoes.
                delay_time = self._sample_log_range((0.001, 1.0), "delay_seconds")

                # Feedback: 0.0 (single repeat) to 0.95 (near-infinite)
                # High feedback can approach instability, frontend caps at 0.98
                feedback = self._sample_range((0.0, 0.95), "feedback")

                # Mix: 0.05 (subtle) to 0.85 (dominant)
                mix = self._sample_range((0.05, 0.85), "mix")
            else:
                delay_time, feedback, mix = 0.3, 0.4, 0.4

            plugin = Delay(
                delay_seconds=delay_time,
                feedback=feedback,
                mix=mix,
            )
            params = {
                "delay_seconds": delay_time,
                "feedback": feedback,
                "mix": mix,
            }
            return [plugin], params

        # Reverb
        if eff_type == "reverb":
            if apply_rand_params:
                # Room size: 0.01 (tiny/tight ambience) to 0.99 (cathedral/infinite)
                # Covers doubling, small room, hall, cathedral, and near-infinite spaces.
                room_size = self._sample_range((0.01, 0.99), "room_size")

                # Damping: 0.0 (bright shimmer) to 0.95 (dark/vintage plate)
                # Low = glass-like/digital, high = warm/muffled
                damping = self._sample_range((0.0, 0.95), "damping")

                # Wet level: 0.05 (subtle depth) to 0.95 (ambient wash)
                # Note: Limited to 0.7 if room_size > 0.85 (prevents clipping with large spaces)
                wet_level = self._sample_range((0.05, 0.95), "wet_level")
                if room_size > 0.85:
                    wet_level = min(wet_level, 0.7)  # Safety: reduce wet for huge rooms

                # Dry level: 0.2 (reverb-dominant) to 1.0 (dry-dominant)
                dry_level = self._sample_range((0.2, 1.0), "dry_level")

                # Width: 0.0 (mono) to 1.0 (full stereo spread)
                width = self._sample_range((0.0, 1.0), "width")
            else:
                room_size, damping, wet_level, dry_level, width = (
                    0.5,
                    0.4,
                    0.35,
                    0.75,
                    0.9,
                )

            plugin = Reverb(
                room_size=room_size,
                damping=damping,
                wet_level=wet_level,
                dry_level=dry_level,
                width=width,
            )
            params = {
                "room_size": room_size,
                "damping": damping,
                "wet_level": wet_level,
                "dry_level": dry_level,
                "width": width,
            }
            return [plugin], params

        raise ValueError(f"Unknown effect type: {eff_type}")

    # Internal factory: from stored params
    def _create_plugin_from_params(
        self,
        eff_type: EffectType,
        plugin_id: str,
        p: Dict[str, Any],
    ) -> List[Any]:
        """
        Build underlying plugin objects from a stored param dict.

        Mirrors _create_plugin but uses exactly the values in p.
        Returns a list of plugin instances (often length 1, multiple for eq:N).
        """
        # VST group
        if eff_type.startswith("vst:"):
            label = eff_type.split(":", 1)[1]
            plugin_path = p.get("plugin_path") or self.vst_registry.get(label)
            if plugin_path is None:
                raise ValueError(
                    f"Cannot reconstruct VST '{label}' for plugin_id '{plugin_id}'. "
                    "No plugin_path stored and not registered in vst_registry."
                )
            plugin = load_plugin(plugin_path)
            return [plugin]

        if eff_type == "gain":
            return [Gain(gain_db=float(p.get("gain_db", 0.0)))]

        if eff_type == "highpass":
            cutoff = float(p.get("cutoff_hz", 1000.0))
            return [HighpassFilter(cutoff_frequency_hz=cutoff)]

        if eff_type == "lowpass":
            cutoff = float(p.get("cutoff_hz", 5000.0))
            return [LowpassFilter(cutoff_frequency_hz=cutoff)]

        if eff_type.startswith("eq:"):
            bands = p.get("bands", [])
            plugins: List[Any] = []
            for band in bands:
                freq = float(band.get("freq_hz", 1000.0))
                gain = float(band.get("gain_db", 0.0))
                q = float(band.get("q", 1.0))
                pf = PeakFilter(
                    cutoff_frequency_hz=freq,
                    gain_db=gain,
                    q=q,
                )
                plugins.append(pf)
            return plugins

        if eff_type == "distortion":
            drive_db = float(p.get("drive_db", 0.0))
            return [Distortion(drive_db=drive_db)]

        if eff_type == "compressor":
            return [
                Compressor(
                    threshold_db=float(p.get("threshold_db", -20.0)),
                    ratio=float(p.get("ratio", 2.0)),
                    attack_ms=float(p.get("attack_ms", 10.0)),
                    release_ms=float(p.get("release_ms", 100.0)),
                )
            ]

        if eff_type == "limiter":
            return [
                Limiter(
                    threshold_db=float(p.get("threshold_db", -6.0)),
                    release_ms=float(p.get("release_ms", 50.0)),
                )
            ]

        if eff_type == "gate":
            return [
                NoiseGate(
                    threshold_db=float(p.get("threshold_db", -40.0)),
                    ratio=float(p.get("ratio", 4.0)),
                    attack_ms=float(p.get("attack_ms", 5.0)),
                    release_ms=float(p.get("release_ms", 100.0)),
                )
            ]

        if eff_type == "chorus":
            return [
                Chorus(
                    rate_hz=float(p.get("rate_hz", 1.0)),
                    depth=float(p.get("depth", 0.3)),
                    centre_delay_ms=float(p.get("centre_delay_ms", 5.0)),
                    feedback=float(p.get("feedback", 0.0)),
                    mix=float(p.get("mix", 0.5)),
                )
            ]

        if eff_type == "phaser":
            return [
                Phaser(
                    rate_hz=float(p.get("rate_hz", 1.0)),
                    depth=float(p.get("depth", 0.5)),
                    centre_frequency_hz=float(p.get("centre_frequency_hz", 800.0)),
                    feedback=float(p.get("feedback", 0.0)),
                    mix=float(p.get("mix", 0.5)),
                )
            ]

        if eff_type == "delay":
            return [
                Delay(
                    delay_seconds=float(p.get("delay_seconds", 0.25)),
                    feedback=float(p.get("feedback", 0.3)),
                    mix=float(p.get("mix", 0.3)),
                )
            ]

        if eff_type == "reverb":
            return [
                Reverb(
                    room_size=float(p.get("room_size", 0.3)),
                    damping=float(p.get("damping", 0.3)),
                    wet_level=float(p.get("wet_level", 0.2)),
                    dry_level=float(p.get("dry_level", 0.8)),
                    width=float(p.get("width", 1.0)),
                )
            ]

        raise ValueError(f"Unknown effect type in params: {eff_type}")


# Simple CLI / test harness


if __name__ == "__main__":
    """
    Test harness for FXChainGenerator.

    This script demonstrates the four main use cases:
    1. Manual FX chain with specific effects
    2. Random FX chain generation
    3. VST/AU plugin integration (commented out - requires plugins)
    4. Parameter sweep for dataset creation

    Usage: python -m fxplorer.applyfx.fx_generator
    """
    import json

    # Setup test environment
    _EXPORT_DIR = make_run_dir(OUTPUT_DIR, "pedalboard")
    SEED = 1
    DRY_AUDIO = Path(ASSETS_DIR/"salsa_piano.wav")

    # Initialize generator with LUFS normalization
    gen = FXChainGenerator(
        dry_audio_path=DRY_AUDIO,
        normalize_dry=True,
        target_lufs=-12.0,
        normalize_output=True,
        rng_seed=SEED,
    )

    # (1) Manual chain test - Specific FX with random parameters
    print("Test 1: Building manual FX chain...")
    manual_chain = ["eq:6", "chorus"]  # Can add: "compressor", "reverb"
    board1, params1 = gen.build_chain(
        chain_spec=manual_chain,
        apply_rand_params=True,  # Randomize parameters within smart ranges
    )
    audio1 = gen.render_audio(board1, global_mix=0.8)
    gen.save_audio(audio1, _EXPORT_DIR/"test_manual_chain.wav")
    with open(_EXPORT_DIR/"test_manual_chain_params.json", "w") as f:
        json.dump(params1, f, indent=2)
    print("Saved test_manual_chain.wav and test_manual_chain_params.json")

    # (2) Random chain test - Algorithmic FX chain generation
    print("\nTest 2: Generating random FX chain...")
    board2, params2 = gen.generate_random_chain(
        chain_complexity="medium",  # Controls # of FX (low=1-2, medium=2-3, high=3-4)
        allowed_effect_types=[
            "eq:6",
            "compressor",
            "reverb",
            "distortion",
            "highpass",
            "lowpass",
        ],
    )
    audio2 = gen.render_audio(board2, global_mix=1.0)
    gen.save_audio(audio2, _EXPORT_DIR/"test_random_chain.wav")
    with open(_EXPORT_DIR/"test_random_chain_params.json", "w") as f:
        json.dump(params2, f, indent=2)
    print("Saved test_random_chain.wav and test_random_chain_params.json")

    # (3) VST example (enable if you have a plugin)

    # try:
    #     gen.register_vst("my_comp", "/path/to/MyCompressor.vst3")
    #     vst_chain = ["gain", "vst:my_comp", "reverb"]
    #     board3, params3 = gen.build_chain(chain_spec=vst_chain, apply_rand_params=True)
    #     audio3 = gen.render_audio(board3, global_mix=0.9)
    #     gen.save_audio(audio3, "test_vst_chain.wav")
    #     with open("test_vst_chain_params.json", "w") as f:
    #         json.dump(params3, f, indent=2)
    #     print("Saved test_vst_chain.wav and test_vst_chain_params.json")
    # except FileNotFoundError as e:
    #     print(f"[VST example skipped] {e}")

    # (4) Simple param sweep test
    sweep_results = gen.generate_param_sweep(
        chain_spec=["gain"],#, "eq:3", "reverb"],
        fx_mod_to_sweep="gain",
        param_to_sweep="gain_db",
        values=[-6.0, 0.0, 6.0],
        normalize_output=False,
    )

    for i, item in enumerate(sweep_results):
        fname = _EXPORT_DIR/f"test_sweep_gain_{i}.wav"
        gen.save_audio(item["audio"], fname)
        print(
            f"Sweep {i}: {item['sweep_param']}={item['sweep_value']} -> {fname}"
        )

    print("FXChainGenerator smoke tests complete.")
