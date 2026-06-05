# FXplorer Architecture Documentation

This document provides in-depth technical details about FXplorer's architecture, data flow, and key implementation decisions.

## Table of Contents
1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [Frontend Architecture](#frontend-architecture)
4. [Data Flow](#data-flow)
5. [Key Algorithms](#key-algorithms)
6. [API Reference](#api-reference)

---

## System Overview

FXplorer uses a **three-stage pipeline** to create interactive 2D semantic spaces of audio effects:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Stage 1   │────▶│   Stage 2   │────▶│   Stage 3   │
│  Generate   │     │    Embed    │     │   Reduce    │
│ FX Samples  │     │   Samples   │     │   to 2D     │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
  Audio Files         Embeddings          Coordinates
  + Metadata          (.npy arrays)       (coords.json)
```

### Design Philosophy

1. **Offline + Online Hybrid**: Heavy computation (FX rendering, embedding) happens offline; lightweight operations (interpolation, playback) happen in-browser
2. **Separation of Concerns**: Backend handles ML/DSP, frontend handles UI/UX and real-time audio
3. **Deterministic Randomness**: All random generation is seeded for reproducibility
4. **Perceptual Accuracy**: LUFS normalization + FX-aware interpolation ensure perceptually meaningful results

---

## Backend Architecture

### Core Modules

#### 1. FX Generation (`fxplorer/applyfx/fx_generator.py`)

**Purpose**: Generate audio samples with Pedalboard FX chains

**Key Classes**:
- `FXChainGenerator`: Main API for FX chain creation and rendering

**Workflow**:
```python
# Initialize with dry audio + normalization settings
gen = FXChainGenerator(
    dry_audio_path="piano.wav",
    normalize_dry=True,        # Normalize input to target LUFS
    target_lufs=-14.0,
    normalize_output=True,     # Normalize output after FX
    rng_seed=42               # Deterministic randomness
)

# Three usage modes:

# 1. Manual chain with specific FX
board, params = gen.build_chain(
    chain_spec=["eq:3", "compressor", "reverb"],
    apply_rand_params=True  # Randomize within smart ranges
)

# 2. Random chain generation
board, params = gen.generate_random_chain(
    chain_complexity=2,  # Number of FX in chain
    allowed_effect_types=["gain", "eq:6", "reverb"]
)

# 3. Parameter sweep for dataset creation
sweep_results = gen.generate_param_sweep(
    chain_spec=["eq:3"],
    fx_mod_to_sweep="eq:3",
    param_to_sweep="bands.0.gain_db",
    values=[-12, -6, 0, 6, 12]
)
```

**Smart Parameter Ranges**:
Each FX type has carefully tuned parameter ranges for musical results:
- **EQ bands**: Frequencies distributed across spectrum, Q values 0.5-4.0, gains ±12dB
- **Compressor**: Threshold -40 to -10 dB, ratio 2:1 to 10:1, attack 1-50ms, release 50-500ms
- **Reverb**: Room size 0.3-0.95, damping 0.2-0.8, wet 0.2-0.7
- **Distortion**: Drive 3-40 dB (exponential distribution for perceptual evenness)

**LUFS Normalization**:
```python
# Two-stage normalization prevents extreme volume variations
dry_audio = normalize_lufs(dry_audio, sr, target_lufs=-14.0)  # Stage 1
fx_audio = apply_fx_chain(dry_audio, board)
if normalize_output:
    fx_audio = normalize_lufs(fx_audio, sr, target_lufs=-14.0)  # Stage 2
```

#### 2. Embedders (`fxplorer/embedders/`)

**LAION-CLAP** (`laion_clap.py`):
- Joint text-audio embedding space
- 512-dimensional embeddings
- Enables text-based semantic search
- Preprocessing: 48kHz mono, 10-second excerpts

**AFx-Rep** (`st_ito` model loaded via `fxplorer/pipeline/2_embed_samples.py` and `backend.py`):
- Audio-only effect representation learning
- Trained specifically on audio effects
- Better for perceptual FX similarity (no text modality)

**Why Two Models?**
- CLAP: User-facing text search ("warm reverb", "bright compressed piano")
- AFx-Rep: Audio similarity clustering (groups perceptually similar FX chains)

#### 3. Pipeline Stages (`fxplorer/pipeline/`)

**Stage 1: Generate Samples** (`1_generate_samples.py`)
```bash
python -m fxplorer.pipeline.1_generate_samples fxplorer/configs/examples/random_chain.yaml

# CLI flags override the YAML for quick runs:
python -m fxplorer.pipeline.1_generate_samples fxplorer/configs/examples/random_chain.yaml \
    --dry-audio assets/salsa_piano.wav \
    --output-dir _outputs/my_run \
    --num-samples 200
```

Output:
- `manifests/manifest_inmem.pkl` - In-memory manifest with rendered audio arrays and FX parameters
- `manifests/manifest_meta.json` - Metadata-only JSON reference

**Stage 2: Embed Samples** (`2_embed_samples.py`)
```bash
python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder clap
python -m fxplorer.pipeline.2_embed_samples <run_dir> --embedder afxrep
```

Output: `manifests/manifest_inmem.pkl` updated in place with CLAP or AFx-Rep embeddings

**Stage 3: Reduce to 2D** (`3_reduce_embeddings.py`)
```bash
python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --embedder clap --method pca
python -m fxplorer.pipeline.3_reduce_embeddings <run_dir> --embedder afxrep --method pca
```

Output:
- `coords.json` - 2D coordinates for visualization
- `pca_model.pkl` - Scaler and trained reducer for projecting new points
- `pca_embeddings.npy`, `pca_embeddings_norm.npy` - Raw and normalized reduced coordinates
- `coords_min.npy`, `coords_span.npy` - Normalization params

**Why PCA over t-SNE/UMAP?**
- **Deterministic**: Same data → same layout every time
- **Projectible**: Can map new points into existing space
- **Fast**: Scales to thousands of samples
- **Linear**: Preserves global structure (UMAP can distort distances)

#### 4. Backend API (`backend.py`)

**Flask REST API** serving the frontend:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Server health check |
| `/api/modes` | GET | Available embedding modes (CLAP, AFx-Rep) |
| `/api/configs` | GET | Frontend-visible generation presets |
| `/api/coords?mode=<mode>` | GET | 2D coordinates for given embedding mode |
| `/api/manifest` | GET | Sample metadata + FX parameters |
| `/api/sample/<idx>` | GET | Metadata, params, coordinates, and audio URL for one sample |
| `/api/audio/<idx>` | GET | Stream audio file by index |
| `/api/dry` | GET | Stream the current dry source |
| `/api/dry_info` | GET | Metadata and basic level stats for the dry source |
| `/api/search` | POST | Text search (CLAP) or audio similarity search (AFx-Rep) |
| `/api/ghost_point` | POST | Project edited params into 2D space |
| `/api/text_point` | POST | Project text query into 2D space (CLAP) |
| `/api/session/run_pipeline` | POST | Trigger full pipeline from upload |

**Upload Caching**:
```python
# Hash-based deduplication prevents redundant pipeline runs
upload_hash = hashlib.sha256(audio_bytes + config_bytes).hexdigest()
if upload_hash in cache:
    return cached_run_dir  # Reuse existing run
else:
    run_full_pipeline()
    cache[upload_hash] = run_dir
```

---

## Frontend Architecture

### Component Hierarchy

```
App.svelte (Root)
├── UploadPanel.svelte          # File upload + pipeline trigger
├── Visualization.svelte        # 2D scatter plot (Canvas/WebGL)
├── Inspector.svelte            # Sidebar
│   ├── PresetManager.svelte    # Preset save/load
│   └── Interpolation Controls  # A/B point selection + slider
├── UnifiedFxPanel.svelte       # FX parameter display (bottom)
│   ├── Visual knobs (top)
│   └── Expandable details (bottom)
└── WaveformMonitor.svelte      # Audio waveform with playhead
```

### State Management

**Reactive Stores** (Svelte's built-in reactivity):

```javascript
// Main state container
let selectedSample = null;     // Currently selected sample
let hoveredSample = null;      // Sample under cursor
let interpolationPointA = null;        // Interpolation endpoint A
let interpolationPointB = null;        // Interpolation endpoint B
let interpolationSlider = 0;           // Interpolation blend position (0-1)
let editableParams = null;     // Live-editable FX params

// Reactive computations (auto-update when dependencies change)
$: fxRackState = interpolationActive && interpolationPreviewEntries.length > 0
    ? 'interpolation'                  // Show interpolated params
    : hoveredSample
    ? 'hover'                  // Hover takes priority (real-time preview)
    : selectedSample
    ? 'selected'               // Show selected params
    : 'none';
```

**Why No Redux/Zustand?**
- Svelte's reactivity is sufficient for this scale
- No deep prop drilling (component tree is shallow)
- Reactive statements (`$:`) are more concise than actions/reducers

### Audio Engine (`lib/audioPlayer.js`)

**Tone.js Architecture**:

```javascript
// Dual-mode playback system
class AudioPlayerService {
    // Preview mode: Short hover previews (5 seconds)
    previewPlayer = new Tone.Player().connect(previewFXChain);

    // Full mode: Selected sample loop
    fullPlayer = new Tone.Player({ loop: true }).connect(fullFXChain);

    // Shared clock for smooth transitions
    clock = Tone.Transport;
}
```

**FX Chain Building**:
```javascript
// Convert backend Pedalboard params → Tone.js nodes
function buildToneChain(pedalboardParams) {
    const chain = [];

    for (const [pluginName, params] of Object.entries(pedalboardParams)) {
        if (pluginName === 'Gain') {
            chain.push(new Tone.Volume(params.gain_db));
        } else if (pluginName === 'Compressor') {
            const comp = new Tone.Compressor({
                threshold: params.threshold_db,
                ratio: params.ratio,
                attack: params.attack_ms / 1000,
                release: params.release_ms / 1000
            });
            chain.push(comp);
        }
        // ... more FX types
    }

    return chain;
}
```

**Waveform Caching**:
```javascript
const waveformCache = new Map();  // index → waveform points

async function updatePlaybackState() {
    const activeIndex = activeSample?.index;

    if (waveformCache.has(activeIndex)) {
        waveformPoints = waveformCache.get(activeIndex);  // Cache hit
    } else {
        const { waveform } = await audioPlayer.getWaveformData(activeIndex, 340);
        waveformCache.set(activeIndex, waveform);  // Cache miss → fetch
        waveformPoints = waveform;
    }
}
```

### Interpolation Engine (`lib/interpolationEngine.js`)

**Perceptual Interpolation Algorithm**:

```javascript
function interpolateBetween(paramsA, paramsB, t) {
    // t ∈ [0, 1]: 0 = fully A, 1 = fully B

    const result = {};

    for (const [pluginName, paramsA_plugin] of Object.entries(paramsA)) {
        const paramsB_plugin = paramsB[pluginName];

        if (!paramsB_plugin) {
            // Plugin only in A → scale by (1-t)
            result[pluginName] = scalePlugin(paramsA_plugin, 1 - t);
            continue;
        }

        // Both chains have this plugin → interpolate parameters
        result[pluginName] = interpolatePlugin(
            pluginName,
            paramsA_plugin,
            paramsB_plugin,
            t
        );
    }

    // Handle plugins only in B
    for (const [pluginName, paramsB_plugin] of Object.entries(paramsB)) {
        if (!paramsA[pluginName]) {
            result[pluginName] = scalePlugin(paramsB_plugin, t);
        }
    }

    return result;
}
```

**FX-Aware Scaling**:

| FX Type | Strategy | Rationale |
|---------|----------|-----------|
| **EQ** | Log-scale frequency, linear Q/gain | Frequency is perceptual (octaves), Q/gain are linear |
| **Compressor** | Linear threshold/ratio, exponential attack/release | Time constants are perceptual (exponential) |
| **Reverb** | Exponential decay, linear room size | Decay time is exponential, room size is linear |
| **Distortion** | Exponential drive | Drive is perceptual (dB scale) |
| **Delay** | Linear time, exponential feedback | Time is linear, feedback affects energy exponentially |

**Example: EQ Band Interpolation**:
```javascript
function interpolateEQBand(bandA, bandB, t) {
    return {
        // Frequency: Log-scale (perceptual octaves)
        frequency_hz: Math.exp(
            (1 - t) * Math.log(bandA.frequency_hz) +
            t * Math.log(bandB.frequency_hz)
        ),

        // Q and gain: Linear
        Q: (1 - t) * bandA.Q + t * bandB.Q,
        gain_db: (1 - t) * bandA.gain_db + t * bandB.gain_db
    };
}
```

### Parameter Mapping (`lib/paramMapper.js`)

**Problem**: Pedalboard (backend) and Tone.js (frontend) have different DSP implementations

**Compensations Applied**:

1. **Highpass/Lowpass Filters**:
```javascript
// Pedalboard: 6dB/oct Butterworth
// Tone.js: 12dB/oct by default

// Compensation: Reduce Q to approximate 6dB/oct rolloff
function mapFilter(pedalboardParams) {
    return new Tone.Filter({
        frequency: pedalboardParams.cutoff_hz,
        type: 'highpass',
        Q: 0.5  // ← Reduced from default 1.0 to match Pedalboard's gentler slope
    });
}
```

2. **Parametric EQ**:
```javascript
// Compensation: Boost Q and gain by 10-20% to match Pedalboard curves
function mapEQBand(band) {
    return new Tone.EQ3({  // Using EQ3 as approximation
        frequency: band.frequency_hz,
        Q: band.Q * 1.15,           // ← 15% boost
        gain: band.gain_db * 1.1    // ← 10% boost
    });
}
```

3. **Compressor**:
```javascript
// Compensation: Softer attack/release, wider knee
function mapCompressor(params) {
    return new Tone.Compressor({
        threshold: params.threshold_db,
        ratio: params.ratio,
        attack: params.attack_ms / 1000 * 1.2,    // ← 20% slower
        release: params.release_ms / 1000 * 1.2,  // ← 20% slower
        knee: 6  // ← Wider knee for smoother compression
    });
}
```

4. **Reverb**:
```javascript
// Compensation: Nonlinear decay mapping
function mapReverb(params) {
    const decay = Math.pow(params.room_size, 1.5) * 5;  // ← Exponential mapping

    return new Tone.Reverb({
        decay: decay,
        preDelay: 0.01,
        wet: params.wet_level
    });
}
```

**Why Compensations Are Needed**:
- Different filter implementations (Butterworth vs Biquad)
- Different oversampling strategies
- Different nonlinear modeling (distortion, compression)
- Frontend must match backend perceptually, not mathematically

---

## Data Flow

### Pipeline Flow (Offline)

```
User Uploads → Backend receives → Hash check
                                      ↓
                              Cached? → Yes → Return existing run
                                      ↓ No
                              Run 3-stage pipeline:

1. Generate (Pedalboard)      → audio/*.wav + manifest.json
2. Embed (CLAP/AFx-Rep)      → embeddings/*.npy + manifest_with_embeddings.json
3. Reduce (PCA/UMAP)         → coords.json + pca_model.pkl
                                      ↓
                              Return run_id to frontend
```

### Interaction Flow (Online)

```
User hovers point → Frontend sends audio request
                         ↓
                    Backend streams audio
                         ↓
                    Frontend builds Tone.js FX chain
                         ↓
                    Playback starts (preview mode)
                         ↓
User clicks point  → Switch to full mode (looping)
                         ↓
User edits params  → Debounced live update (75ms)
                         ↓
                    Apply new params to Tone.js chain
```

### Interpolation Flow

```
User sets point A → Store params A
User sets point B → Store params B
User drags slider → interpolationEngine.interpolateBetween(A, B, t)
                         ↓
                    Update preview params
                         ↓
Slider released   → Apply interpolated params to audio
                         ↓
                    Playback with blended FX chain
```

---

## Key Algorithms

### 1. LUFS Normalization

```python
def normalize_lufs(audio, sr, target_lufs=-14.0):
    """
    Normalize audio to target loudness using EBU R128 LUFS standard.

    Why LUFS instead of peak normalization?
    - Perceptually uniform loudness
    - Prevents samples from sounding too quiet or too loud
    - Industry standard for broadcast/streaming
    """
    meter = pyloudnorm.Meter(sr)
    current_lufs = meter.integrated_loudness(audio)
    delta_lufs = target_lufs - current_lufs
    gain_linear = 10 ** (delta_lufs / 20)
    return audio * gain_linear
```

### 2. Text Projection (CLAP)

```python
def project_text_to_2d(text_query, pca_model, clap_model):
    """
    Project text query into existing 2D space.

    Steps:
    1. Embed text using CLAP text encoder
    2. Project embedding using trained PCA model
    3. Normalize to [0, 1] range for visualization
    """
    text_embedding = clap_model.get_text_embedding(text_query)  # 512-dim
    coords_2d = pca_model.transform(text_embedding)             # 2-dim
    coords_normalized = (coords_2d - coords_min) / coords_span  # [0, 1]
    return coords_normalized
```

### 3. Deterministic Random Chain Generation

```python
def generate_random_chain(self, chain_complexity=2, allowed_fx=None, allow_repeats=False):
    """
    Generate deterministic random FX chain.

    Determinism via seeded RNG ensures:
    - Reproducible experiments
    - Consistent results across runs
    - Version control friendly (same seed → same audio)
    """
    np.random.seed(self.rng_seed)  # Deterministic seed

    fx_pool = allowed_fx or self.base_effect_types

    if allow_repeats:
        chain = self.rng.choice(fx_pool, size=chain_complexity)
    else:
        chain = self.rng.choice(fx_pool, size=chain_complexity, replace=False)

    return self.build_chain(chain, apply_rand_params=True)
```

---

## API Reference

See `backend.py` for full implementation details. Key endpoints:

### GET `/api/coords?mode=<mode>`

Returns 2D coordinates for visualization.

**Response**:
```json
[
    {"x": 0.234, "y": 0.567},
    {"x": 0.891, "y": 0.123},
    ...
]
```

### GET `/api/manifest`

Returns sample metadata with FX parameters.

**Response**:
```json
[
    {
        "index": 0,
        "name": "sample_000",
        "audio_path": "audio/sample_000.wav",
        "type": "generated",
        "params": {
            "plugins": {
                "Gain": {"gain_db": 3.2},
                "Reverb": {"room_size": 0.7, "wet_level": 0.4}
            }
        }
    },
    ...
]
```

### POST `/api/text_point`

Project text query into 2D space (CLAP only).

**Request**:
```json
{
    "text": "warm roomy piano",
    "mode": "clap",
    "k": 5
}
```

**Response**:
```json
{
    "coords": {"x": 0.456, "y": 0.789},
    "nearest": [0, 23, 45, 67, 89],  // Indices of k-nearest samples
    "text": "warm roomy piano",
    "mode": "clap"
}
```

### POST `/api/search`

Unified search endpoint. JSON requests run CLAP text search or AFx-Rep reference search; multipart requests run AFx-Rep audio-upload search.

**Request**:
```json
{
    "query": "warm roomy piano",
    "mode": "clap",
    "k": 10
}
```

**Response**:
```json
{
    "results": [
        {"idx": 0, "score": 0.98, "sample": {...}}
    ],
    "mode": "clap",
    "query": "warm roomy piano"
}
```

### POST `/api/ghost_point`

Render edited FX parameters, embed the rendered audio in the selected space, and project the point into the current 2D reducer.

---

## Performance Considerations

### Backend Optimizations

1. **Batch Embedding**: Process multiple samples in parallel (GPU batching)
2. **Upload Caching**: Hash-based deduplication avoids redundant pipeline runs
3. **Lazy Model Loading**: Models loaded on first use, not at startup
4. **Waveform Downsampling**: The frontend decodes audio buffers and caches compact waveform summaries for visualization

### Frontend Optimizations

1. **Waveform Caching**: In-memory cache prevents redundant fetch/decode work
2. **Debounced Parameter Updates**: 75ms debounce on live editing prevents audio glitches
3. **Audio Buffer Caching**: Tone.js buffers cached per sample
4. **Reactive State**: Only re-render components when dependencies change

### Disk Space Management

- **Problem**: 53+ run directories, each 100-500MB
- **Solution**: `scripts/cleanup_old_runs.py` with configurable retention policies
- **Recommendation**: Keep last 5 runs or 7 days of data

---

## Future Architecture Considerations

### Scalability

**Current Limitations**:
- Frontend handles ~500 samples max before canvas rendering slows
- Backend PCA doesn't scale beyond ~10k samples efficiently
- No distributed processing for pipeline stages

**Potential Solutions**:
- WebGL-based visualization for 10k+ points
- Incremental PCA or UMAP approximations
- Distributed embedding with Ray or Dask

### Storage

**Current**: Local filesystem storage (manifest pickle with audio arrays, metadata JSON, and reducer outputs)

**Alternative**:
- HDF5 for efficient tensor storage
- SQLite for metadata queries
- Cloud storage (S3) for large-scale datasets

### Real-Time FX

**Current**: Offline Pedalboard rendering, online Tone.js playback

**Alternative**:
- Web Audio Worklets for high-quality browser FX
- JUCE-based VST host for plugin support
- Server-side streaming with low-latency FX

---

**Last Updated**: 2025-12-10
**Version**: 1.0
