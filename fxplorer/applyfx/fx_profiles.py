"""
Perceptual parameter profiles for each FX type. Used to ensure diverse sampling when exploring a single FX. (on pedalboard side)
Goal: provide some sort of "archetype" coverage (make sure we have some wideband coverage of what an effect can do)

"archetypes" compiled from audio engineering references / DAW presets/ empirically chosen
- common DAW & plugins presets (logic, ableton, reaper, etc)
- mixing engineer's handbook (owinski, 2017)

When generating N samples for an FX:
- Sample from multiple profiles to cover sonic archetypes
- E.g., 20 chorus samples → mix of subtle/classic/leslie/vibrato/shimmer

Usage:
    from fxplorer.applyfx.fx_profiles import get_fx_profiles

    profiles = get_fx_profiles("chorus")
    # Returns list of parameter range dicts for chorus archetypes
"""

FX_PROFILES = {
    "chorus": [
        {
            "name": "subtle_doubling",
            "weight": 0.6,
            "params": {
                "rate_hz": (0.1, 1.0),
                "depth": (0.1, 0.4),
                "centre_delay_ms": (3.0, 7.0),
                "feedback": (0.0, 0.2),
                "mix": (0.2, 0.5),
            }
        },
        {
            "name": "classic_chorus",
            "weight": 1.1,
            "params": {
                "rate_hz": (0.5, 2.5),
                "depth": (0.4, 0.7),
                "centre_delay_ms": (7.0, 14.0),
                "feedback": (0.2, 0.5),
                "mix": (0.4, 0.7),
            }
        },
        {
            "name": "leslie_rotary",
            "weight": 1.2,
            "params": {
                "rate_hz": (0.6, 2.0),
                "depth": (0.7, 1.0),
                "centre_delay_ms": (12.0, 20.0),
                "feedback": (0.5, 0.85),
                "mix": (0.6, 1.0),
            }
        },
        {
            "name": "wide_ensemble",
            "weight": 1.4,
            "params": {
                "rate_hz": (1.2, 5.0),
                "depth": (0.8, 1.0),
                "centre_delay_ms": (12.0, 20.0),
                "feedback": (0.6, 0.95),
                "mix": (0.8, 1.0),
            }
        },
        {
            "name": "aggressive_warble",
            "weight": 1.6,
            "params": {
                "rate_hz": (5.0, 10.0),
                "depth": (0.85, 1.0),
                "centre_delay_ms": (8.0, 18.0),
                "feedback": (0.6, 0.95),
                "mix": (0.85, 1.0),
            }
        },
        {
            "name": "vibrato_warble",
            "weight": 0.9,
            "params": {
                "rate_hz": (4.0, 9.0),
                "depth": (0.6, 1.0),
                "centre_delay_ms": (3.0, 8.0),
                "feedback": (0.0, 0.3),
                "mix": (0.4, 0.85),
            }
        },
        {
            "name": "shimmer_detune",
            "weight": 1.0,
            "params": {
                "rate_hz": (0.05, 0.3),
                "depth": (0.7, 1.0),
                "centre_delay_ms": (8.0, 18.0),
                "feedback": (0.4, 0.95),
                "mix": (0.7, 1.0),
            }
        },
    ],

    "gain": [
        {
            "name": "attenuate",
            "weight": 1.0,
            "params": {
                "gain_db": (-24.0, -8.0),
            }
        },
        {
            "name": "neutral",
            "weight": 1.2,
            "params": {
                "gain_db": (-3.0, 3.0),
            }
        },
        {
            "name": "boost",
            "weight": 1.0,
            "params": {
                "gain_db": (6.0, 24.0),
            }
        },
    ],

    "highpass": [
        {
            "name": "rumble_cut",
            "weight": 1.2,
            "params": {
                "cutoff_hz": (20.0, 120.0),
            }
        },
        {
            "name": "thin_out",
            "weight": 1.0,
            "params": {
                "cutoff_hz": (120.0, 600.0),
            }
        },
        {
            "name": "telephone",
            "weight": 0.7,
            "params": {
                "cutoff_hz": (600.0, 3000.0),
            }
        },
    ],

    "lowpass": [
        {
            "name": "darken",
            "weight": 1.0,
            "params": {
                "cutoff_hz": (300.0, 1500.0),
            }
        },
        {
            "name": "warmth",
            "weight": 1.2,
            "params": {
                "cutoff_hz": (1500.0, 6000.0),
            }
        },
        {
            "name": "air_cut",
            "weight": 0.8,
            "params": {
                "cutoff_hz": (6000.0, 18000.0),
            }
        },
    ],

    "reverb": [
        {
            "name": "tight_ambience",
            "weight": 1.0,
            "params": {
                "room_size": (0.01, 0.15),
                "damping": (0.3, 0.7),
                "wet_level": (0.1, 0.3),
                "dry_level": (0.7, 1.0),
                "width": (0.5, 1.0),
            }
        },
        {
            "name": "small_room",
            "weight": 1.5,
            "params": {
                "room_size": (0.15, 0.4),
                "damping": (0.2, 0.6),
                "wet_level": (0.2, 0.5),
                "dry_level": (0.5, 0.9),
                "width": (0.6, 1.0),
            }
        },
        {
            "name": "hall",
            "weight": 1.2,
            "params": {
                "room_size": (0.4, 0.7),
                "damping": (0.1, 0.5),
                "wet_level": (0.3, 0.6),
                "dry_level": (0.4, 0.8),
                "width": (0.7, 1.0),
            }
        },
        {
            "name": "cathedral",
            "weight": 1.0,
            "params": {
                "room_size": (0.7, 0.95),
                "damping": (0.0, 0.4),
                "wet_level": (0.4, 0.7),
                "dry_level": (0.3, 0.7),
                "width": (0.8, 1.0),
            }
        },
        {
            "name": "infinite_shimmer",
            "weight": 0.6,
            "params": {
                "room_size": (0.9, 0.99),
                "damping": (0.0, 0.2),
                "wet_level": (0.5, 0.7),  # Limited to prevent clipping
                "dry_level": (0.2, 0.5),
                "width": (0.9, 1.0),
            }
        },
        {
            "name": "washed_out",
            "weight": 0.7,
            "params": {
                "room_size": (0.6, 0.95),
                "damping": (0.05, 0.35),
                "wet_level": (0.6, 0.9),
                "dry_level": (0.2, 0.6),
                "width": (0.7, 1.0),
            }
        },
    ],

    "compressor": [
        {
            "name": "gentle_glue",
            "weight": 1.5,
            "params": {
                "threshold_db": (-20.0, -10.0),
                "ratio": (1.5, 3.0),
                "attack_ms": (10.0, 40.0),
                "release_ms": (80.0, 250.0),
            }
        },
        {
            "name": "aggressive_pump",
            "weight": 1.0,
            "params": {
                "threshold_db": (-15.0, -5.0),
                "ratio": (4.0, 10.0),
                "attack_ms": (0.5, 5.0),
                "release_ms": (20.0, 100.0),
            }
        },
        {
            "name": "parallel_thickening",
            "weight": 1.0,
            "params": {
                "threshold_db": (-50.0, -30.0),
                "ratio": (3.0, 8.0),
                "attack_ms": (5.0, 20.0),
                "release_ms": (100.0, 400.0),
            }
        },
        {
            "name": "brick_wall_limiting",
            "weight": 0.8,
            "params": {
                "threshold_db": (-6.0, -1.0),
                "ratio": (10.0, 20.0),
                "attack_ms": (0.01, 2.0),
                "release_ms": (30.0, 100.0),
            }
        },
    ],

    "distortion": [
        {
            "name": "warmth_saturation",
            "weight": 1.5,
            "params": {
                "drive_db": (3.0, 12.0),
            }
        },
        {
            "name": "overdrive",
            "weight": 1.2,
            "params": {
                "drive_db": (12.0, 22.0),
            }
        },
        {
            "name": "heavy_distortion",
            "weight": 1.0,
            "params": {
                "drive_db": (22.0, 35.0),
            }
        },
        {
            "name": "extreme_fuzz",
            "weight": 0.8,
            "params": {
                "drive_db": (35.0, 40.0),
            }
        },
        {
            "name": "gnarly_edge",
            "weight": 0.7,
            "params": {
                "drive_db": (28.0, 40.0),
            }
        },
    ],

    "phaser": [
        {
            "name": "subtle_sweep",
            "weight": 1.2,
            "params": {
                "rate_hz": (0.1, 1.0),
                "depth": (0.2, 0.5),
                "centre_frequency_hz": (400.0, 1500.0),
                "feedback": (0.0, 0.3),
                "mix": (0.2, 0.5),
            }
        },
        {
            "name": "classic_phaser",
            "weight": 1.5,
            "params": {
                "rate_hz": (0.5, 3.0),
                "depth": (0.4, 0.7),
                "centre_frequency_hz": (200.0, 3000.0),
                "feedback": (0.2, 0.6),
                "mix": (0.3, 0.7),
            }
        },
        {
            "name": "resonant_sweep",
            "weight": 1.0,
            "params": {
                "rate_hz": (1.0, 6.0),
                "depth": (0.6, 0.9),
                "centre_frequency_hz": (100.0, 5000.0),
                "feedback": (0.5, 0.75),
                "mix": (0.5, 0.9),
            }
        },
        {
            "name": "extreme_modulation",
            "weight": 0.7,
            "params": {
                "rate_hz": (5.0, 12.0),
                "depth": (0.7, 1.0),
                "centre_frequency_hz": (80.0, 6000.0),
                "feedback": (0.6, 0.75),
                "mix": (0.6, 0.95),
            }
        },
        {
            "name": "wide_resonant",
            "weight": 0.6,
            "params": {
                "rate_hz": (2.0, 7.0),
                "depth": (0.8, 1.0),
                "centre_frequency_hz": (200.0, 4000.0),
                "feedback": (0.6, 0.75),
                "mix": (0.7, 1.0),
            }
        },
    ],

    "delay": [
        {
            "name": "haas_stereo_width",
            "weight": 0.8,
            "params": {
                "delay_seconds": (0.005, 0.035),
                "feedback": (0.0, 0.2),
                "mix": (0.1, 0.3),
            }
        },
        {
            "name": "slap_echo",
            "weight": 1.2,
            "params": {
                "delay_seconds": (0.05, 0.15),
                "feedback": (0.1, 0.4),
                "mix": (0.2, 0.5),
            }
        },
        {
            "name": "rhythmic_echo",
            "weight": 1.5,
            "params": {
                "delay_seconds": (0.15, 0.6),
                "feedback": (0.3, 0.7),
                "mix": (0.3, 0.65),
            }
        },
        {
            "name": "ambient_wash",
            "weight": 1.0,
            "params": {
                "delay_seconds": (0.6, 1.0),
                "feedback": (0.5, 0.95),
                "mix": (0.4, 0.85),
            }
        },
        {
            "name": "dubby",
            "weight": 0.7,
            "params": {
                "delay_seconds": (0.25, 0.8),
                "feedback": (0.6, 0.95),
                "mix": (0.6, 0.9),
            }
        },
    ],

    "limiter": [
        {
            "name": "gentle_ceiling",
            "weight": 1.2,
            "params": {
                "threshold_db": (-8.0, -4.0),
                "release_ms": (30.0, 120.0),
            }
        },
        {
            "name": "brick_wall",
            "weight": 0.8,
            "params": {
                "threshold_db": (-3.0, -0.5),
                "release_ms": (10.0, 50.0),
            }
        },
    ],

    "gate": [
        {
            "name": "gentle_expander",
            "weight": 1.1,
            "params": {
                "threshold_db": (-60.0, -40.0),
                "ratio": (2.0, 6.0),
                "attack_ms": (1.0, 10.0),
                "release_ms": (80.0, 250.0),
            }
        },
        {
            "name": "tight_gate",
            "weight": 1.0,
            "params": {
                "threshold_db": (-40.0, -20.0),
                "ratio": (6.0, 12.0),
                "attack_ms": (0.2, 5.0),
                "release_ms": (20.0, 120.0),
            }
        },
        {
            "name": "choppy",
            "weight": 0.7,
            "params": {
                "threshold_db": (-30.0, -10.0),
                "ratio": (12.0, 30.0),
                "attack_ms": (0.05, 2.0),
                "release_ms": (10.0, 80.0),
            }
        },
    ],

    "eq:6": [
        {
            "name": "subtle_correction",
            "weight": 1.5,
            "params": {
                "bands.*.gain_db": (-3.0, 3.0),
                "bands.*.q": (0.5, 1.5),
            }
        },
        {
            "name": "creative_shaping",
            "weight": 1.5,
            "params": {
                "bands.*.gain_db": (-8.0, 8.0),
                "bands.*.q": (0.7, 2.5),
            }
        },
        {
            "name": "extreme_filtering",
            "weight": 1.0,
            "params": {
                "bands.*.gain_db": (-15.0, 15.0),
                "bands.*.q": (1.0, 5.0),
            }
        },
        {
            "name": "tilt_bright",
            "weight": 0.7,
            "params": {
                "bands.0.gain_db": (-6.0, -2.0),
                "bands.1.gain_db": (-3.0, 1.0),
                "bands.4.gain_db": (3.0, 8.0),
                "bands.5.gain_db": (4.0, 10.0),
                "bands.*.q": (0.6, 1.6),
            }
        },
        {
            "name": "tilt_dark",
            "weight": 0.7,
            "params": {
                "bands.0.gain_db": (3.0, 8.0),
                "bands.1.gain_db": (1.0, 4.0),
                "bands.4.gain_db": (-8.0, -3.0),
                "bands.5.gain_db": (-10.0, -4.0),
                "bands.*.q": (0.6, 1.6),
            }
        },
        {
            "name": "mid_scoop",
            "weight": 0.8,
            "params": {
                "bands.2.gain_db": (-12.0, -6.0),
                "bands.3.gain_db": (-8.0, -3.0),
                "bands.*.q": (0.8, 2.0),
            }
        },
        {
            "name": "presence_push",
            "weight": 0.8,
            "params": {
                "bands.3.gain_db": (3.0, 8.0),
                "bands.4.gain_db": (4.0, 10.0),
                "bands.*.q": (0.8, 2.5),
            }
        },
        {
            "name": "surgical_notch",
            "weight": 0.6,
            "params": {
                "bands.*.gain_db": (-18.0, -6.0),
                "bands.*.q": (3.0, 8.0),
            }
        },
    ],
}


def get_fx_profiles(fx_type: str) -> list:
    """
    Get parameter profiles for an FX type.

    Args:
        fx_type: FX type like "chorus", "reverb", "eq:6", etc.

    Returns:
        List of profile dicts, or None if no profiles defined
    """
    return FX_PROFILES.get(fx_type)


def sample_from_profiles(fx_type: str, num_samples: int, rng, random_ratio: float = 0.3) -> list:
    """
    Distribute samples across profiles with a mix of guided and random exploration.

    Args:
        fx_type: FX type like "chorus"
        num_samples: Total number of samples to generate
        rng: numpy random generator
        random_ratio: Fraction of samples to generate randomly (default 0.3 = 30%)
                     Rest are guided by profiles for better coverage

    Returns:
        List of (profile_name, profile_params) tuples, one per sample
        profile_name is None for random samples
    """
    profiles = get_fx_profiles(fx_type)
    if not profiles:
        return None

    # Split into guided vs random samples
    num_random = max(1, int(num_samples * random_ratio))
    num_guided = num_samples - num_random

    # Calculate weighted distribution for guided samples
    weights = [p["weight"] for p in profiles]
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    # Distribute guided samples proportionally
    profile_counts = []
    remaining = num_guided

    for i, weight in enumerate(normalized_weights[:-1]):
        count = round(num_guided * weight)
        profile_counts.append(count)
        remaining -= count

    # Last profile gets remaining guided samples
    profile_counts.append(max(0, remaining))

    # Build output list: guided samples
    result = []
    for profile, count in zip(profiles, profile_counts):
        for _ in range(count):
            result.append((profile["name"], profile["params"]))

    # Add random samples (marked with None profile)
    for _ in range(num_random):
        result.append((None, None))

    # Shuffle to mix archetypes and random samples
    rng.shuffle(result)

    return result
