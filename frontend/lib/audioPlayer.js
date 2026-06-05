/**
 * Tone.js-based audio playback engine.
 *
 * Manages real-time audio playback with dynamic FX chains for the FXplorer frontend.
 *
 * Key things here: (NOTE: AC to check)
 * - Dual-mode playback: Preview (hover) + Full (selected loop)
 * - Shared playhead clock for smooth transitions between samples
 * - Dynamic FX chain building from Pedalboard parameters
 * - Buffer caching for instant playback
 * - Crossfade support for smooth preview transitions

 */

import * as Tone from 'tone';
import { api } from './api.js';
import { mapBackendParamsToTone, applyParamsToToneNodes } from './paramMapper.js';

class AudioPlayer {
  // Encapsulates preview + full playback plus interpolation controls.
  constructor() {
    this.initialized = false;

    // Preview playback state
    this.previewGeneration = 0;        // guards async crossfades
    this.previewPlayer = null;         // active preview player
    this.previewPlayerGain = null;     // per-preview gain (for crossfade)
    this.previewPlayerSourceGain = null; // pre-FX normalization gain
    this.previewGain = null;           // master preview output
    this.previewChain = [];            // current FX chain
    this.previewBufferDuration = 0;
    this.previewClockStart = null;     // shared playhead clock
    this.previewPausedOffset = 0;
    this.lastPreview = null;

    // Full playback state
    this.fullPlayer = null;            // single looping Tone.Player
    this.fullBusGain = null;           // master full output
    this.fullOutGain = null;           // per-full output gain
    this.fullMixGain = null;           // per-full mix bus (chain output + interpolation mix)
    this.fullSourceGain = null;        // pre-FX normalization gain
    this.fullChain = [];               // current FX chain
    this.fullBufferDuration = 0;
    this.fullClockStart = null;        // shared playhead clock
    this.fullPausedOffset = 0;
    this.lastFull = null;
    this.interpolationActive = false;
    this.interpolationCrossfadeActive = false;
    this.interpolationPlayerA = null;
    this.interpolationPlayerB = null;
    this.interpolationGainA = null;
    this.interpolationGainB = null;
    this.interpolationSourceGainA = null;
    this.interpolationSourceGainB = null;
    this.interpolationChainA = [];
    this.interpolationChainB = [];
    this.interpolationBufferDuration = 0;
    this.interpolationNodeMap = null;
    this.interpolationNodeKey = null;

    // Shared buffer cache
    this.bufferCache = new Map();      // url -> ToneAudioBuffer

    this.isPlaying = false;
    this.isPreviewing = false;
    this.normalizePlayback = false;
    this.dryNormalizeGain = 1;
    this.dryNormalizeReady = false;
    this.basePreviewGain = 0.6;
    this.baseFullGain = 0.8;
    this.fxMakeupGainDb = 0;
    this.fxBypass = false;
    this.dryAudioUrl = null;
  }

  // Initialization

  async init() {
    if (this.initialized) return;
    await Tone.start(); // unlock audio context after user gesture

    this.previewGain = new Tone.Gain(this.basePreviewGain).toDestination();
    this.fullBusGain = new Tone.Gain(this.baseFullGain).toDestination();
    this.fullOutGain = new Tone.Gain(1).connect(this.fullBusGain);
    this.fullMixGain = new Tone.Gain(1).connect(this.fullOutGain);

    this.initialized = true;
  }

  // Buffer loading and caching

  async loadBuffer(url) {
    // Shared fetch helper so repeated plays reuse Tone buffers.
    if (this.bufferCache.has(url)) return this.bufferCache.get(url);
    const buf = await new Promise((resolve, reject) => {
      const b = new Tone.ToneAudioBuffer(
        url,
        () => resolve(b),
        (err) => reject(err)
      );
    });
    this.bufferCache.set(url, buf);
    return buf;
  }

  clearCache() {
    this.bufferCache.clear();
    this.dryNormalizeGain = 1;
    this.dryNormalizeReady = false;
    this.dryAudioUrl = null;
  }

  setNormalizePlayback(enabled) {
    this.normalizePlayback = Boolean(enabled);
    this._applyPlaybackGain();
  }

  _applyPlaybackGain() {
    const scale = this._getNormalizeScale();
    if (this.previewPlayerSourceGain) {
      this._rampGain(this.previewPlayerSourceGain, scale, 0.05);
    }
    if (this.fullSourceGain) {
      this._rampGain(this.fullSourceGain, scale, 0.05);
    }
    if (this.interpolationSourceGainA) {
      this._rampGain(this.interpolationSourceGainA, scale, 0.05);
    }
    if (this.interpolationSourceGainB) {
      this._rampGain(this.interpolationSourceGainB, scale, 0.05);
    }
  }

  _getNormalizeScale() {
    return this.normalizePlayback ? this.dryNormalizeGain : 1;
  }

  _estimateRms(buffer) {
    try {
      const numChannels = buffer.numberOfChannels;
      if (!numChannels) return 1;
      let sumSq = 0;
      let count = 0;
      for (let ch = 0; ch < numChannels; ch++) {
        const arr = buffer.toArray(ch);
        for (let i = 0; i < arr.length; i++) {
          const v = arr[i];
          sumSq += v * v;
          count++;
        }
      }
      if (count === 0) return 1;
      return Math.sqrt(sumSq / count);
    } catch (err) {
      return 1;
    }
  }

  _estimatePeak(buffer) {
    try {
      const numChannels = buffer.numberOfChannels;
      if (!numChannels) return 1;
      let maxAbs = 0;
      for (let ch = 0; ch < numChannels; ch++) {
        const arr = buffer.toArray(ch);
        for (let i = 0; i < arr.length; i++) {
          const abs = Math.abs(arr[i]);
          if (abs > maxAbs) maxAbs = abs;
        }
      }
      return maxAbs || 1;
    } catch (err) {
      return 1;
    }
  }

  _computeGainScaleFromRms(rms, peak = 1) {
    if (rms <= 0) return 1;
    const targetRms = this._dbToGain(-3);
    const gain = targetRms / rms;
    const maxSafeGain = 0.95 / peak; // leave 5% headroom from clipping
    return Math.min(Math.max(gain, 0.1), maxSafeGain, 100);
  }

  _computeGainScale(buffer) {
    const rms = this._estimateRms(buffer);
    return this._computeGainScaleFromRms(rms);
  }

  _ensureDryNormalizeGain(buffer) {
    if (this.dryNormalizeReady) return;
    const rms = this._estimateRms(buffer);
    const peak = this._estimatePeak(buffer);
    this.dryNormalizeGain = this._computeGainScaleFromRms(rms, peak);
    this.dryNormalizeReady = true;
    console.log('[audioPlayer] dryNormalizeGain:', this.dryNormalizeGain);
    console.log('[audioPlayer] dryRms:', rms, 'targetRms:', this._dbToGain(-3), 'dryPeak:', peak);
  }

  async _loadDryBufferAndScale() {
    const url = this._getDryAudioUrl();
    const buffer = await this.loadBuffer(url);
    this._ensureDryNormalizeGain(buffer);
    return { buffer, sourceGainScale: this._getNormalizeScale() };
  }

  _getDryAudioUrl() {
    if (!this.dryAudioUrl) {
      this.dryAudioUrl = api.getDryAudioUrl(true);
    }
    return this.dryAudioUrl;
  }

  _dbToGain(db) {
    return Math.pow(10, db / 20);
  }

  // FX chain helpers

  _teardownChain(chain) {
    chain.forEach((node) => node.dispose?.());
    chain.length = 0;
  }

  _ensurePlayer(current) {
    return current || new Tone.Player({ autostart: false, loop: true });
  }

  _stopPlayer(player) {
    try { player.stop(); } catch (e) { /* ignore */ }
  }

  _ensureGain(current, value) {
    return current || new Tone.Gain(value);
  }

  _startPlayerWithRamp(player, gainNode, sourceGain, offset, fadeIn = 0.1, preFade = 0.02, targetGain = 1, sourceGainScale = 1) {
    this._rampGain(gainNode, 0, preFade);
    if (sourceGain) {
      this._rampGain(sourceGain, sourceGainScale, preFade);
    }
    player.start(0, offset);
    this._rampGain(gainNode, targetGain, fadeIn);
  }

  async _prepareDryPlayback(clockStart, bufferDurationOverride = null) {
    const { buffer, sourceGainScale } = await this._loadDryBufferAndScale();
    const bufferDuration = bufferDurationOverride || buffer.duration;
    const offset = this._computeOffset(clockStart, bufferDuration);
    return { buffer, sourceGainScale, bufferDuration, offset };
  }

  _rebuildChain(chain, player, gainNode, params, inputNode) {
    this._teardownChain(chain);
    return this._buildChain(player, gainNode, params, inputNode);
  }

  _buildChain(player, gainNode, params, inputNode = null) {
    // Converts backend-ish params to Tone nodes and inserts them between player/gain.
    // Disconnect only the player from any previous FX
    try { player.disconnect(); } catch (e) {}

    const effectiveParams = this.fxBypass ? {} : (params || {});
    const chain = [];
    const { nodes, nodeMap } = mapBackendParamsToTone(effectiveParams);
    let prev = inputNode || player;
    if (inputNode) {
      try { inputNode.disconnect(); } catch (e) {}
      player.connect(inputNode);
    }

    if (nodes.length === 0) {
      prev.connect(gainNode);       // gainNode is still connected to destination
    } else {
      nodes.forEach((node) => {
        prev.connect(node);
        prev = node;
      });
      prev.connect(gainNode);
    }
    chain.push(...nodes);
    return { chain, nodeMap };
  }

  setFxBypass(enabled) {
    this.fxBypass = Boolean(enabled);

    if (this.previewPlayer && this.previewPlayerGain) {
      const { chain } = this._rebuildChain(
        this.previewChain,
        this.previewPlayer,
        this.previewPlayerGain,
        this.lastPreview?.params || {},
        this.previewPlayerSourceGain
      );
      this.previewChain = chain;
    }

    if (this.interpolationCrossfadeActive && this.interpolationPlayerA && this.interpolationPlayerB) {
      const chainA = this._rebuildChain(
        this.interpolationChainA,
        this.interpolationPlayerA,
        this.interpolationGainA,
        this.lastFull?.paramsA || {},
        this.interpolationSourceGainA
      );
      const chainB = this._rebuildChain(
        this.interpolationChainB,
        this.interpolationPlayerB,
        this.interpolationGainB,
        this.lastFull?.paramsB || {},
        this.interpolationSourceGainB
      );
      this.interpolationChainA = chainA.chain;
      this.interpolationChainB = chainB.chain;
    } else if (this.fullPlayer && this.fullMixGain) {
      const built = this._rebuildChain(
        this.fullChain,
        this.fullPlayer,
        this.fullMixGain,
        this.lastFull?.params || {},
        this.fullSourceGain
      );
      this.fullChain = built.chain;
      if (this.interpolationActive) {
        this.interpolationNodeMap = built.nodeMap;
        this.interpolationNodeKey = this._getPluginKey(this.lastFull?.params || {});
      }
    }
  }


  // Playhead helpers

  _computeOffset(clockStart, bufferDuration) {
    if (!clockStart || bufferDuration <= 0) return 0;
    const elapsed = Tone.now() - clockStart;
    return elapsed % bufferDuration;
  }

  _rampGain(gainNode, target, duration = 0.05) {
    if (!gainNode || !gainNode.gain) return;
    const now = Tone.now();
    const current = gainNode.gain.value;
    gainNode.gain.cancelScheduledValues(now);
    gainNode.gain.setValueAtTime(current, now);
    gainNode.gain.linearRampToValueAtTime(target, now + duration);
  }

  _fadeAndDisposePlayer(player, gainNode, chain, fadeTime = 0.05, sourceGain = null) {
    if (!player) return;

    if (gainNode) {
      this._rampGain(gainNode, 0, fadeTime);
    }

    const disposeFn = () => {
      try { player.stop(); } catch (e) { /* ignore */ }
      try { player.dispose(); } catch (e) { /* ignore */ }
      if (gainNode?.dispose) {
        try { gainNode.dispose(); } catch (e) { /* ignore */ }
      }
      if (sourceGain?.dispose) {
        try { sourceGain.dispose(); } catch (e) { /* ignore */ }
      }
      if (chain) this._teardownChain(chain);
    };

    setTimeout(disposeFn, fadeTime * 1000);
  }

  // Preview playback API

  /**
   * Realtime hover preview.
   * Audio is a single continuous loop; playback continues from a shared clock
   * even when switching samples.
   */
  async playPreview(sampleIdx, params = {}, options = {}) {
    const restart = options.restart === true;
    const resume = options.resume === true;

    await this.init();
    // Ensure full playback isn't overlapping
    this.stopFull();

    const generation = ++this.previewGeneration;

    // Clock logic
    if (restart) {
      this.previewClockStart = Tone.now();
      this.previewPausedOffset = 0;
    } else if (resume && this.previewPausedOffset > 0) {
      this.previewClockStart = Tone.now() - this.previewPausedOffset;
      this.previewPausedOffset = 0;
    } else if (this.previewClockStart === null) {
      this.previewClockStart = Tone.now();
    }

    try {
      const { buffer, sourceGainScale } = await this._loadDryBufferAndScale();
      if (generation !== this.previewGeneration) return;
      const bufferDuration = buffer.duration;
      const offset = restart && !resume
        ? 0
        : this._computeOffset(this.previewClockStart, bufferDuration);
      const fade = restart ? 0.08 : 0.35;

      // Incoming player + gain
      const incomingPlayer = new Tone.Player({ autostart: false, loop: true });
      incomingPlayer.buffer = buffer;
      const incomingGain = new Tone.Gain(0).connect(this.previewGain);
      const incomingSourceGain = new Tone.Gain(sourceGainScale);
      const incomingBuilt = this._buildChain(
        incomingPlayer,
        incomingGain,
        params,
        incomingSourceGain
      );
      const incomingChain = incomingBuilt.chain;

      // Start new player first, using absolute time
      incomingPlayer.start(0, offset);

      // Crossfade: fade in incoming
      this._rampGain(incomingGain, 1, fade);
      this._rampGain(incomingSourceGain, sourceGainScale, fade);

      // Fade out/cleanup outgoing if it exists
      const outgoingPlayer = this.previewPlayer;
      const outgoingGain = this.previewPlayerGain;
      const outgoingSourceGain = this.previewPlayerSourceGain;
      const outgoingChain = this.previewChain.slice();

      if (outgoingPlayer) {
        this._fadeAndDisposePlayer(outgoingPlayer, outgoingGain, outgoingChain, fade, outgoingSourceGain);
      }

      // Switch references to new preview
      this.previewPlayer = incomingPlayer;
      this.previewPlayerGain = incomingGain;
      this.previewPlayerSourceGain = incomingSourceGain;
      this.previewChain = incomingChain;
      this.previewBufferDuration = bufferDuration;
      this.isPreviewing = true;
      this.lastPreview = { sampleIdx, params };
    } catch (err) {
      console.error('Preview playback error:', err);
      this.isPreviewing = false;
    }
  }

  stopPreview(options = {}) {
    const preservePause = options.preservePause === true;
    const immediate = options.immediate === true;

    // Invalidate any pending preview cleanup tied to previous generation
    this.previewGeneration++;

    const player = this.previewPlayer;
    const gain = this.previewPlayerGain;
    const sourceGain = this.previewPlayerSourceGain;
    const chain = this.previewChain.slice();

    this.previewPlayer = null;
    this.previewPlayerGain = null;
    this.previewPlayerSourceGain = null;
    this.previewChain = [];
    this.previewBufferDuration = 0;
    this.isPreviewing = false;

    if (!preservePause) {
      this.previewPausedOffset = 0;
      this.previewClockStart = null;
    }

    if (!player) return;

    if (immediate) {
      try { player.stop(); } catch (e) { /* ignore */ }
      try { player.dispose(); } catch (e) { /* ignore */ }
      if (gain?.dispose) {
        try { gain.dispose(); } catch (e) { /* ignore */ }
      }
      if (sourceGain?.dispose) {
        try { sourceGain.dispose(); } catch (e) { /* ignore */ }
      }
      this._teardownChain(chain);
    } else {
      this._fadeAndDisposePlayer(player, gain, chain, 0.05, sourceGain);
    }
  }

  // Full playback API

  async playFull(sampleIdx, params = {}, options = {}) {
    const resume = options.resume === true;

    await this.init();
    // Ensure preview isn't overlapping
    this.stopPreview();

    // Clock logic
    if (resume && this.fullPausedOffset > 0) {
      this.fullClockStart = Tone.now() - this.fullPausedOffset;
      this.fullPausedOffset = 0;
    } else if (this.fullClockStart === null) {
      this.fullClockStart = Tone.now();
    }

    try {
      const { buffer, sourceGainScale, bufferDuration, offset } =
        await this._prepareDryPlayback(this.fullClockStart);

      this.fullPlayer = this._ensurePlayer(this.fullPlayer);

      // If it was already playing, gently fade out before restarting
      if (this.isPlaying) {
        this._rampGain(this.fullOutGain, 0, 0.02);
        this._stopPlayer(this.fullPlayer);
      }

      this.fullPlayer.buffer = buffer;
      this.fullBufferDuration = bufferDuration;

      this.fullSourceGain = this._ensureGain(this.fullSourceGain, sourceGainScale);

      this._teardownChain(this.fullChain);
      const fullBuilt = this._buildChain(
        this.fullPlayer,
        this.fullMixGain,
        params,
        this.fullSourceGain
      );
      this.fullChain = fullBuilt.chain;

      // quick fade to avoid clicks
      this._startPlayerWithRamp(
        this.fullPlayer,
        this.fullOutGain,
        this.fullSourceGain,
        offset,
        0.1,
        0.02,
        1,
        sourceGainScale
      );

      this.isPlaying = true;
      this.lastFull = { sampleIdx, params };
    } catch (err) {
      console.error('Full playback error:', err);
      this.isPlaying = false;
    }
  }

  stopFull(options = {}) {
    const preservePause = options.preservePause === true;
    const immediate = options.immediate === true;

    if (this.interpolationCrossfadeActive) {
      this._stopCrossfade(immediate);
    }

    const player = this.fullPlayer;
    const gain = this.fullOutGain;
    const chain = this.fullChain.slice();

    this.fullPlayer = null;
    this.fullChain = [];
    this.fullBufferDuration = 0;
    this.isPlaying = false;
    this.interpolationActive = false;
    this.interpolationCrossfadeActive = false;

    if (!preservePause) {
      this.fullPausedOffset = 0;
      this.fullClockStart = null;
    }

    if (!player) return;

    const cleanup = () => {
      try { player.stop(); } catch (e) { /* ignore */ }
      try { player.dispose(); } catch (e) { /* ignore */ }
      if (this.fullSourceGain) {
        try { this.fullSourceGain.disconnect(); } catch (e) { /* ignore */ }
        try { this.fullSourceGain.dispose(); } catch (e) { /* ignore */ }
        this.fullSourceGain = null;
      }
      this._teardownChain(chain);
    };

    if (immediate) {
      cleanup();
    } else {
      // Fade out master full gain then dispose
      const fade = 0.05;
      this._rampGain(gain, 0, fade);
      setTimeout(cleanup, fade * 1000);
    }
  }

  // Global control

  getStatus() {
    const previewActive = this.isPreviewing && this.previewBufferDuration > 0;
    const fullActive = this.isPlaying && this.fullBufferDuration > 0;

    const previewPosition = previewActive
      ? this._computeOffset(this.previewClockStart, this.previewBufferDuration)
      : null;
    const fullPosition = fullActive
      ? this._computeOffset(this.fullClockStart, this.fullBufferDuration)
      : null;

    return {
      preview: previewActive
        ? { position: previewPosition, duration: this.previewBufferDuration }
        : null,
      full: fullActive
        ? {
            position: fullPosition,
            duration: this.fullBufferDuration,
            isInterpolation: this.interpolationActive  // Add interpolation mode indicator
          }
        : null,
    };
  }

  async getWaveformData(sampleIdx, points = 220) {
    // Handle 'dry' keyword for dry audio waveform
    const url = sampleIdx === 'dry'
      ? this._getDryAudioUrl()
      : api.getAudioUrl(sampleIdx);
    const buffer = await this.loadBuffer(url);
    const channelData = buffer.toArray(0);
    const windowSize = Math.max(1, Math.floor(channelData.length / points));
    const waveform = [];

    // First pass: collect min/max values
    const rawWaveform = [];
    for (let i = 0; i < points; i++) {
      const start = i * windowSize;
      if (start >= channelData.length) break;

      const end = Math.min(channelData.length, start + windowSize);
      let min = 1;
      let max = -1;
      for (let s = start; s < end; s++) {
        const v = channelData[s];
        if (v < min) min = v;
        if (v > max) max = v;
      }

      rawWaveform.push({ min, max });
    }

    // Normalize to full height: find global min/max
    let globalMin = 0;
    let globalMax = 0;
    rawWaveform.forEach(({ min, max }) => {
      if (min < globalMin) globalMin = min;
      if (max > globalMax) globalMax = max;
    });

    const range = Math.max(Math.abs(globalMin), Math.abs(globalMax)) || 1;

    // Normalize each point to [-1, 1] range
    rawWaveform.forEach(({ min, max }) => {
      waveform.push({
        min: min / range,
        max: max / range
      });
    });

    return { waveform, duration: buffer.duration };
  }

  // Stop, pause, and resume

  stop() {
    this.stopFull({ immediate: true });
    this.stopPreview({ immediate: true });
  }

  pause() {
    const status = this.getStatus();

    if (status.preview) {
      this.previewPausedOffset = status.preview.position % status.preview.duration;
    } else {
      this.previewPausedOffset = 0;
    }

    if (status.full) {
      this.fullPausedOffset = status.full.position % status.full.duration;
    } else {
      this.fullPausedOffset = 0;
    }

    this.stopFull({ preservePause: true });
    this.stopPreview({ preservePause: true });

    this.previewClockStart = null;
    this.fullClockStart = null;
    this.interpolationActive = false;
  }

  resume() {
    if (this.fullPausedOffset > 0 && this.lastFull) {
      if (this.lastFull.mode === 'interpolation') {
        this.setInterpolationParams(this.lastFull.params || {}, { resume: true });
        return;
      }
      if (typeof this.lastFull.sampleIdx === 'number') {
        this.playFull(this.lastFull.sampleIdx, this.lastFull.params || {}, { resume: true });
        return;
      }
    }
    if (this.previewPausedOffset > 0 && this.lastPreview) {
      this.playPreview(this.lastPreview.sampleIdx, this.lastPreview.params || {}, { resume: true });
    }
  }

  async setInterpolationParams(params = {}, options = {}) {
    // Public entry point used by the interpolation slider to (re)apply FX params.
    await this.init();
    const forceRestart = options.restart === true;

    if (this.interpolationCrossfadeActive) {
      this._stopCrossfade(true);
    }

    if (!this.interpolationActive || forceRestart || !this.fullPlayer) {
      await this._startInterpolationPlayback(params, options);
    } else {
      await this._updateInterpolationChain(params);
    }
  }

  async setInterpolationCrossfade(paramsA = {}, paramsB = {}, t = 0.5, options = {}) {
    await this.init();
    const forceRestart = options.restart === true;
    if (!this.interpolationCrossfadeActive || forceRestart || !this.interpolationPlayerA || !this.interpolationPlayerB) {
      await this._startInterpolationCrossfade(paramsA, paramsB, t, options);
    } else {
      this._updateInterpolationCrossfade(t);
    }
  }

  async _startInterpolationPlayback(params = {}, options = {}) {
    // Spins up the dedicated loop that interpolation uses (always fed by /api/dry).
    this.stopPreview();

    const resume = options.resume === true && this.fullPausedOffset > 0;
    if (resume) {
      this.fullClockStart = Tone.now() - this.fullPausedOffset;
      this.fullPausedOffset = 0;
    } else {
      this.fullClockStart = Tone.now();
    }

    const { buffer, sourceGainScale, bufferDuration, offset } =
      await this._prepareDryPlayback(this.fullClockStart);

    this.fullPlayer = this._ensurePlayer(this.fullPlayer);
    this._stopPlayer(this.fullPlayer);

    this.fullPlayer.buffer = buffer;
    this.fullBufferDuration = bufferDuration;

    this._teardownChain(this.fullChain);
    this.fullSourceGain = this._ensureGain(this.fullSourceGain, sourceGainScale);
    const built = this._buildChain(
      this.fullPlayer,
      this.fullMixGain,
      params,
      this.fullSourceGain
    );
    this.fullChain = built.chain;
    this.interpolationNodeMap = built.nodeMap;
    this.interpolationNodeKey = this._getPluginKey(params);

    this._startPlayerWithRamp(
      this.fullPlayer,
      this.fullOutGain,
      this.fullSourceGain,
      offset,
      0.1,
      0.02,
      1,
      sourceGainScale
    );

    this.isPlaying = true;
    this.interpolationActive = true;
    this.lastFull = { sampleIdx: null, params, mode: 'interpolation' };
  }

  async _startInterpolationCrossfade(paramsA = {}, paramsB = {}, t = 0.5, options = {}) {
    this.stopPreview();
    if (this.fullPlayer) {
      this.stopFull({ immediate: true });
    }

    const resume = options.resume === true && this.fullPausedOffset > 0;
    if (resume) {
      this.fullClockStart = Tone.now() - this.fullPausedOffset;
      this.fullPausedOffset = 0;
    } else {
      this.fullClockStart = Tone.now();
    }

    const { buffer, sourceGainScale, bufferDuration, offset } =
      await this._prepareDryPlayback(this.fullClockStart);

    this.interpolationPlayerA = new Tone.Player({ autostart: false, loop: true });
    this.interpolationPlayerB = new Tone.Player({ autostart: false, loop: true });
    this.interpolationGainA = new Tone.Gain(0).connect(this.fullMixGain);
    this.interpolationGainB = new Tone.Gain(0).connect(this.fullMixGain);
    this.interpolationSourceGainA = new Tone.Gain(sourceGainScale);
    this.interpolationSourceGainB = new Tone.Gain(sourceGainScale);

    this.interpolationPlayerA.buffer = buffer;
    this.interpolationPlayerB.buffer = buffer;
    this.interpolationBufferDuration = bufferDuration;

    this._teardownChain(this.interpolationChainA);
    this._teardownChain(this.interpolationChainB);
    const chainA = this._buildChain(
      this.interpolationPlayerA,
      this.interpolationGainA,
      paramsA,
      this.interpolationSourceGainA
    );
    const chainB = this._buildChain(
      this.interpolationPlayerB,
      this.interpolationGainB,
      paramsB,
      this.interpolationSourceGainB
    );
    this.interpolationChainA = chainA.chain;
    this.interpolationChainB = chainB.chain;

    this._rampGain(this.fullOutGain, 0, 0.02);
    this._rampGain(this.interpolationSourceGainA, sourceGainScale, 0.02);
    this._rampGain(this.interpolationSourceGainB, sourceGainScale, 0.02);
    this.interpolationPlayerA.start(0, offset);
    this.interpolationPlayerB.start(0, offset);
    this._rampGain(this.fullOutGain, 1, 0.1);

    this._updateInterpolationCrossfade(t);

    this.isPlaying = true;
    this.interpolationActive = true;
    this.interpolationCrossfadeActive = true;
    this.lastFull = { sampleIdx: null, paramsA, paramsB, mode: 'crossfade' };
  }

  _updateInterpolationCrossfade(t = 0.5) {
    if (!this.interpolationGainA || !this.interpolationGainB) return;
    const clamped = Math.min(Math.max(t, 0), 1);
    const gainA = Math.cos(clamped * Math.PI * 0.5);
    const gainB = Math.sin(clamped * Math.PI * 0.5);
    this._rampGain(this.interpolationGainA, gainA, 0.05);
    this._rampGain(this.interpolationGainB, gainB, 0.05);
  }

  _stopCrossfade(immediate = false) {
    const fade = 0.05;
    const dispose = () => {
      if (this.interpolationPlayerA) {
        try { this.interpolationPlayerA.stop(); } catch (e) {}
        try { this.interpolationPlayerA.dispose(); } catch (e) {}
      }
      if (this.interpolationPlayerB) {
        try { this.interpolationPlayerB.stop(); } catch (e) {}
        try { this.interpolationPlayerB.dispose(); } catch (e) {}
      }
      if (this.interpolationGainA?.dispose) {
        try { this.interpolationGainA.dispose(); } catch (e) {}
      }
      if (this.interpolationGainB?.dispose) {
        try { this.interpolationGainB.dispose(); } catch (e) {}
      }
      try { this.interpolationGainA?.disconnect(); } catch (e) {}
      try { this.interpolationGainB?.disconnect(); } catch (e) {}
      if (this.interpolationSourceGainA?.dispose) {
        try { this.interpolationSourceGainA.dispose(); } catch (e) {}
      }
      if (this.interpolationSourceGainB?.dispose) {
        try { this.interpolationSourceGainB.dispose(); } catch (e) {}
      }
      this._teardownChain(this.interpolationChainA);
      this._teardownChain(this.interpolationChainB);
      this.interpolationPlayerA = null;
      this.interpolationPlayerB = null;
      this.interpolationGainA = null;
      this.interpolationGainB = null;
      this.interpolationSourceGainA = null;
      this.interpolationSourceGainB = null;
      this.interpolationChainA = [];
      this.interpolationChainB = [];
      this.interpolationBufferDuration = 0;
      this.interpolationCrossfadeActive = false;
    };

    if (immediate) {
      dispose();
    } else {
      if (this.interpolationGainA) this._rampGain(this.interpolationGainA, 0, fade);
      if (this.interpolationGainB) this._rampGain(this.interpolationGainB, 0, fade);
      setTimeout(dispose, fade * 1000);
    }
  }

  async _updateInterpolationChain(params = {}) {
    // Rebuilds the Tone FX nodes in place while gently ducking the gain.
    if (!this.fullPlayer) {
      await this._startInterpolationPlayback(params);
      return;
    }

    const nextKey = this._getPluginKey(params);
    if (!this.interpolationNodeMap || nextKey !== this.interpolationNodeKey) {
      this._rampGain(this.fullOutGain, 0.15, 0.05);
      await new Promise((resolve) => setTimeout(resolve, 60));
      this._teardownChain(this.fullChain);
      const built = this._buildChain(this.fullPlayer, this.fullMixGain, params, this.fullSourceGain);
      this.fullChain = built.chain;
      this.interpolationNodeMap = built.nodeMap;
      this.interpolationNodeKey = nextKey;
      this._rampGain(this.fullOutGain, 0.8, 0.06);
    } else {
      applyParamsToToneNodes(params, this.interpolationNodeMap, 0.15);
    }
    this.lastFull = { sampleIdx: null, params, mode: 'interpolation' };
  }

  _getPluginKey(params = {}) {
    const plugins = params?.plugins ?? params ?? {};
    // Normalize plugin IDs to match fxUtils.getChainKeyFromParams()
    // This ensures chorus_0 and chorus_2 are treated as the same FX type
    const normalizedKeys = Object.keys(plugins).map(key => key.replace(/_(\d+)$/, '')).sort();
    return normalizedKeys.join('|');
  }
}

// Export singleton instance
export const audioPlayer = new AudioPlayer();
