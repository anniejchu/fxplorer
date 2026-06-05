<script>
  /**
   * Root component and state container for FXplorer.
   *
   * Main orchestrator for FXplorer. Manages:
   * - Sample data loading (coords, manifest from backend)
   * - Audio playback (preview + full modes via audioPlayer.js)
   * - User interactions (hover, click, interpolation, search)
   * - Parameter editing (live updates with debouncing)
   * - Waveform visualization (cached for performance)
   *
   * COMPONENT TREE:
   * App (this file)
   * ├── UploadPanel (file upload + pipeline trigger; modal on first run)
   * ├── Visualization (2D scatter plot canvas)
   * ├── Inspector (sidebar with interpolation controls)
   * ├── UnifiedFxPanel (FX params display at bottom)
   * └── WaveformMonitor (audio waveform with playhead)
   *
   */

  import { onMount } from 'svelte';
  import Visualization from './components/Visualization.svelte';
  import Inspector from './components/Inspector.svelte';
  import UploadPanel from './components/UploadPanel.svelte';
  import WaveformMonitor from './components/WaveformMonitor.svelte';
  import InterpolationIndicator from './components/InterpolationIndicator.svelte';
  import SpecialPointsNav from './components/SpecialPointsNav.svelte';
  import { audioPlayer } from './lib/audioPlayer.js';
  import { interpolateBetween, scaleParamsForDryWet } from './lib/interpolationEngine.js';
  import { getChainKeyFromParams } from './lib/fxUtils.js';
  import { canPairInterpolation, haveSameFxChain, isDryParams } from './lib/interpolationUtils.js';
  import { deriveSampleIndex } from './lib/sampleUtils.js';
  import { presetStore } from './lib/presetStore.js';
  import {
    buildPreviewEntries,
    buildEditGhostParams,
    calculateGhostPoint,
    cloneParams,
    computeInterpolationGhostCoords,
    getSampleParams,
    setValueAtPath
  } from './lib/appUtils.js';
  import { api } from './lib/api.js';
  import {
    ARROW_KEY_RATE,
    AUDIO_UPDATE_DEBOUNCE,
    DEFAULT_MODE,
    EDIT_GHOST_DEBOUNCE,
    MAX_INTERPOLATION_PREVIEW_ENTRIES,
    INTERPOLATION_SLIDER_STEP,
    INTERPOLATION_SNAP_EPSILON
  } from './lib/constants.js';

  const SIDEBAR_MIN = 280;
  const SIDEBAR_MAX = 520;
  let sidebarWidth = 360;
  let sidebarDragging = false;
  let sidebarEl = null;

  // Embedding and sample data
  let currentMode = DEFAULT_MODE;  // Current embedding mode (defaulted for frontend fallback)
  let availableModes = [];   // Available embedding modes from backend
  let samples = [];          // Array of sample metadata from manifest.json
  let coords = [];           // 2D coordinates for visualization
  let isInitializing = true; // Initial loading state
  let loading = false;       // Data fetch state (keeps UI mounted)
  let error = null;          // Global error message
  let hasPopulation = false; // Whether we have any samples to display
  let showGeneratePanel = true; // Show modal generate panel until samples exist

  // Sample selection and interaction
  let selectedSample = null;  // Currently selected sample (clicked)
  let hoveredSample = null;   // Sample under mouse cursor
  let lastHoveredSample = null; // Sticky hover for waveform display

  // Audio playback
  let hoverPlaybackMode = 'smooth';  // 'smooth' (crossfade) or 'restart' (immediate)
  let isPaused = false;              // Global pause state
  let fxBypass = false;              // Toggle FX on/off for A/B
  let fxBypassFlash = false;         // Brief UI indicator when toggled
  let fxBypassFlashTimer = null;
  let normalizePlayback = true;     // Toggle for loudness normalization
  let playbackState = {              // Playback info for waveform monitor
    mode: 'idle',                    // 'idle', 'preview' (hover), or 'full' (selected)
    position: 0,                     // Current playhead position in seconds
    duration: 0,                     // Total duration in seconds
    label: '',                       // Sample name for display
    hoverMode: hoverPlaybackMode
  };

  // Waveform visualization
  let waveformPoints = [];      // Array of waveform amplitude values
  let waveformLoading = false;  // Loading state for waveform fetch
  let waveformSampleIdx = null; // Index of sample currently shown in waveform
  let waveformRequestId = 0;    // Request ID to prevent race conditions
  let playheadUpdating = false; // Lock to prevent concurrent updates

  // Search (CLAP text and AFx-Rep audio)
  let searchResults = [];           // Indices of search result samples
  let virtualPoints = [];           // Text query points projected onto 2D space
  let textPrompt = '';              // User's text search query
  let textPlacementStatus = '';     // Success message
  let textPlacementError = '';      // Error message
  let textPlacementLoading = false; // Loading state for text embedding
  let audioSearchFile = null;       // Uploaded audio file for AFx-Rep search
  let audioSearchLoading = false;   // Loading state for audio search
  let audioSearchStatus = '';       // Status message for audio search
  let audioSearchError = '';        // Error message for audio search
  let audioPreviewUrl = null;       // Object URL for audio preview
  let audioPreviewPlaying = false;  // Whether audio preview is playing
  let audioPreviewElement = null;   // Reference to audio element

  // Special points navigation
  let specialPointsIndex = -1;     // Current index in special points array
  let showSpecialPointsNav = false; // Whether to show the navigation UI

  // Presets
  let presetRefreshToken = 0;
  let presetPointsRequestId = 0;

  // Live parameter editing
  let editableParams = null;  // Currently editable FX parameters (cloned from sample)
  let isLiveEditing = false;  // Whether live editing is active
  let audioUpdateTimer = null;   // Shared debounce timer for audio updates

  // Interpolating
  let interpolationPointA = null;         // Interpolation endpoint A {index, name, params, type}
  let interpolationPointB = null;         // Interpolation endpoint B
  let interpolationChainKey = null;       // Cached chain key for interpolation eligibility
  let interpolationSlider = 0;            // Blend position [0, 1]
  let interpolationStatus = '';           // Status message
  let interpolationError = '';            // Error message
  let interpolationActive = false;        // Whether interpolating is currently active
  let interpolationPreviewParams = null;  // Blended parameters at current slider position
  let interpolationPreviewPercent = 0;    // Slider position as percentage (0-100)
  let interpolationGhostCoords = null;    // Interpolated coordinates for ghost point on canvas
  let editGhost = null;           // Green ghost at selected point
  let isEditingParams = false;
  let editGhostTimer = null;
  let editGhostRequestId = 0;
  let editGhostLoading = false;
  let interpolationPointAIndex = null;    // Index of interpolation point A (for canvas)
  let interpolationPointBIndex = null;    // Index of interpolation point B (for canvas)

  // Keyboard interpolation mode state
  let keyboardInterpolationMode = false;  // Tracks if in keyboard interpolation mode
  let interpolationSliderStep = INTERPOLATION_SLIDER_STEP;     // 3% increment per arrow key
  let arrowKeyHeld = null;        // 'left' | 'right' | null
  let arrowKeyInterval = null;    // Interval for continuous updates

  // Audio update debouncing to reduce artifacts
  let lastSelectedIndex = null;
  let showFloatingControls = true;

  // Constants

  // Utility functions

  // Caches for performance (avoid redundant network requests)
  const waveformCache = new Map();  // sampleIndex → waveform points array
  const textProbeCache = new Map();  // query text → {coords, nearest, ...}

  // Reactive declarations

  // Interpolation state
  $: canInterpolate = Boolean(interpolationPointA?.params && interpolationPointB?.params);  // Can only interpolate if both points are set
  $: interpolationPreviewEntries = buildPreviewEntries(interpolationPreviewParams, MAX_INTERPOLATION_PREVIEW_ENTRIES);
  $: interpolationPointAIndex = typeof interpolationPointA?.index === 'number' ? interpolationPointA.index : null;
  $: interpolationPointBIndex = typeof interpolationPointB?.index === 'number' ? interpolationPointB.index : null;
  $: interpolationGhostCoords = computeInterpolationGhostCoords(coords, interpolationPointAIndex, interpolationPointBIndex, interpolationSlider);


  // FX Panel display state - determines which params to show at bottom of screen
  // IMPORTANT: Hover takes priority over selected for real-time preview feedback
  $: fxRackState = interpolationActive && interpolationPreviewEntries.length > 0
    ? 'interpolation'          // Show interpolated params when interpolating is active
    : hoveredSample    // Hover takes priority (real-time feedback)
    ? 'hover'
    : selectedSample   // Fall back to selected sample
    ? 'selected'
    : 'none';          // No params to display

  $: fxRackParams = (() => {
    if (fxRackState === 'interpolation' && interpolationPreviewParams) {
      return interpolationPreviewParams;
    }
    if (fxRackState === 'selected' && editableParams) {
      return editableParams;
    }
    if (fxRackState === 'hover') {
      return getSampleParams(hoveredSample);
    }
    if (fxRackState === 'selected') {
      return getSampleParams(selectedSample);
    }
    return null;
  })();

  $: fxRackSample = fxRackState === 'selected' || fxRackState === 'interpolation'
    ? selectedSample
    : fxRackState === 'hover'
    ? hoveredSample
    : null;

  $: fxRackReadonly = fxRackState === 'hover' || fxRackState === 'interpolation';

  // Special points: samples that are interpolated or have custom names
  $: specialPoints = samples.filter(s =>
    s.type === 'interpolation' ||
    s.type === 'edited' ||
    (s.customName && s.customName.trim() !== '')
  );

  // Auto-hide navigation when no special points exist
  $: if (specialPoints.length === 0) {
    showSpecialPointsNav = false;
    specialPointsIndex = -1;
  }
  $: if (hasPopulation && showGeneratePanel) {
    showGeneratePanel = false;
  }
  $: if (!selectedSample) {
    editableParams = null;
    isLiveEditing = false;
    isEditingParams = false;
  } else if (selectedSample?.index !== lastSelectedIndex) {
    lastSelectedIndex = selectedSample?.index ?? null;
    editableParams = cloneParams(getSampleParams(selectedSample) || {});
    isLiveEditing = false;
    isEditingParams = false;
  }

  onMount(() => {
    // Kick off initial data fetch + Tone polling once the component mounts.
    let stopTicker = null;
    (async () => {
      try {
        await initialize();
        stopTicker = startPlayheadTicker();
      } catch (err) {
        error = err.message;
        console.error('Initialization error:', err);
      }
    })();

    return () => {
      if (stopTicker) stopTicker();
    };
  });

  async function initialize() {
    isInitializing = true;
    
    // Get available modes for embedding spaces (CLAP vs AFX-REP)
    const modesData = await api.getModes();
    availableModes = modesData.modes;
    currentMode = modesData?.default || DEFAULT_MODE;

    // Initialize audio player in background. Tone.start() may require a user gesture
    // in some browsers; do not block the UI on it. Audio will be enabled on first
    // user interaction (click/play) when Tone.start() can succeed.
    audioPlayer.setNormalizePlayback(normalizePlayback);
    audioPlayer.init().catch((err) => {
      // Defer audio init until user gesture; log for debugging.
      console.warn('Audio initialization deferred (awaiting user gesture):', err);
    });

    isInitializing = false;
  }

  function startPlayheadTicker() {
    updatePlaybackState();
    const id = setInterval(updatePlaybackState, 120);
    return () => clearInterval(id);
  }

  async function updatePlaybackState() {
    if (playheadUpdating) return;
    playheadUpdating = true;

    const status = audioPlayer.getStatus();
    let mode = 'idle';
    let position = 0;
    let duration = 0;
    let activeSample = null;

    if (status.full) {
      mode = 'full';
      position = status.full.position;
      duration = status.full.duration;
      activeSample = selectedSample;
    } else if (status.preview) {
      mode = 'preview';
      position = status.preview.position;
      duration = status.preview.duration;
      activeSample = hoveredSample || lastHoveredSample;
    }

    playbackState = {
      mode,
      position,
      duration,
      label: activeSample?.name || '',
      hoverMode: hoverPlaybackMode,
      fxBypass
    };

    // Determine which waveform to show:
    // - Interpolation mode or saved interpolations: show dry audio waveform (use 'dry' as key)
    // - Edited samples: show original sample's waveform (derivedFrom)
    // - Regular samples: show their own waveform (index)
    let waveformKey = null;
    if (mode !== 'idle') {
      if (interpolationActive || keyboardInterpolationMode || activeSample?.type === 'interpolation') {
        waveformKey = 'dry';
      } else if (typeof activeSample?.derivedFrom === 'number') {
        waveformKey = activeSample.derivedFrom;
      } else if (typeof activeSample?.index === 'number') {
        waveformKey = activeSample.index;
      } else {
        waveformKey = 'dry';
      }
    }

    if (waveformKey === null) {
      waveformPoints = [];
      waveformSampleIdx = null;
      waveformLoading = false;
    } else if (waveformKey !== waveformSampleIdx) {
      const cached = waveformCache.get(waveformKey);
      if (cached) {
        waveformPoints = cached;
        waveformSampleIdx = waveformKey;
        waveformLoading = false;
      } else {
        waveformLoading = true;
        const reqId = ++waveformRequestId;
        try {
          const { waveform } = waveformKey === 'dry'
            ? await audioPlayer.getWaveformData('dry', 340)
            : await audioPlayer.getWaveformData(waveformKey, 340);
          if (reqId === waveformRequestId) {
            waveformCache.set(waveformKey, waveform);
            waveformPoints = waveform;
            waveformSampleIdx = waveformKey;
            waveformLoading = false;
          }
        } catch (err) {
          if (reqId === waveformRequestId) {
            waveformLoading = false;
            waveformPoints = [];
          }
          console.error('Waveform fetch failed:', err);
        }
      }
    }

    playheadUpdating = false;
  }

  const resetPlaybackSelection = () => {
    audioPlayer.stop();
    audioPlayer.clearCache();
    hoveredSample = null;
    selectedSample = null;
  };

  const bumpPresetRefresh = () => {
    presetRefreshToken = Date.now();
  };

  const getPresetPlugins = (params) => {
    if (!params) return null;
    if (params.plugins && typeof params.plugins === 'object') return params.plugins;
    return params;
  };

  const buildPresetParamsFromSample = (sample) => {
    if (!sample) return null;
    const baseParams = sample?.params || {};
    const plugins = getSampleParams(sample);
    if (!plugins || Object.keys(plugins).length === 0) return null;
    const chain = baseParams?.chain;
    if (Array.isArray(chain) && chain.length > 0) {
      return {
        ...baseParams,
        chain,
        plugins: cloneParams(plugins)
      };
    }
    return cloneParams(plugins);
  };

  const autoSavePreset = (name, sample) => {
    const trimmed = String(name || '').trim();
    if (!trimmed) return;
    const params = buildPresetParamsFromSample(sample);
    if (!params) return;
    try {
      presetStore.savePreset(trimmed, params, {
        auto: true,
        source: sample?.type || 'sample'
      });
      bumpPresetRefresh();
    } catch (err) {
      console.error('Auto preset save failed:', err);
    }
  };

  const injectPresetPoints = async (mode, baseSamples, baseCoords) => {
    const requestId = ++presetPointsRequestId;
    const presets = presetStore.getAllPresets();
    if (!presets.length || !Array.isArray(baseSamples) || !baseSamples.length) return;

    const baseSample = baseSamples.find(
      (sample) => sample?.params?.chain && getSampleParams(sample)
    );
    const baseChain = baseSample?.params?.chain || null;
    const baseKey = baseSample ? getChainKeyFromParams(getSampleParams(baseSample) || {}) : null;

    const additions = [];
    const newCoords = [];

    for (const preset of presets) {
      if (requestId !== presetPointsRequestId) return;
      const storedParams = preset?.params || {};
      const plugins = getPresetPlugins(storedParams);
      if (!plugins || Object.keys(plugins).length === 0) continue;

      if (baseKey) {
        const presetKey = getChainKeyFromParams(plugins);
        if (presetKey !== baseKey) continue;
      }

      const chain = storedParams?.chain || baseChain;
      if (!Array.isArray(chain) || chain.length === 0) continue;

      const params = {
        ...storedParams,
        chain,
        plugins: cloneParams(plugins)
      };

      const point = await calculateGhostPoint(api, mode, params);
      if (!point) continue;

      const idx = baseSamples.length + additions.length;
      additions.push({
        idx,
        index: idx,
        id: preset.id || Date.now() + idx,
        name: preset.name,
        customName: preset.name,
        type: 'preset',
        presetId: preset.id,
        params
      });
      newCoords.push(point);
    }

    if (requestId !== presetPointsRequestId) return;
    if (additions.length) {
      samples = [...baseSamples, ...additions];
      coords = [...baseCoords, ...newCoords];
    }
  };

  async function loadModeData(mode) {
    // Pull coords + manifest for a given embedding space (CLAP or AFx-Rep).
    loading = true;
    try {
      resetVirtualHighlights();
      resetInterpolationControls();
      const [coordsData, manifestData] = await Promise.all([
        api.getCoords(mode),
        api.getManifest()
      ]);

      coords = coordsData;
      samples = (manifestData || []).map((item, idx) => ({ ...item, idx, index: idx }));
      currentMode = mode;
      hasPopulation =
        (Array.isArray(coordsData) && coordsData.length > 0) ||
        (Array.isArray(manifestData) && manifestData.length > 0);
      await injectPresetPoints(mode, samples, coords);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function handleModeChange(newMode) {
    if (newMode !== currentMode) {
      resetVirtualHighlights();
      resetInterpolationControls();
      resetPlaybackSelection();
      isPaused = false;
      loadModeData(newMode);
    }
  }

  async function handlePipelineGenerate(event) {
    // Accepts upload-panel events, calls backend pipeline, and reloads the map.
    const {
      file,
      configId,
      targetSamples,
      embedModes,
      allowedFx,
      reductionMethod,
      explorationMode,
      sampleCounts,
      selectedFx,
      combinations,
      onComplete,
      onError
    } = event.detail;
    error = null;
    resetPlaybackSelection();
    hasPopulation = false;
    resetVirtualHighlights();
    resetInterpolationControls();
    editableParams = null;
    isLiveEditing = false;

    try {
      const resp = await api.runPipeline(
        file,
        configId,
        embedModes,
        targetSamples,
        allowedFx,
        reductionMethod,
        explorationMode,
        sampleCounts,
        selectedFx,
        combinations
      );
      const embedList = Array.isArray(embedModes) ? embedModes : String(embedModes || '').split(',').filter(Boolean);

      if (resp.available_modes && resp.available_modes.length) {
        availableModes = resp.available_modes;
      } else if (embedList.length) {
        availableModes = embedList;
      } else {
        const modesData = await api.getModes();
        availableModes = modesData.modes;
      }

      const nextMode =
        resp?.default_mode ||
        (embedList.includes('afxrep') && 'afxrep') ||
        (embedList.includes('clap') && 'clap') ||
        availableModes[0] ||
        currentMode;

      await loadModeData(nextMode);
      currentMode = nextMode;
      if (resp.num_samples && resp.num_samples > 0) {
        hasPopulation = true;
      }
      const count = resp.num_samples ?? coords.length;
      if (onComplete) {
        onComplete(`Loaded ${count} samples in ${nextMode.toUpperCase()} space (requested ~${targetSamples}).`);
      }
      showGeneratePanel = false;
    } catch (err) {
      error = err.message;
      if (onError) onError(err.message);
      showGeneratePanel = true;
    }
  }

  function handleSampleHover(event) {
    // Hovering a node starts a quiet preview and updates tooltip state.
    const { sample, index } = event.detail;
    const selectingInterpolationPoint = (interpolationPointA && !interpolationPointB) || (interpolationPointB && !interpolationPointA);
    if (selectingInterpolationPoint && sample) {
      const anchorParams = interpolationPointA?.params || interpolationPointB?.params || {};
      const baseKey = interpolationChainKey || getChainKeyFromParams(anchorParams);
      const rawCandidateParams = sample?.params?.plugins || sample?.params || {};
      const candidateKey = isDryParams(rawCandidateParams)
        ? 'dry'
        : getChainKeyFromParams(rawCandidateParams);
      if (baseKey && baseKey !== 'dry' && candidateKey !== 'dry' && candidateKey !== baseKey) {
        return;
      }
    }
    hoveredSample = { ...sample, index };
    lastHoveredSample = hoveredSample;
    isPaused = false;
    interpolationActive = false;

    // Play audio preview on hover
    // For saved interpolations without backend audio, playPreview will use dry audio + FX
    if (sample) {
      const idx = sample.type === 'interpolation' || sample.type === 'preset' ? 'dry' : index;
      if (idx !== null) {
        audioPlayer.playPreview(
          idx,
          getSampleParams(sample) || {},
          { restart: hoverPlaybackMode === 'restart' }
        );
      }
    }
  }

  function handleSampleLeave() {
    hoveredSample = null;
    if (isPaused) {
      return;
    }
    if (selectedSample) {
      audioPlayer.stopPreview();
      if ((isEditingParams || isLiveEditing) && editableParams) {
        scheduleLivePreview(true);
      } else if (selectedSample?.type === 'interpolation') {
        audioPlayer.setInterpolationParams(getSampleParams(selectedSample) || {});
      } else if (typeof selectedSample?.index === 'number') {
        audioPlayer.playFull(selectedSample.index, getSampleParams(selectedSample) || {});
      }
    }
  }

  function handleSampleClick(event) {
    // Clicking pins the selection + starts the full loop (Tone Player).
    const { sample, coord, index } = event.detail;
    selectedSample = { ...sample, index };
    isPaused = false;
    interpolationActive = false;
    isLiveEditing = false;
    isEditingParams = false;
    editGhostLoading = false;
    editableParams = cloneParams(getSampleParams(sample) || {});
    if (coord && typeof coord.x === 'number' && typeof coord.y === 'number') {
      editGhost = { x: coord.x, y: coord.y };
    } else if (typeof index === 'number' && coords[index]) {
      editGhost = { x: coords[index].x, y: coords[index].y };
    } else {
      editGhost = null;
    }

    // Play full audio on click
    // Saved interpolations don't have backend audio - use interpolation mode playback instead
    if (sample?.type === 'interpolation' || sample?.type === 'preset') {
      audioPlayer.setInterpolationParams(getSampleParams(sample) || {});
    } else if (index !== null) {
      audioPlayer.playFull(index, getSampleParams(sample) || {});
    }
  }

  function handlePause() {
    audioPlayer.pause();
    interpolationActive = false;
  }

  function handleNameChange(event) {
    const { index, name, isEditingParams: isEditing } = event.detail || {};
    if (typeof index !== 'number' || !name) return;
    if (!samples || !samples[index]) return;
    if (isEditing && editGhost && editableParams) {
      const baseParams = samples[index]?.params || {};
      const chain = baseParams.chain || [];
      const nextParams = {
        ...baseParams,
        chain,
        plugins: cloneParams(editableParams)
      };
      const newIndex = samples.length;
      const newSample = {
        ...samples[index],
        index: newIndex,
        idx: newIndex,
        name,
        customName: name,
        derivedFrom: index,
        params: nextParams,
        id: Date.now()
      };
      samples = [...samples, newSample];
      coords = [...coords, { x: editGhost.x, y: editGhost.y }];
      selectedSample = newSample;
      isEditingParams = false;
      editGhost = null;
      autoSavePreset(name, newSample);
      return;
    }

    const updated = { ...samples[index], customName: name, name };
    samples = [
      ...samples.slice(0, index),
      updated,
      ...samples.slice(index + 1)
    ];
    if (selectedSample?.index === index) {
      selectedSample = { ...selectedSample, customName: name, name };
    }
    if (hoveredSample?.index === index) {
      hoveredSample = { ...hoveredSample, customName: name, name };
    }
    autoSavePreset(name, updated);
  }

  function handleInterpolationSave(event) {
    const { name, pointA, pointB, percent } = event.detail || {};
    if (!name || !interpolationPreviewParams || !interpolationGhostCoords) return;

    // Get the chain from one of the interpolation points (they should have the same chain)
    // Find the original sample to get the full params structure
    const sourceIndex = typeof pointA?.index === 'number' ? pointA.index :
                       typeof pointB?.index === 'number' ? pointB.index : 0;
    const sourceParams = samples[sourceIndex]?.params || {};
    const chain = sourceParams.chain || [];

    // Create new sample with interpolated parameters
    const newIndex = samples.length;
    const newSample = {
      index: newIndex,
      idx: newIndex,
      name,
      customName: name,
      type: 'interpolation',
      derivedFrom: {
        pointA: pointA?.index ?? pointA?.name,
        pointB: pointB?.index ?? pointB?.name,
        percent
      },
      params: {
        chain,
        plugins: cloneParams(interpolationPreviewParams)
      },
      id: Date.now()
    };

    // Add to samples and coords arrays
    samples = [...samples, newSample];
    const newCoord = { x: interpolationGhostCoords.x, y: interpolationGhostCoords.y };
    coords = [...coords, newCoord];

    // Exit keyboard interpolation mode if active
    if (keyboardInterpolationMode) {
      keyboardInterpolationMode = false;
      if (arrowKeyInterval) {
        clearInterval(arrowKeyInterval);
        arrowKeyInterval = null;
      }
      arrowKeyHeld = null;
      resetCanvasZoom();
    }

    // Exit interpolation mode (clear all interpolation state)
    resetInterpolationControls();

    // Now select the new sample (similar to handleSampleClick)
    selectedSample = newSample;
    isPaused = false;
    isLiveEditing = false;
    isEditingParams = false;
    editGhostLoading = false;
    editableParams = cloneParams(getSampleParams(newSample) || {});
    editGhost = newCoord;

    // Play the newly saved interpolation sample
    audioPlayer.setInterpolationParams(getSampleParams(newSample) || {});
    autoSavePreset(name, newSample);
  }

  function resetVirtualHighlights() {
    // Remove cached probe overlays so the canvas always reflects current data.
    searchResults = [];
    virtualPoints = [];
    textPlacementStatus = '';
    textPlacementError = '';
    textProbeCache.clear();
    editableParams = null;
    isLiveEditing = false;
  }

  function applyTextProbeResult(resp, { fromCache = false } = {}) {
    const coords = resp?.coords || {};
    if (typeof coords.x !== 'number' || typeof coords.y !== 'number') {
      throw new Error('Backend returned no coordinates.');
    }
    const point = {
      id: Date.now(),
      coords: [coords.x, coords.y],
      text: resp?.text || textPrompt.trim(),
      mode: resp?.mode || 'clap'
    };
    virtualPoints = [...virtualPoints.slice(-3), point];
    searchResults = resp?.nearest || [];
    textPlacementStatus = fromCache
      ? `Loaded saved result for "${point.text}".`
      : `Placed "${point.text}" on the map.`;
    textPlacementError = '';
  }

  async function handleTextProjection() {
    // Drives the Quick Find box: embed text, plot its projected point, label matches.
    textPlacementError = '';
    textPlacementStatus = '';

    if (!hasPopulation) {
      textPlacementError = 'Generate a space first.';
      return;
    }
    if (!availableModes.includes('clap')) {
      textPlacementError = 'This run has no CLAP embeddings.';
      return;
    }
    if (currentMode !== 'clap') {
      textPlacementError = 'Switch to CLAP mode to project text.';
      return;
    }

    const query = textPrompt.trim();
    if (!query) {
      textPlacementError = 'Describe a sound first.';
      return;
    }

    const cacheKey = query.toLowerCase();
    if (textProbeCache.has(cacheKey)) {
      try {
        applyTextProbeResult(textProbeCache.get(cacheKey), { fromCache: true });
      } catch (err) {
        console.error('Cached projection invalid, refetching:', err);
        textProbeCache.delete(cacheKey);
      }
      return;
    }

    textPlacementLoading = true;
    try {
      const resp = await api.projectTextPoint(query, 'clap', 5);
      textProbeCache.set(cacheKey, resp);
      applyTextProbeResult(resp);
    } catch (err) {
      textPlacementError = err?.message || 'Failed to project text.';
      textPlacementStatus = '';
      console.error('Text projection failed:', err);
    } finally {
      textPlacementLoading = false;
    }
  }

  function clearTextProjections() {
    virtualPoints = [];
    searchResults = [];
    textPlacementStatus = '';
    textPlacementError = '';
  }

  async function handleAudioSearch(file) {
    if (!file || currentMode !== 'afxrep') return;

    audioSearchLoading = true;
    audioSearchStatus = '';
    audioSearchError = '';
    searchResults = [];

    // Create object URL for audio preview
    if (audioPreviewUrl) {
      URL.revokeObjectURL(audioPreviewUrl);
    }
    audioPreviewUrl = URL.createObjectURL(file);
    audioPreviewPlaying = false;

    try {
      const result = await api.searchAudio(file, 10);

      if (result.results && Array.isArray(result.results)) {
        // Keep the full result objects (they already have .idx property)
        searchResults = result.results;
        audioSearchStatus = `Found ${searchResults.length} similar FX chains`;
      } else {
        audioSearchError = 'No results returned';
      }
    } catch (err) {
      audioSearchError = err?.message || 'Audio search failed';
      console.error('Audio search error:', err);
    } finally {
      audioSearchLoading = false;
    }
  }

  function clearAudioSearch() {
    audioSearchFile = null;
    searchResults = [];
    audioSearchStatus = '';
    audioSearchError = '';

    // Clean up audio preview
    if (audioPreviewUrl) {
      URL.revokeObjectURL(audioPreviewUrl);
      audioPreviewUrl = null;
    }
    audioPreviewPlaying = false;
    if (audioPreviewElement) {
      audioPreviewElement.pause();
      audioPreviewElement.currentTime = 0;
    }
  }

  function toggleAudioPreview() {
    if (!audioPreviewElement || !audioPreviewUrl) return;

    if (audioPreviewPlaying) {
      audioPreviewElement.pause();
      audioPreviewPlaying = false;
    } else {
      audioPreviewElement.play();
      audioPreviewPlaying = true;
    }
  }

  function handleAudioPreviewEnded() {
    audioPreviewPlaying = false;
  }

  function clearAllSearch() {
    clearTextProjections();
    clearAudioSearch();
  }

  // Special points navigation

  function toggleSpecialPointsNav() {
    showSpecialPointsNav = !showSpecialPointsNav;
    if (showSpecialPointsNav && specialPoints.length > 0) {
      // Start at first special point if toggling on
      if (specialPointsIndex < 0) {
        specialPointsIndex = 0;
        navigateToSpecialPoint(0);
      }
    }
  }

  function navigateToSpecialPoint(index) {
    if (index < 0 || index >= specialPoints.length) return;

    specialPointsIndex = index;
    const sample = specialPoints[index];
    const sampleIndex = deriveSampleIndex(sample, samples);
    if (sampleIndex === null || sampleIndex === undefined) return;

    // Select the sample (this will trigger audio playback and inspector update)
    handleSampleClick({ detail: {
      sample,
      coord: coords[sampleIndex],
      index: sampleIndex
    }});
  }

  function goToNextSpecialPoint() {
    if (specialPoints.length === 0) return;
    const nextIndex = (specialPointsIndex + 1) % specialPoints.length;
    navigateToSpecialPoint(nextIndex);
  }

  function goToPrevSpecialPoint() {
    if (specialPoints.length === 0) return;
    const prevIndex = specialPointsIndex <= 0
      ? specialPoints.length - 1
      : specialPointsIndex - 1;
    navigateToSpecialPoint(prevIndex);
  }

  function scheduleAudioUpdate(callback, delay) {
    if (audioUpdateTimer) {
      clearTimeout(audioUpdateTimer);
    }
    audioUpdateTimer = setTimeout(() => {
      audioUpdateTimer = null;
      callback();
    }, delay);
  }

  function scheduleLivePreview(forceRestart = false) {
    if (!selectedSample || !editableParams) return;
    scheduleAudioUpdate(() => applyEditableParams(forceRestart), 75);
  }

  async function applyEditableParams(forceRestart = false) {
    if (!selectedSample || !editableParams) return;
    try {
      await audioPlayer.setInterpolationParams(
        { plugins: editableParams },
        { restart: forceRestart || !isLiveEditing }
      );
      isLiveEditing = true;
      interpolationStatus = `Live edit: #${selectedSample.index}`;
      interpolationError = '';
    } catch (err) {
      interpolationError = err?.message || 'Live edit failed.';
      console.error('Live edit error:', err);
    }
  }

  function handleParamChange(event) {
    if (!selectedSample) return;
    const detail = event.detail || {};
    const { plugin, path = [], value } = detail;
    if (!plugin) return;
    const base = editableParams
      ? cloneParams(editableParams)
      : cloneParams(getSampleParams(selectedSample) || {});
    const pluginState = base?.[plugin] ?? {};
    base[plugin] = setValueAtPath(pluginState, path, value);
    editableParams = base;
    isEditingParams = true;
    scheduleEditGhostUpdate();
    scheduleLivePreview(!isLiveEditing);
  }

  function scheduleEditGhostUpdate() {
    if (!editableParams) {
      editGhostLoading = false;
      return;
    }
    if (editGhostTimer) {
      clearTimeout(editGhostTimer);
    }
    const requestId = ++editGhostRequestId;
    editGhostLoading = true;
    editGhostTimer = setTimeout(() => {
      editGhostTimer = null;
      const params = buildEditGhostParams(selectedSample, editableParams);
      if (!params) {
        editGhostLoading = false;
        return;
      }
      calculateGhostPoint(api, currentMode, params)
        .then((next) => {
          if (requestId !== editGhostRequestId) return;
          if (next) {
            editGhost = next;
          }
        })
        .finally(() => {
          if (requestId === editGhostRequestId) {
            editGhostLoading = false;
          }
        });
    }, EDIT_GHOST_DEBOUNCE);
  }

  function resetInterpolationControls() {
    interpolationPointA = null;
    interpolationPointB = null;
    interpolationChainKey = null;
    interpolationStatus = '';
    interpolationError = '';
    interpolationActive = false;
    interpolationSlider = 0;
    interpolationPreviewParams = null;
    interpolationPreviewPercent = 0;

    if (audioUpdateTimer) {
      clearTimeout(audioUpdateTimer);
      audioUpdateTimer = null;
    }

  }

  function assignInterpolationPoint(which, sourceSample) {
    if (!sourceSample) {
      interpolationError = 'Select or hover a sample first.';
      return;
    }
    const params = getSampleParams(sourceSample);
    if (!params || Object.keys(params).length === 0) {
      if (sourceSample?.type !== 'dry') {
        interpolationError = 'Selected sample has no FX parameters.';
        return;
      }
    }
    const other = which === 'A' ? interpolationPointB : interpolationPointA;
    if (other?.params && !canPairInterpolation(params, other.params)) {
      interpolationError = 'Interpolating requires matching FX chains (dry can pair with any FX).';
      return;
    }
    const index = deriveSampleIndex(sourceSample, samples);
    if (index === null || index === undefined) {
      interpolationError = 'Could not determine sample index.';
      return;
    }
    const label =
      sourceSample.name ||
      (sourceSample.type ? `${sourceSample.type} #${index}` : `Sample #${index}`);
    const context = {
      index,
      name: label,
      params,
      type: sourceSample.type || '',
    };
    if (which === 'A') {
      interpolationPointA = context;
      interpolationChainKey = getChainKeyFromParams(params);
    } else {
      interpolationPointB = context;
    }
    interpolationStatus = '';
    interpolationError = '';
    interpolationActive = false;
    if (interpolationPointA?.params && interpolationPointB?.params) {
      interpolationSlider = 0;
      updateInterpolationPreview(0);
      interpolationStatus = 'Ready. Press M to start blending.';
    } else {
      interpolationPreviewParams = null;
      interpolationPreviewPercent = 0;
    }
  }

  function handleInspectorAssign(event) {
    const detail = event.detail || {};
    const which = detail.which;
    const source = detail.source;

    // Handle null/empty selection (clear point)
    if (!source) {
      if (which === 'A') {
        interpolationPointA = null;
        interpolationChainKey = null;
      } else {
        interpolationPointB = null;
      }
      interpolationStatus = '';
      interpolationError = '';
      interpolationActive = false;
      interpolationPreviewParams = null;
      interpolationPreviewPercent = 0;
      return;
    }

    // Handle new dropdown format: {type: 'sample', index: N} or {type: 'preset', presetId, name, params}
    if (source.type === 'preset') {
      // Preset-based interpolation point
      const presetParams = source.params || {};
      const other = which === 'A' ? interpolationPointB : interpolationPointA;
      if (other?.params && !canPairInterpolation(presetParams, other.params)) {
        interpolationError = 'Interpolating requires matching FX chains (dry can pair with any FX).';
        return;
      }
      const context = {
        index: null,  // Presets don't have sample indices
        name: source.name,
        params: presetParams,
        type: 'preset',
        presetId: source.presetId
      };
      if (which === 'A') {
        interpolationPointA = context;
        interpolationChainKey = getChainKeyFromParams(presetParams);
      } else {
        interpolationPointB = context;
      }
    } else if (source.type === 'sample') {
      // Sample-based interpolation point
      const sample = samples[source.index];
      if (!sample) {
        interpolationError = 'Sample not found.';
        return;
      }
      assignInterpolationPoint(which, sample);
      return;  // assignInterpolationPoint handles the rest
    } else {
      // Old format fallback (shouldn't happen anymore)
      const sample = source === 'hovered' ? hoveredSample : selectedSample;
      assignInterpolationPoint(which, sample);
      return;
    }

    // Update interpolation status for preset-based selection
    interpolationStatus = '';
    interpolationError = '';
    interpolationActive = false;
    if (interpolationPointA?.params && interpolationPointB?.params) {
      interpolationSlider = 0;
      updateInterpolationPreview(0);
      interpolationStatus = 'Ready. Press M to start blending.';
    } else {
      interpolationPreviewParams = null;
      interpolationPreviewPercent = 0;
    }
  }

  function clearInterpolationSelections() {
    if (interpolationActive) {
      audioPlayer.stopFull();
    }
    resetInterpolationControls();
  }

  function updateInterpolationPreview(position = interpolationSlider) {
    if (!interpolationPointA?.params || !interpolationPointB?.params) {
      interpolationPreviewParams = null;
      interpolationPreviewPercent = 0;
      return null;
    }
    const clamped = Math.min(Math.max(position, 0), 1);
    let t = clamped;
    let blended;
    const isDryA = isDryParams(interpolationPointA.params);
    const isDryB = isDryParams(interpolationPointB.params);
    if (isDryA || isDryB) {
      const wetParams = isDryA ? interpolationPointB.params : interpolationPointA.params;
      const alpha = isDryA ? clamped : 1 - clamped;
      if (alpha <= INTERPOLATION_SNAP_EPSILON) {
        blended = {};
        t = isDryA ? 0 : 1;
      } else if (1 - alpha <= INTERPOLATION_SNAP_EPSILON) {
        blended = cloneParams(wetParams);
        t = isDryA ? 1 : 0;
      } else {
        blended = scaleParamsForDryWet(wetParams, alpha);
        t = clamped;
      }
    } else if (clamped <= INTERPOLATION_SNAP_EPSILON) {
      blended = cloneParams(interpolationPointA.params);
      t = 0;
    } else if (1 - clamped <= INTERPOLATION_SNAP_EPSILON) {
      blended = cloneParams(interpolationPointB.params);
      t = 1;
    } else {
      blended = interpolateBetween(interpolationPointA.params, interpolationPointB.params, clamped);
    }
    interpolationPreviewParams = blended;
    interpolationPreviewPercent = Math.round(t * 100);
    return { t, blended };
  }

  function handleInterpolationSliderInput(eventOrValue) {
    const rawValue =
      typeof eventOrValue === 'number'
        ? eventOrValue
        : parseFloat(eventOrValue?.target?.value);
    const value = isNaN(rawValue) ? 0 : rawValue;
    interpolationSlider = isNaN(value) ? 0 : value;
    const preview = updateInterpolationPreview(interpolationSlider);
    if (interpolationActive && preview) {
      scheduleInterpolationApply(preview);
    }
  }

  function handleInterpolationSliderCommit(eventOrValue) {
    if (typeof eventOrValue === 'number') {
      interpolationSlider = isNaN(eventOrValue) ? interpolationSlider : eventOrValue;
    } else if (eventOrValue?.target?.value !== undefined) {
      const parsed = parseFloat(eventOrValue.target.value);
      if (!isNaN(parsed)) {
        interpolationSlider = parsed;
      }
    }
    const preview = updateInterpolationPreview(interpolationSlider);
    if (!canInterpolate || !preview) return;
    if (!interpolationActive) {
      interpolationStatus = 'Press M to start playback.';
      return;
    }
    applyInterpolationBlend(preview);
  }

  function handleInterpolationStart() {
    if (!canInterpolate) {
      interpolationError = 'Assign both interpolation points first.';
      return;
    }
    const preview = updateInterpolationPreview(interpolationSlider);
    if (!preview) return;
    applyInterpolationBlend(preview, { restart: true });
  }

  function handlePresetLoad(event) {
    const { params } = event.detail;
    if (!params) return;

    // Set as editable params and apply
    const plugins = params?.plugins ? params.plugins : params;
    editableParams = cloneParams(plugins);
    isLiveEditing = false;

    // Apply to audio if something is selected
    if (selectedSample) {
      scheduleLivePreview(true);
    }
  }

  async function applyInterpolationBlend(previewResult = null, { restart = false } = {}) {
    if (!canInterpolate) return;

    // Check if both points are the same (handles both samples and presets)
    const isSamePoint =
      (interpolationPointA.type === 'preset' && interpolationPointB.type === 'preset' && interpolationPointA.presetId === interpolationPointB.presetId) ||
      (interpolationPointA.type !== 'preset' && interpolationPointB.type !== 'preset' && interpolationPointA.index === interpolationPointB.index);

    if (isSamePoint) {
      interpolationError = 'Pick two different samples/presets to interpolate.';
      return;
    }
    const paramsA = interpolationPointA.params;
    const paramsB = interpolationPointB.params;
    if (!paramsA || !paramsB) {
      interpolationError = 'Missing FX parameters.';
      return;
    }
    const preview = previewResult || updateInterpolationPreview(interpolationSlider);
    if (!preview) return;
    const { t, blended } = preview;
    const useParams =
      t <= INTERPOLATION_SNAP_EPSILON
        ? interpolationPointA.params
        : 1 - t <= INTERPOLATION_SNAP_EPSILON
        ? interpolationPointB.params
        : blended;
    const wrapped = { plugins: useParams };
    const percent = Math.round(t * 100);
    const isDryA = isDryParams(interpolationPointA.params);
    const isDryB = isDryParams(interpolationPointB.params);
    const sameChain = haveSameFxChain(interpolationPointA.params, interpolationPointB.params);
    if (!sameChain && !isDryA && !isDryB) {
      interpolationError = 'Interpolating requires matching FX chains. Pick two points with the same FX.';
      interpolationActive = false;
      return;
    }
    interpolationStatus = isDryA || isDryB
      ? `Wet/Dry interpolation (${percent}%)`
      : `Interpolating #${interpolationPointA.index} → #${interpolationPointB.index} (${percent}%)`;
    interpolationError = '';
    try {
      await audioPlayer.setInterpolationParams(wrapped, restart ? { restart: true } : {});
      interpolationActive = true;
    } catch (err) {
      interpolationError = err?.message || 'Interpolation playback failed.';
      interpolationActive = false;
      console.error('Interpolation playback error:', err);
    }
  }

  function scheduleInterpolationApply(preview) {
    scheduleAudioUpdate(() => applyInterpolationBlend(preview, { restart: false }), AUDIO_UPDATE_DEBOUNCE);
  }


  // Keyboard interpolation mode management

  let visualizationComponent;

  async function enterKeyboardInterpolationMode() {
    if (!canInterpolate) {
      interpolationError = "Assign both interpolation points first (hover + press 1/2)";
      return;
    }
    if (!canPairInterpolation(interpolationPointA?.params, interpolationPointB?.params)) {
      interpolationError = "Keyboard interpolation requires matching FX chains.";
      return;
    }

    keyboardInterpolationMode = true;
    selectedSample = null;
    editableParams = null;
    isEditingParams = false;
    isLiveEditing = false;
    interpolationSlider = 0;  // Start at Point A

    // Trigger canvas zoom to interpolation points
    zoomToInterpolationPoints();

    // Start playback at Point A
    const preview = updateInterpolationPreview(0);
    await applyInterpolationBlend(preview, { restart: true });

    interpolationStatus = "Keyboard interpolation mode active. Use ← → arrows to blend, ESC to exit.";
  }

  function exitKeyboardInterpolationMode() {
    keyboardInterpolationMode = false;

    // Clean up arrow key interval if still active
    if (arrowKeyInterval) {
      clearInterval(arrowKeyInterval);
      arrowKeyInterval = null;
    }
    arrowKeyHeld = null;

    // Reset canvas zoom (return to auto-fit all points)
    resetCanvasZoom();

    // Clear interpolation selections when exiting keyboard mode
    resetInterpolationControls();

    interpolationStatus = "Exited keyboard interpolation mode.";
  }

  function adjustInterpolationSlider(delta) {
    const newValue = Math.max(0, Math.min(1, interpolationSlider + delta));
    interpolationSlider = newValue;

    // Update preview immediately for visual feedback
    const preview = updateInterpolationPreview(interpolationSlider);

    if (preview) {
      scheduleInterpolationApply(preview);
    }
  }

  function handleInterpolationIndicatorChange(event) {
    const newPercent = event.detail.percent;
    const newSliderValue = newPercent / 100;
    interpolationSlider = newSliderValue;

    // Update preview immediately for visual feedback
    const preview = updateInterpolationPreview(interpolationSlider);

    if (preview) {
      scheduleInterpolationApply(preview);
    }
  }

  function zoomToInterpolationPoints() {
    if (visualizationComponent?.zoomToPoints) {
      visualizationComponent.zoomToPoints(interpolationPointAIndex, interpolationPointBIndex);
    }
  }

  function resetCanvasZoom() {
    if (visualizationComponent?.resetZoom) {
      visualizationComponent.resetZoom();
    }
  }

  function resetInterpolationSelection() {
    if (interpolationActive) {
      audioPlayer.stopFull();
    }
    interpolationPointA = null;
    interpolationPointB = null;
    interpolationChainKey = null;
    interpolationActive = false;
    interpolationSlider = 0;
    interpolationPreviewParams = null;
    interpolationPreviewPercent = 0;
    interpolationStatus = 'Exited interpolation mode.';
    interpolationError = '';
    if (keyboardInterpolationMode) {
      exitKeyboardInterpolationMode();
    }
  }

  // Keyboard event handlers

  function handleKeyDown(event) {
    const target = event.target;
    if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) {
      return;
    }
    if (event.key === "b" || event.key === "B") {
      toggleFxBypass();
      return;
    }
    if (event.key === "h" || event.key === "H") {
      showFloatingControls = !showFloatingControls;
      return;
    }
    if (event.key === "Escape") {
      if (keyboardInterpolationMode || interpolationActive || interpolationPointA || interpolationPointB) {
        event.preventDefault();
        resetInterpolationSelection();
        return;
      }
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      if (isEditingParams && selectedSample) {
        editableParams = cloneParams(getSampleParams(selectedSample) || {});
        isEditingParams = false;
        isLiveEditing = false;
        editGhost = selectedSample?.index != null && coords[selectedSample.index]
          ? { x: coords[selectedSample.index].x, y: coords[selectedSample.index].y }
          : editGhost;
        const resetParams = getSampleParams(selectedSample) || {};
        if (selectedSample?.type === 'interpolation') {
          audioPlayer.setInterpolationParams(resetParams, { restart: true });
        } else if (typeof selectedSample?.index === 'number') {
          audioPlayer.playFull(selectedSample.index, resetParams);
        }
        interpolationStatus = 'Edit canceled.';
        interpolationError = '';
        return;
      }
      if (keyboardInterpolationMode) {
        exitKeyboardInterpolationMode();
        return;
      }
      if (interpolationActive) {
        audioPlayer.stopFull();
      }
      if (interpolationPointB) {
        interpolationPointB = null;
      } else if (interpolationPointA) {
        interpolationPointA = null;
        interpolationChainKey = null;
      } else {
        return;
      }
      interpolationStatus = 'Cleared interpolation point.';
      interpolationError = '';
      interpolationActive = false;
      interpolationSlider = 0;
      interpolationPreviewParams = null;
      interpolationPreviewPercent = 0;
      return;
    }
    // Keys 1/2 for interpolation point assignment
    if (hoveredSample && (event.key === "1" || event.key === "2")) {
      const location = event.key === "1" ? "A" : "B";
      handleInspectorAssign({
        detail: { which: location, source: {type: "sample", index: hoveredSample.index} }
      });
      return;
    }

    // M key - Enter keyboard interpolation mode
    if (event.key === "m" || event.key === "M") {
      if (canInterpolate && !keyboardInterpolationMode) {
        event.preventDefault();
        enterKeyboardInterpolationMode();
      }
      return;
    }

    // [ ] keys - Navigate special points (when not in interpolation mode)
    if (!keyboardInterpolationMode && (event.key === "[" || event.key === "]")) {
      if (specialPoints.length === 0) return;
      event.preventDefault();

      // Auto-show navigation if hidden
      if (!showSpecialPointsNav) {
        showSpecialPointsNav = true;
        if (specialPointsIndex < 0) {
          specialPointsIndex = 0;
          navigateToSpecialPoint(0);
        }
        return;
      }

      // Navigate prev/next
      if (event.key === "[") {
        goToPrevSpecialPoint();
      } else {
        goToNextSpecialPoint();
      }
      return;
    }

    // LEFT/RIGHT ARROW > to control interpolation - Start continuous adjustment on hold
    if (keyboardInterpolationMode && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();

      // Ignore if already holding (prevents key repeat spam)
      if (arrowKeyHeld) return;

      const direction = event.key === "ArrowLeft" ? 'left' : 'right';
      arrowKeyHeld = direction;

      // Immediate first adjustment
      const delta = direction === 'left' ? -interpolationSliderStep : interpolationSliderStep;
      adjustInterpolationSlider(delta);

      // Start interval for continuous updates while held
      arrowKeyInterval = setInterval(() => {
        const delta = arrowKeyHeld === 'left' ? -interpolationSliderStep : interpolationSliderStep;
        adjustInterpolationSlider(delta);
      }, ARROW_KEY_RATE);

      return;
    }
  }

  function toggleFxBypass(forceValue = null) {
    fxBypass = typeof forceValue === 'boolean' ? forceValue : !fxBypass;
    audioPlayer.setFxBypass(fxBypass);
    fxBypassFlash = true;
    clearTimeout(fxBypassFlashTimer);
    fxBypassFlashTimer = setTimeout(() => {
      fxBypassFlash = false;
    }, 1200);
  }

  function handleKeyUp(event) {
    // Stop continuous arrow key updates when released
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      arrowKeyHeld = null;
      if (arrowKeyInterval) {
        clearInterval(arrowKeyInterval);
        arrowKeyInterval = null;
      }
    }
  }

  function startSidebarResize(event) {
    event.preventDefault();
    sidebarDragging = true;
  }

  function stopSidebarResize() {
    sidebarDragging = false;
  }

  function handleSidebarMouseMove(event) {
    if (!sidebarDragging || !sidebarEl) return;
    const rect = sidebarEl.getBoundingClientRect();
    const nextWidth = Math.max(SIDEBAR_MIN, Math.min(event.clientX - rect.left, SIDEBAR_MAX));
    sidebarWidth = nextWidth;
  }
</script>

<svelte:window
  on:keydown={handleKeyDown}
  on:keyup={handleKeyUp}
  on:mousemove={handleSidebarMouseMove}
  on:mouseup={stopSidebarResize}
/>

<!-- Hidden audio element for preview playback -->
{#if audioPreviewUrl}
  <audio
    bind:this={audioPreviewElement}
    src={audioPreviewUrl}
    on:ended={handleAudioPreviewEnded}
    style="display: none;"
  ></audio>
{/if}

<!-- Interpolationage Indicator (top-center overlay) -->
<InterpolationIndicator
  visible={keyboardInterpolationMode || interpolationActive}
  pointA={interpolationPointA}
  pointB={interpolationPointB}
  percent={interpolationPreviewPercent}
  sidebarWidth={sidebarWidth}
  on:change={handleInterpolationIndicatorChange}
/>

<main class="app">
  {#if error}
    <div class="error-banner">
      <span>⚠️ {error}</span>
      <button on:click={() => error = null}>×</button>
    </div>
  {/if}

  {#if fxBypassFlash}
    <div class="fx-bypass-indicator {fxBypass ? 'on' : 'off'}">
      {fxBypass ? 'FX BYPASS' : 'FX ON'}
    </div>
  {/if}

  {#if isInitializing}
    <div class="loading-screen">
      <div class="spinner"></div>
      <p>Loading FXplorer...</p>
    </div>
  {:else}
    <div class="layout">
      <aside class="sidebar" bind:this={sidebarEl} style={`width: ${sidebarWidth}px;`}>
        <header class="app-header">
          <h1>FXplorer</h1>
          <p class="subtitle">Audio FX Exploration Space! Audition, interpolate, edit, save</p>
        </header>

        <Inspector
          {selectedSample}
          {hoveredSample}
          {editableParams}
          {interpolationPreviewEntries}
          {interpolationActive}
          {interpolationPointA}
          {interpolationPointB}
          {interpolationPreviewPercent}
          {keyboardInterpolationMode}
          {isEditingParams}
          fxParams={fxRackParams}
          fxDisplayState={fxRackState}
          fxSampleInfo={fxRackSample}
          fxReadonly={fxRackReadonly}
          {fxBypass}
          {presetRefreshToken}
          on:presetLoad={handlePresetLoad}
          on:paramChange={handleParamChange}
          on:nameChange={handleNameChange}
          on:interpolationSave={handleInterpolationSave}
          on:fxBypassChange={(event) => toggleFxBypass(event.detail?.enabled)}
        />
        <div class="sidebar-resizer" on:mousedown={startSidebarResize} role="separator" aria-orientation="vertical"></div>
      </aside>

      <!-- Main Visualization Area -->
      <section class="main-content">
        {#if hasPopulation}
          <Visualization
            bind:this={visualizationComponent}
            {coords}
            {samples}
            {currentMode}
            {searchResults}
            {virtualPoints}
            {selectedSample}
            {hoveredSample}
            showOverlays={showFloatingControls}
            {interpolationPointA}
            {interpolationPointB}
            {interpolationChainKey}
            {interpolationActive}
            {keyboardInterpolationMode}
            interpolationPointAIndex={interpolationPointAIndex}
            interpolationPointBIndex={interpolationPointBIndex}
            interpolationGhost={interpolationGhostCoords}
            editGhost={editGhost}
            {editGhostLoading}
            on:sampleHover={handleSampleHover}
            on:sampleLeave={handleSampleLeave}
            on:sampleClick={handleSampleClick}
          />
          {#if showFloatingControls}
            <div class="floating-controls">
            <div class="control-stack">
              <p class="label">Embedding mode</p>
              <div class="btn-group">
                {#each availableModes as modeBtn}
                  <button
                    class:active={currentMode === modeBtn}
                    on:click={() => hasPopulation && handleModeChange(modeBtn)}
                    aria-pressed={currentMode === modeBtn}
                    disabled={!hasPopulation}
                  >
                    {modeBtn.toUpperCase()}
                  </button>
                {/each}
              </div>
            </div>

            <div class="control-stack">
              <p class="label">Hover playback</p>
              <div class="btn-group">
                <button
                  class:active={hoverPlaybackMode === 'smooth'}
                  on:click={() => {
                    hoverPlaybackMode = 'smooth';
                    audioPlayer.stopPreview();
                    isPaused = false;
                  }}
                >
                  Smooth
                </button>
                <button
                  class:active={hoverPlaybackMode === 'restart'}
                  on:click={() => {
                    hoverPlaybackMode = 'restart';
                    audioPlayer.stopPreview();
                    isPaused = false;
                  }}
                >
                  Restart
                </button>
              </div>
            </div>

            <!-- Mode-Specific Search Controls -->
            <div class="control-stack search-stack">
              {#if currentMode === 'clap'}
                <!-- CLAP Text Search -->
                <p class="label">Text Search (CLAP)</p>
                <div class="text-probe-row">
                  <input
                    type="text"
                    placeholder="e.g., warm roomy piano"
                    bind:value={textPrompt}
                    on:keydown={(event) => {
                      if (event.key === 'Enter') {
                        handleTextProjection();
                      }
                    }}
                    disabled={textPlacementLoading || !hasPopulation}
                  />
                  <button
                    class="primary"
                    on:click={handleTextProjection}
                    disabled={textPlacementLoading || !hasPopulation}
                  >
                    {textPlacementLoading ? 'Embedding...' : 'Drop'}
                  </button>
                  {#if virtualPoints.length > 0}
                    <button class="ghost" on:click={clearTextProjections} disabled={textPlacementLoading}>
                      Clear
                    </button>
                  {/if}
                </div>
                {#if textPlacementLoading}
                  <div class="search-progress">
                    <div class="bar"></div>
                  </div>
                {/if}
                {#if textPlacementStatus}
                  <p class="status-note">{textPlacementStatus}</p>
                {/if}
                {#if textPlacementError}
                  <p class="error-note">{textPlacementError}</p>
                {/if}
              {:else if currentMode === 'afxrep'}
                <!-- AFx-Rep Audio Search -->
                <p class="label">Audio Search (AFx-Rep)</p>
                <div class="audio-search-container">
                  {#if audioSearchFile}
                    <div class="file-selected">
                      <span class="file-icon">🎵</span>
                      <div class="file-info">
                        <span class="file-name">{audioSearchFile.name}</span>
                        <button
                          class="audio-preview-btn"
                          on:click={toggleAudioPreview}
                          title={audioPreviewPlaying ? 'Pause' : 'Play'}
                        >
                          {audioPreviewPlaying ? '⏸' : '▶️'}
                        </button>
                      </div>
                      <button class="ghost file-clear" on:click={clearAudioSearch}>×</button>
                    </div>
                  {:else}
                    <label class="file-upload-zone" class:disabled={!hasPopulation}>
                      <input
                        type="file"
                        accept="audio/*"
                        disabled={!hasPopulation || audioSearchLoading}
                        on:change={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            audioSearchFile = file;
                            handleAudioSearch(file);
                          }
                        }}
                        style="display: none;"
                      />
                      <span class="upload-icon">🗂️</span>
                      <span class="upload-text">Drop audio or click to browse</span>
                      <span class="upload-formats">WAV, MP3, FLAC, OGG</span>
                    </label>
                  {/if}
                </div>
                {#if audioSearchLoading}
                  <div class="search-progress">
                    <div class="bar"></div>
                  </div>
                {/if}
                {#if audioSearchStatus}
                  <p class="status-note">{audioSearchStatus}</p>
                {/if}
                {#if audioSearchError}
                  <p class="error-note">{audioSearchError}</p>
                {/if}
                {#if searchResults.length > 0}
                  <button class="ghost" on:click={clearAudioSearch}>Clear Results</button>
                {/if}
              {/if}
            </div>
            <button
              class="pause-btn"
              on:click={() => {
                if (isPaused) {
                  audioPlayer.resume();
                } else {
                  handlePause();
                }
                isPaused = !isPaused;
              }}
            >
              {isPaused ? '> Resume' : '⏸ Pause'}
            </button>

            <!-- Special Points Navigation -->
            <SpecialPointsNav
              {specialPoints}
              {specialPointsIndex}
              {showSpecialPointsNav}
              onToggle={toggleSpecialPointsNav}
              onPrev={goToPrevSpecialPoint}
              onNext={goToNextSpecialPoint}
            />
            <p class="control-hint">Press <code>H</code> to hide/show this panel</p>
            </div>
          {/if}
          <div class="bottom-panels">
            <WaveformMonitor
              state={playbackState}
              waveform={waveformPoints}
              loading={waveformLoading}
            />
          </div>
        {:else}
          <div class="empty-state">
            <div class="empty-graphic">⬤</div>
            <h3>Upload to populate the space</h3>
            <p>Pick a dry file and FX preset to generate samples and view the map.</p>
          </div>
        {/if}
      </section>
    </div>
    {#if showGeneratePanel}
      <div class="modal-overlay">
        <div class="modal-panel">
          <UploadPanel on:generate={handlePipelineGenerate} />
        </div>
      </div>
    {/if}
  {/if}
</main>

<style>
  @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Space+Mono:wght@400;700&family=Manrope:wght@400;500;600;700&display=swap');

  :global(body) {
    --bg: #1a140f;
    --panel: #241c15;
    --panel-strong: #2c231a;
    --panel-deep: #33281f;
    --border: #3b2f24;
    --border-strong: #4a3a2c;
    --text: #f1e6d2;
    --text-strong: #f7efe0;
    --muted: #c0ad92;
    --muted-2: #a08b73;
    --accent: #c78b5a;
    --accent-2: #8a6f4d;
    --accent-3: #d6a36a;
    --success: #7d9a6c;
    --error: #c56b52;

    margin: 0;
    padding: 0;
    font-family: 'Manrope', sans-serif;
    background: var(--bg);
    color: var(--text);
  }

  :global(h1),
  :global(h2),
  :global(h3),
  :global(.mode-label) {
    font-family: 'Fira Code', monospace;
    letter-spacing: 0.02em;
  }

  :global(h1) {
    font-size: 0.85rem;
  }

  :global(h2) {
    font-size: 0.75rem;
  }

  :global(h3) {
    font-size: 0.7rem;
  }

  .app {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
  }

  .error-banner {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    background: var(--error);
    color: white;
    padding: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    z-index: 1000;
  }

  .error-banner button {
    background: none;
    border: none;
    color: white;
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0 0.5rem;
  }

  .fx-bypass-indicator {
    position: fixed;
    top: 1rem;
    right: 1.25rem;
    padding: 0.4rem 0.75rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    z-index: 1000;
    border: 1px solid var(--border);
    background: rgba(36, 28, 21, 0.88);
    color: var(--text);
    animation: fxPulse 1.2s ease-out;
  }

  .fx-bypass-indicator.on {
    background: rgba(197, 107, 82, 0.22);
    border-color: var(--error);
    color: var(--text-strong);
  }

  .fx-bypass-indicator.off {
    background: rgba(125, 154, 108, 0.22);
    border-color: var(--success);
    color: var(--text-strong);
  }

  @keyframes fxPulse {
    0% { transform: translateY(-6px); opacity: 0; }
    20% { opacity: 1; }
    100% { transform: translateY(0); opacity: 1; }
  }

  .loading-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    gap: 1rem;
  }

  .spinner {
    width: 50px;
    height: 50px;
    border: 4px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .layout {
    display: flex;
    height: 100vh;
    position: relative;
  }

  .sidebar {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    width: 360px;
    background: var(--panel);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 20;
  }

  .sidebar-resizer {
    position: absolute;
    top: 0;
    right: -3px;
    width: 6px;
    height: 100%;
    cursor: col-resize;
    background: transparent;
  }

  .sidebar-resizer:hover {
    background: rgba(199, 139, 90, 0.15);
  }

  .app-header {
    padding: 1.5rem;
    border-bottom: 1px solid var(--border);
  }

  .app-header h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-3) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .subtitle {
    margin: 0.25rem 0 0 0;
    font-size: 0.875rem;
    color: var(--muted);
  }

  .main-content {
    flex: 1;
    position: relative;
    overflow: hidden;
    padding-bottom: 180px; /* Space for waveform monitor */
  }

  .modal-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(26, 20, 15, 0.7);
    backdrop-filter: blur(2px);
    z-index: 900;
  }

  .modal-panel {
    width: min(520px, 92vw);
    max-height: 90vh;
    overflow: auto;
    overflow-x: hidden;
    border-radius: 14px;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55);
  }

  .empty-state {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--muted-2);
  }

  .empty-state h3 {
    margin: 0;
    color: var(--text-strong);
  }

  .empty-state p {
    margin: 0;
    color: var(--muted);
  }

  .empty-graphic {
    font-size: 2rem;
    color: var(--border);
  }

  .floating-controls {
    position: absolute;
    top: 1rem;
    right: 1rem;
    display: grid;
    gap: 0.75rem;
    background: rgba(36, 28, 21, 0.92);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem;
    backdrop-filter: blur(8px);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
  }

  .control-stack {
    display: grid;
    gap: 0.35rem;
  }

  .control-stack .label {
    margin: 0;
    color: var(--muted);
    font-size: 0.85rem;
    letter-spacing: 0.04em;
  }

  .btn-group {
    display: grid;
    grid-auto-flow: column;
    gap: 0.35rem;
  }

  .btn-group button {
    padding: 0.55rem 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--panel-strong);
    color: var(--text);
    cursor: pointer;
    transition: border 0.15s, background 0.15s, color 0.15s;
    min-width: 92px;
  }

  .btn-group button.active {
    border-color: var(--accent);
    background: #3a2b1f;
    color: var(--text-strong);
  }

  .btn-group button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .pause-btn {
    padding: 0.6rem 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: linear-gradient(135deg, rgba(199, 139, 90, 0.28), rgba(214, 163, 106, 0.18));
    color: var(--text-strong);
    cursor: pointer;
    font-weight: 600;
    transition: transform 0.1s ease, border 0.15s;
  }

  .pause-btn:hover {
    transform: translateY(-1px);
    border-color: var(--accent-3);
  }

  .text-probe-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .text-probe-row input {
    flex: 1;
    padding: 0.45rem 0.6rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    font-size: 0.9rem;
  }

  .text-probe-row button {
    padding: 0.45rem 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: var(--panel-strong);
    color: var(--text-strong);
    cursor: pointer;
    font-weight: 600;
  }

  .text-probe-row button.primary {
    border-color: var(--accent);
    background: #3a2b1f;
  }

  .text-probe-row button.ghost {
    background: transparent;
    border-color: var(--border);
    color: var(--muted-2);
  }

  .text-probe-row button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @keyframes probePulse {
    0% { transform: translateX(-40%); }
    50% { transform: translateX(40%); }
    100% { transform: translateX(140%); }
  }

  /* Unified search progress */
  .search-progress {
    width: 100%;
    height: 4px;
    background: var(--panel-strong);
    border-radius: 999px;
    margin-top: 0.4rem;
    overflow: hidden;
  }

  .search-progress .bar {
    width: 35%;
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-3));
    border-radius: inherit;
    animation: probePulse 0.9s ease-in-out infinite;
  }

  /* Audio search UI */
  .audio-search-container {
    margin-top: 0.5rem;
  }

  .file-upload-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 1rem;
    border: 2px dashed var(--border);
    border-radius: 8px;
    background: var(--panel);
    cursor: pointer;
    transition: all 0.2s;
  }

  .file-upload-zone:hover:not(.disabled) {
    border-color: var(--accent);
    background: #2f231a;
  }

  .file-upload-zone.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .upload-icon {
    font-size: 1.5rem;
  }

  .upload-text {
    font-size: 0.9rem;
    color: var(--text);
  }

  .upload-formats {
    font-size: 0.75rem;
    color: var(--muted-2);
  }

  .file-selected {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
  }

  .file-icon {
    font-size: 1.25rem;
  }

  .file-info {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }

  .file-name {
    flex: 1;
    font-size: 0.9rem;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .audio-preview-btn {
    background: var(--accent);
    border: none;
    border-radius: 6px;
    color: white;
    font-size: 1rem;
    padding: 0.35rem 0.6rem;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
  }

  .audio-preview-btn:hover {
    background: var(--accent-3);
  }

  .file-clear {
    font-size: 1.25rem;
    padding: 0 0.5rem;
    background: transparent;
    border: none;
    color: var(--muted-2);
    cursor: pointer;
    transition: color 0.2s;
  }

  .file-clear:hover {
    color: var(--error);
  }

  .status-note {
    margin: 0.4rem 0 0;
    font-size: 0.85rem;
    color: var(--success);
  }

  .error-note {
    margin: 0.3rem 0 0;
    font-size: 0.85rem;
    color: var(--error);
  }

  .bottom-panels {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    pointer-events: auto;
    padding: 1rem;
    z-index: 10;
  }

  .bottom-panels :global(.unified-fx-panel) {
    pointer-events: auto;
  }

  .bottom-panels :global(.waveform-monitor) {
    pointer-events: auto;
  }

  .control-hint {
    margin: 0.35rem 0 0;
    font-size: 0.75rem;
    color: var(--muted-2);
  }

  .control-hint code {
    font-family: "Courier New", monospace;
    color: var(--text);
  }

</style>
