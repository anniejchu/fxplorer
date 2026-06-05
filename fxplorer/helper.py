from datetime import datetime
import os
import random
import uuid
from pathlib import Path
from typing import List, Optional, Union

import numbers
import numpy as np
import pyloudnorm as pyln
import requests
import torch
from audiotools import AudioSignal
from tqdm import tqdm

from fxplorer.constants import AFX_REP_CKPT, AFX_REP_CONFIG, AFX_REP_BASE_URL


def make_run_dir(parent: Path, prefix: str = "run") -> Path:
    """
    Create a unique timestamped subdirectory inside `parent`.

    Example:
        run_20250115_133015_a3c9fe
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]  # short unique suffix
    run_dir = parent / f"{prefix}_{now_str}_{uid}"
    
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir

def set_all_seeds(seed=42):
    """Comprehensive seed setting"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ['PYTHONHASHSEED'] = str(seed)

def get_clap_model(model_choice: str, **kwargs):
    if model_choice == "laion_clap":
        from fxplorer.embedders.laion_clap import LAIONCLAPWrapper
        force_cpu = os.getenv("CLAP_FORCE_CPU", "0").strip().lower() in ("1", "true", "yes")
        device = "cpu" if force_cpu else ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            model = LAIONCLAPWrapper(device=device, **kwargs)
        except RuntimeError as err:
            if device == "cuda" and "out of memory" in str(err).lower():
                print("Warning: CLAP CUDA OOM; retrying on CPU.")
                model = LAIONCLAPWrapper(device="cpu", **kwargs)
            else:
                raise
    else:
        raise ValueError("choose a valid model!")
    return model


def download_file(url, out_dir, chunk_size: int = 8192):

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    local_filename = out_dir / url.split('/')[-1]

    # Determine download size if provided
    head = requests.head(url, allow_redirects=True)
    total_bytes = head.headers.get("Content-Length")
    total = int(total_bytes) // chunk_size if total_bytes and total_bytes.isdigit() else None

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        content_iter = r.iter_content(chunk_size=chunk_size)
        if total:
            content_iter = tqdm(content_iter, total=total)
        with open(local_filename, 'wb') as f:
            for chunk in content_iter:
                if not chunk:
                    continue
                f.write(chunk)
    return local_filename


def ensure_afxrep_checkpoint(base_url: Optional[str] = None):
    """
    Ensure that the AFx-Rep checkpoint + config live under PRETRAINED_DIR.

    If missing, download from the public Hugging Face repo (or a user-specified base URL).
    """
    base = base_url or os.environ.get("AFX_REP_BASE_URL") or AFX_REP_BASE_URL
    ckpt_name = AFX_REP_CKPT.name
    config_name = AFX_REP_CONFIG.name

    if not AFX_REP_CKPT.exists():
        print(f"[↓] Downloading {ckpt_name} from {base}")
        downloaded = download_file(f"{base.rstrip('/')}/{ckpt_name}", AFX_REP_CKPT.parent)
        if downloaded != AFX_REP_CKPT:
            downloaded.rename(AFX_REP_CKPT)
        print(f"Saved checkpoint to {AFX_REP_CKPT}")
    else:
        print(f"AFx-Rep checkpoint found at {AFX_REP_CKPT}")

    if not AFX_REP_CONFIG.exists():
        print(f"[↓] Downloading {config_name} from {base}")
        downloaded = download_file(f"{base.rstrip('/')}/{config_name}", AFX_REP_CONFIG.parent)
        if downloaded != AFX_REP_CONFIG:
            downloaded.rename(AFX_REP_CONFIG)
        print(f"Saved config to {AFX_REP_CONFIG}")
    else:
        print(f"AFx-Rep config found at {AFX_REP_CONFIG}")

class AbstractCLAPWrapper:
    def preprocess_audio(self, signal: AudioSignal) -> AudioSignal:
        raise NotImplementedError("implement me :)")
    
    def get_audio_embeddings(self, signal: AudioSignal) -> torch.Tensor:
        raise NotImplementedError()
    
    def get_text_embeddings(self, text: Union[str, List[str]]) -> torch.Tensor:
        raise NotImplementedError()
    
    def compute_similarities(self, audio_emb, text_emb) -> torch.Tensor:
        raise NotImplementedError
    
    @property
    def sample_rate(self):
        raise NotImplementedError()


_LUFS_METER_CACHE = {}
def normalize_lufs(audio: np.ndarray, sample_rate: int, target_lufs: float = -14.0,debug: bool = False):
    if audio.ndim != 1 and audio.ndim != 2:
        raise ValueError(f"Audio must be 1D or 2D, got shape {audio.shape}")

    if audio.ndim == 1:
        original_shape = "mono"
        work_audio = audio[:, None]  # convert to (samples, 1)
        transpose_back = False

    elif audio.ndim == 2:
        # Detect orientation
        if audio.shape[0] <= 5:
            # Probably (channels, samples)
            original_shape = "channels_first"
            work_audio = audio.T  # → (samples, channels)
            transpose_back = True
        else:
            # Probably already (samples, channels)
            original_shape = "samples_first"
            work_audio = audio
            transpose_back = False

    if debug:
        print(f"[normalize_lufs] original shape: {audio.shape} ({original_shape})")
        print(f"[normalize_lufs] work_audio shape for pyloudnorm: {work_audio.shape}")

    # 2) Measure LUFS (use cached meter for performance)
    if sample_rate not in _LUFS_METER_CACHE:
        _LUFS_METER_CACHE[sample_rate] = pyln.Meter(sample_rate)
    meter = _LUFS_METER_CACHE[sample_rate]
    loudness = meter.integrated_loudness(work_audio)

    # 3) Compute gain needed to reach target LUFS
    gain_db = target_lufs - loudness
    gain_factor = 10.0 ** (gain_db / 20.0)

    if debug:
        print(f"[normalize_lufs] loudness={loudness:.2f} LUFS, target={target_lufs}")
        print(f"[normalize_lufs] applying gain {gain_db:.2f} dB (x{gain_factor:.3f})")

    # 4) Apply gain
    normalized = work_audio * gain_factor

    # 5) Return audio in original shape
    if original_shape == "mono":
        return normalized[:, 0]

    if transpose_back:
        return normalized.T  # back to (channels, samples)

    return normalized  # already (samples, channels)


def set_nested(d: dict, key_path: str, value):
    """
    Set nested dictionary value from a dotted path, e.g.:

        key_path = "bands.0.gain_db"
    """
    keys = key_path.split(".")
    obj = d
    for k in keys[:-1]:
        if k.isdigit():
            k = int(k)
            obj = obj[k]
        else:
            obj = obj.setdefault(k, {})
    last = keys[-1]
    if last.isdigit():
        obj[int(last)] = value
    else:
        obj[last] = value


def preprocess_audio(audio_path_or_array: Union[torch.Tensor, str, Path, np.ndarray, AudioSignal], 
                     salient_excerpt_duration: Optional[int] = None, 
                     sample_rate: Optional[int] = None, force_mono=True) -> AudioSignal:
    """Preprocesses an audio input (file path, tensor, ndarray, or AudioSignal).
    
    Args:
        audio_path_or_array: The audio input, can be a file path, tensor, ndarray, or AudioSignal.
        salient_excerpt_duration: If provided, extracts the salient excerpt of this duration.
        sample_rate: Required if input is a tensor or ndarray.
        
    Returns:
        Processed `AudioSignal`.
    """

    if isinstance(audio_path_or_array, (str, Path)):  
        sig = AudioSignal(audio_path_or_array)  
    elif isinstance(audio_path_or_array, AudioSignal):
        sig = audio_path_or_array  
    elif isinstance(audio_path_or_array, (torch.Tensor, np.ndarray)):
        if sample_rate is None:
            raise ValueError("Must provide `sample_rate` if input is a tensor or ndarray")
        sig = AudioSignal(audio_path_or_array, sample_rate)
    else:
        raise ValueError("Input must be a file path, AudioSignal, tensor, or ndarray")
    
    if force_mono:
        sig = sig.to_mono()

    sig = sig.normalize(-24)

    # Apply salient excerpt if specified
    if salient_excerpt_duration:
        return at_salient_excerpt(sig, duration=salient_excerpt_duration, loudness_cutoff=0)

    return sig

#hacking audiotools salient excerpt to work on AudioSignal type 
def random_state(seed: Union[int, np.random.RandomState]):
    """
    Turn seed into a np.random.RandomState instance.

    Parameters
    ----------
    seed : typing.Union[int, np.random.RandomState] or None
        If seed is None, return the RandomState singleton used by np.random.
        If seed is an int, return a new RandomState instance seeded with seed.
        If seed is already a RandomState instance, return it.
        Otherwise raise ValueError.

    Returns
    -------
    np.random.RandomState
        Random state object.

    Raises
    ------
    ValueError
        If seed is not valid, an error is thrown.
    """
    if seed is None or seed is np.random:
        return np.random.mtrand._rand
    elif isinstance(seed, (numbers.Integral, np.integer, int)):
        return np.random.RandomState(seed)
    elif isinstance(seed, np.random.RandomState):
        return seed
    else:
        raise ValueError(
            "%r cannot be used to seed a numpy.random.RandomState" " instance" % seed
        )

def at_excerpt(signal: AudioSignal,
            offset: float = None,
            duration: float = None,
            state: Union[np.random.RandomState, int] = None):
    signal = signal.clone()
    total_duration = signal.duration
    state = random_state(state)
    lower_bound = 0 if offset is None else offset
    upper_bound = max(total_duration - duration, 0)
    offset = state.uniform(lower_bound, upper_bound)

        # Convert offset and duration to number of samples
    offset_samples = int(offset * signal.sample_rate)
    duration_samples = int(duration * signal.sample_rate)
    signal.audio_data = signal.audio_data[..., offset_samples:offset_samples + duration_samples]

    signal.metadata["offset"] = offset
    signal.metadata["duration"] = duration
    return signal

def at_salient_excerpt(
        sig: AudioSignal,
        duration: int, 
        loudness_cutoff: float = None,
        num_tries: int = 8,
        state: Union[np.random.RandomState, int] = None):

    state = random_state(state)
    if loudness_cutoff is None:
        excerpt = at_excerpt(sig, duration=duration, state=state)
    else:
        loudness = -np.inf
        num_try = 0
        while loudness <= loudness_cutoff:
            excerpt = at_excerpt(sig, duration=duration, state=state)
            loudness = excerpt.loudness()
            num_try += 1
            if num_tries is not None and num_try >= num_tries:
                break
    return excerpt
