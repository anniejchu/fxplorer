<script>
  import { createEventDispatcher } from 'svelte';

  export let params = null;
  export let displayState = 'none';
  export let sampleInfo = null;
  export let readonly = false;
  export let fxBypass = false;

  const dispatch = createEventDispatcher();


  const VIS_WIDTH = 260;
  const VIS_HEIGHT = 90;

  const PARAM_BOUNDS = {
    gain_db: { min: -24, max: 24, step: 0.5 },
    cutoff_hz: { min: 20, max: 20000, step: 10 },
    highpass_cutoff_hz: { min: 50, max: 12000, step: 10 },
    lowpass_cutoff_hz: { min: 300, max: 16000, step: 10 },
    freq_hz: { min: 20, max: 20000, step: 10 },
    frequency_hz: { min: 20, max: 20000, step: 10 },
    q: { min: 0.1, max: 8.0, step: 0.1 },
    drive_db: { min: 0, max: 40, step: 0.5 },
    bit_depth: { min: 1, max: 16, step: 1 },
    threshold_db: { min: -70, max: 0, step: 0.5 },
    ratio: { min: 1.0, max: 30.0, step: 0.1 },
    attack_ms: { min: 0.01, max: 120, step: 0.1 },
    release_ms: { min: 10, max: 1000, step: 5 },
    delay_seconds: { min: 0.01, max: 1.0, step: 0.01 },
    feedback: { min: 0.0, max: 0.95, step: 0.01 },
    mix: { min: 0.0, max: 1.0, step: 0.01 },
    rate_hz: { min: 0.05, max: 12.0, step: 0.1 },
    depth: { min: 0.0, max: 1.0, step: 0.01 },
    centre_delay_ms: { min: 2, max: 30, step: 0.5 },
    centre_frequency_hz: { min: 80, max: 6000, step: 10 },
    room_size: { min: 0.0, max: 1.0, step: 0.01 },
    damping: { min: 0.0, max: 1.0, step: 0.01 },
    wet_level: { min: 0.0, max: 1.0, step: 0.01 },
    dry_level: { min: 0.0, max: 1.0, step: 0.01 },
    width: { min: 0.0, max: 1.0, step: 0.01 },
  };

  const FX_LABELS = {
    gain: 'Gain',
    eq: 'EQ',
    compressor: 'Compressor',
    limiter: 'Limiter',
    gate: 'Gate',
    reverb: 'Reverb',
    delay: 'Delay',
    chorus: 'Chorus',
    phaser: 'Phaser',
    distortion: 'Distortion',
    highpass: 'High-pass',
    lowpass: 'Low-pass',
  };

  function getParamBounds(paramKey) {
    const parts = paramKey.split('.');
    const baseName = parts[parts.length - 1];
    if (PARAM_BOUNDS[baseName]) {
      return PARAM_BOUNDS[baseName];
    }
    return { min: -50, max: 50, step: 0.1 };
  }

  function getFxParamBounds(kind, paramKey) {
    const base = getParamBounds(paramKey);
    if (kind === 'chorus') {
      if (paramKey === 'centre_delay_ms') {
        return { ...base, min: 3, max: 20 };
      }
      if (paramKey === 'feedback') {
        return { ...base, max: 0.95 };
      }
      if (paramKey === 'mix') {
        return { ...base, max: 1.0 };
      }
      if (paramKey === 'rate_hz') {
        return { ...base, max: 10.0 };
      }
      if (paramKey === 'depth') {
        return { ...base, min: 0.05 };
      }
    }
    if (kind === 'phaser') {
      if (paramKey === 'rate_hz') {
        return { ...base, min: 0.01, max: 12.0 };
      }
      if (paramKey === 'depth') {
        return { ...base, min: 0.05, max: 1.0 };
      }
      if (paramKey === 'centre_frequency_hz') {
        return { ...base, min: 80, max: 6000 };
      }
      if (paramKey === 'feedback') {
        return { ...base, max: 0.75 };
      }
      if (paramKey === 'mix') {
        return { ...base, min: 0.1, max: 0.95 };
      }
    }
    if (kind === 'delay') {
      if (paramKey === 'delay_seconds') {
        return { ...base, min: 0.001, max: 1.0 };
      }
      if (paramKey === 'feedback') {
        return { ...base, max: 0.95 };
      }
      if (paramKey === 'mix') {
        return { ...base, min: 0.05, max: 0.85 };
      }
    }
    if (kind === 'reverb') {
      if (paramKey === 'room_size') {
        return { ...base, min: 0.01, max: 0.99 };
      }
      if (paramKey === 'damping') {
        return { ...base, max: 0.95 };
      }
      if (paramKey === 'wet_level') {
        return { ...base, min: 0.05, max: 0.95 };
      }
      if (paramKey === 'dry_level') {
        return { ...base, min: 0.2, max: 1.0 };
      }
      if (paramKey === 'width') {
        return { ...base, min: 0.0, max: 1.0 };
      }
    }
    if (kind === 'compressor') {
      if (paramKey === 'threshold_db') {
        return { ...base, min: -60, max: -1 };
      }
      if (paramKey === 'ratio') {
        return { ...base, min: 1.2, max: 20.0 };
      }
      if (paramKey === 'attack_ms') {
        return { ...base, min: 0.01, max: 120 };
      }
      if (paramKey === 'release_ms') {
        return { ...base, min: 10, max: 1000 };
      }
    }
    if (kind === 'limiter') {
      if (paramKey === 'threshold_db') {
        return { ...base, min: -12, max: -0.5 };
      }
      if (paramKey === 'release_ms') {
        return { ...base, min: 10, max: 200 };
      }
    }
    if (kind === 'gate') {
      if (paramKey === 'threshold_db') {
        return { ...base, min: -70, max: -10 };
      }
      if (paramKey === 'ratio') {
        return { ...base, min: 2, max: 30 };
      }
      if (paramKey === 'attack_ms') {
        return { ...base, min: 0.1, max: 20 };
      }
      if (paramKey === 'release_ms') {
        return { ...base, min: 10, max: 800 };
      }
    }
    if (kind === 'distortion') {
      if (paramKey === 'drive_db') {
        return { ...base, min: 0, max: 40 };
      }
    }
    if (kind === 'highpass' || kind === 'lowpass') {
      if (paramKey === 'cutoff_hz') {
        return { ...base, min: 20, max: 20000 };
      }
    }
    if (kind === 'gain') {
      if (paramKey === 'gain_db') {
        return { ...base, min: -24, max: 24 };
      }
    }
    return base;
  }

  function getFxKind(pluginName) {
    const name = pluginName.toLowerCase();
    if (name.includes('eq')) return 'eq';
    if (name.includes('compressor')) return 'compressor';
    if (name.includes('limiter')) return 'limiter';
    if (name.includes('gate')) return 'gate';
    if (name.includes('reverb')) return 'reverb';
    if (name.includes('delay')) return 'delay';
    if (name.includes('chorus')) return 'chorus';
    if (name.includes('phaser')) return 'phaser';
    if (name.includes('distortion')) return 'distortion';
    if (name.includes('highpass')) return 'highpass';
    if (name.includes('lowpass')) return 'lowpass';
    if (name.includes('gain')) return 'gain';
    return 'fx';
  }

  function getFxLabel(pluginName) {
    const kind = getFxKind(pluginName);
    return FX_LABELS[kind] || 'FX';
  }

  function emitParamChange(plugin, path, value) {
    if (readonly || fxBypass) return;
    dispatch('paramChange', { plugin, path, value });
  }

  function handleBypassToggle() {
    dispatch('fxBypassChange', { enabled: !fxBypass });
  }


  function formatParamValue(value) {
    if (typeof value === 'number') {
      return Number.isInteger(value) ? value.toString() : value.toFixed(2);
    }
    return String(value);
  }

  function formatLabel(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function toLogX(freq, width) {
    const min = 20;
    const max = 20000;
    const clamped = Math.max(min, Math.min(max, freq));
    const ratio = Math.log10(clamped / min) / Math.log10(max / min);
    return ratio * width;
  }

  function buildEqCurvePath(bands, width, height) {
    if (!bands || !bands.length) return '';
    const mid = height * 0.5;
    const points = [];
    const steps = 80;
    for (let i = 0; i <= steps; i++) {
      const x = (i / steps) * width;
      const freq = 20 * Math.pow(20000 / 20, i / steps);
      let gainSum = 0;
      bands.forEach((band) => {
        const center = band.freq_hz || 1000;
        const q = Math.max(0.1, band.q || 1);
        const gain = band.gain_db || 0;
        const dist = Math.log2(freq / center);
        const spread = 0.6 / q;
        const weight = Math.exp(-(dist * dist) / (spread * spread));
        gainSum += gain * weight;
      });
      const y = mid - (gainSum / 24) * (height * 0.45);
      points.push(`${x},${Math.max(4, Math.min(height - 4, y))}`);
    }
    return `M${points.join(' L')}`;
  }

  function buildCompressorCurvePath(threshold = -24, ratio = 4, width, height) {
    const inMin = -60;
    const inMax = 0;
    const points = [];
    for (let i = 0; i <= 60; i++) {
      const inputDb = inMin + (i / 60) * (inMax - inMin);
      const outputDb = inputDb <= threshold
        ? inputDb
        : threshold + (inputDb - threshold) / Math.max(1, ratio);
      const x = ((inputDb - inMin) / (inMax - inMin)) * width;
      const y = height - ((outputDb - inMin) / (inMax - inMin)) * height;
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }

  function normalizeRange(value, min, max) {
    if (value === undefined || value === null || !isFinite(value)) return 0;
    if (max === min) return 0;
    return Math.min(1, Math.max(0, (value - min) / (max - min)));
  }

  function buildGateCurvePath(threshold = -40, ratio = 4, width, height) {
    const inMin = -70;
    const inMax = 0;
    const points = [];
    for (let i = 0; i <= 70; i++) {
      const inputDb = inMin + (i / 70) * (inMax - inMin);
      const outputDb = inputDb <= threshold
        ? threshold + (inputDb - threshold) / Math.max(1, ratio)
        : inputDb;
      const x = ((inputDb - inMin) / (inMax - inMin)) * width;
      const y = height - ((outputDb - inMin) / (inMax - inMin)) * height;
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }

  function buildDistortionCurvePath(driveDb = 12, width, height) {
    const drive = Math.max(0.5, driveDb / 12);
    const points = [];
    for (let i = 0; i <= 60; i++) {
      const xNorm = (i / 60) * 2 - 1;
      const yNorm = Math.tanh(xNorm * drive);
      const x = ((xNorm + 1) / 2) * width;
      const y = height - ((yNorm + 1) / 2) * height;
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }

  function buildLfoPath(rate = 1, depth = 0.5, width, height) {
    const points = [];
    const cycles = Math.max(0.5, Math.min(3, rate / 2));
    for (let i = 0; i <= 60; i++) {
      const x = (i / 60) * width;
      const y = height * 0.5 + Math.sin((i / 60) * Math.PI * 2 * cycles) * depth * (height * 0.35);
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }

  function buildChorusDelayLines(delayMs = 6, depth = 0.5, width, height) {
    const delayNorm = normalizeRange(delayMs, PARAM_BOUNDS.centre_delay_ms.min, PARAM_BOUNDS.centre_delay_ms.max);
    const centerX = 10 + delayNorm * (width - 20);
    const span = 20 + depth * (width * 0.35);
    const ys = [height * 0.3, height * 0.5, height * 0.7];
    const paths = [];
    ys.forEach((y, idx) => {
      const points = [];
      const phase = idx * Math.PI * 0.5;
      for (let i = 0; i <= 40; i++) {
        const t = i / 40;
        const x = Math.max(8, Math.min(width - 8, centerX - span * 0.5 + t * span));
        const wobble = Math.sin(t * Math.PI * 2 + phase) * depth * (height * 0.08);
        points.push(`${x},${y + wobble}`);
      }
      paths.push(`M${points.join(' L')}`);
    });
    return paths;
  }

  function buildChorusOrbit(delayMs = 6, depth = 0.5, rate = 1, width, height) {
    const minSize = Math.min(width, height);
    const delayNorm = normalizeRange(delayMs, PARAM_BOUNDS.centre_delay_ms.min, PARAM_BOUNDS.centre_delay_ms.max);
    const baseRadius = 10 + delayNorm * (minSize * 0.32);
    const depthRadius = 4 + depth * (minSize * 0.18);
    const inner = Math.max(8, baseRadius - depthRadius);
    const outer = Math.min(minSize * 0.5 - 6, baseRadius + depthRadius);
    const dotCount = Math.max(2, Math.min(6, Math.round(rate) + 1));
    const dots = [];
    for (let i = 0; i < dotCount; i++) {
      const angle = (i / dotCount) * Math.PI * 2 + Math.PI / 6;
      const wobble = Math.sin(i * 1.7) * depthRadius * 0.35;
      const radius = baseRadius + wobble;
      dots.push({
        x: width * 0.5 + Math.cos(angle) * radius,
        y: height * 0.5 + Math.sin(angle) * radius,
      });
    }
    return {
      cx: width * 0.5,
      cy: height * 0.5,
      inner,
      outer,
      dots,
    };
  }

  function buildRateTicks(rate = 1, width) {
    const count = Math.max(1, Math.min(5, Math.round(rate)));
    const ticks = [];
    const start = width - 12 - count * 6;
    for (let i = 0; i < count; i++) {
      ticks.push({ x: start + i * 6 });
    }
    return ticks;
  }

  function buildPhaserNotches(depth = 0.5, centreFrequency = 800, width, height) {
    const notches = [];
    const count = 4;
    const spread = Math.max(0.15, depth) * 0.25;
    const centreX = toLogX(centreFrequency, width);
    for (let i = 0; i < count; i++) {
      const offset = (i - (count - 1) / 2) * spread * width;
      const x = Math.min(width - 8, Math.max(8, centreX + offset));
      const notchDepth = height * (0.35 + depth * 0.35);
      notches.push({ x, y: height * 0.5, depth: notchDepth });
    }
    return notches;
  }

  function buildPhaserCurvePath(depth = 0.5, centreFrequency = 800, width, height) {
    const base = height * 0.45;
    const notchCount = 5;
    const spread = Math.max(0.15, depth) * 0.3;
    const centreX = toLogX(centreFrequency, width);
    const notchPositions = [];
    for (let i = 0; i < notchCount; i++) {
      const offset = (i - (notchCount - 1) / 2) * spread * width;
      notchPositions.push(Math.min(width - 10, Math.max(10, centreX + offset)));
    }
    const points = [];
    for (let i = 0; i <= 90; i++) {
      const x = (i / 90) * width;
      let dip = 0;
      notchPositions.forEach((nx) => {
        const dist = (x - nx) / (width * 0.08);
        dip += Math.exp(-dist * dist);
      });
      const depthScale = 0.08 + depth * 0.28;
      const y = base + dip * (height * depthScale);
      points.push(`${x},${Math.min(height - 6, y)}`);
    }
    return { path: `M${points.join(' L')}`, notches: notchPositions };
  }

  function buildChorusWaveformLines(delayMs = 6, depth = 0.5, rate = 1, mix = 0.5, width, height) {
    const mid = height * 0.45;
    const amp = height * 0.18;
    const delayNorm = normalizeRange(delayMs, PARAM_BOUNDS.centre_delay_ms.min, PARAM_BOUNDS.centre_delay_ms.max);
    const offsetBase = (delayNorm * 0.12 + 0.02) * width;
    const wobble = depth * 0.06 * width;
    const speed = Math.max(0.4, Math.min(4, rate));
    const points = (phase, xOffset) => {
      const pts = [];
      for (let i = 0; i <= 60; i++) {
        const t = i / 60;
        const x = t * width;
        const wobbleShift = Math.sin(t * Math.PI * 2 * speed + phase) * wobble;
        const y = mid + Math.sin(t * Math.PI * 2) * amp;
        pts.push(`${Math.max(0, Math.min(width, x + xOffset + wobbleShift))},${y}`);
      }
      return `M${pts.join(' L')}`;
    };
    const dry = points(0, 0);
    const wetOpacity = Math.min(0.9, Math.max(0.2, mix));
    const voices = [
      { d: points(Math.PI * 0.5, offsetBase), opacity: wetOpacity },
      { d: points(Math.PI, -offsetBase * 0.8), opacity: wetOpacity * 0.85 },
      { d: points(Math.PI * 1.5, offsetBase * 1.2), opacity: wetOpacity * 0.7 },
    ];
    return { dry, voices };
  }

  function buildReverbEtcPath(roomSize = 0.4, damping = 0.4, width, height) {
    const tail = Math.max(0.25, Math.min(1, 0.25 + roomSize * 0.85));
    const damp = Math.max(0.2, Math.min(1, 1 - damping * 0.85));
    const points = [];
    for (let i = 0; i <= 80; i++) {
      const t = i / 80;
      const x = t * width;
      const early = t < 0.2 ? (1 - t / 0.2) * 0.6 : 0;
      const decay = Math.exp(-t / tail) * (0.45 + damp * 0.55);
      const y = height - (early + decay) * height;
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }

  function buildChorusSpread(depth = 0.5, mix = 0.5, width = 220, height = 70) {
    const spread = Math.max(0.1, Math.min(1, (depth * 0.65 + mix * 0.45)));
    const centerX = width * 0.5;
    const maxOffset = width * 0.38 * spread;
    const voiceCount = 3;
    const bars = [];
    for (let i = 0; i < voiceCount; i++) {
      const t = voiceCount === 1 ? 0.5 : i / (voiceCount - 1);
      const x = centerX - maxOffset + t * maxOffset * 2;
      const h = height * (0.35 + mix * 0.35 + (i === 1 ? 0.1 : 0));
      bars.push({ x, h });
    }
    return {
      spread,
      bars,
      centerX,
      maxOffset,
    };
  }

  function buildImpulseTail(roomSize = 0.4, damping = 0.4, width = 220, height = 70) {
    const peak = height * 0.85;
    const tail = Math.max(0.2, Math.min(1, 0.25 + roomSize * 0.75));
    const damp = Math.max(0.1, Math.min(1, 1 - damping * 0.8));
    const points = [];
    for (let i = 0; i <= 60; i++) {
      const t = i / 60;
      const x = t * width;
      const y = height - (peak * Math.exp(-t / tail) * (0.4 + damp * 0.6));
      points.push(`${x},${y}`);
    }
    return `M${points.join(' L')}`;
  }
  function buildFilterPath(kind, cutoff = 1000, width, height) {
    const xCut = toLogX(cutoff, width);
    if (kind === 'lowpass') {
      return `M0,${height * 0.3} L${xCut},${height * 0.3} L${width},${height * 0.8}`;
    }
    return `M0,${height * 0.8} L${xCut},${height * 0.8} L${width},${height * 0.3}`;
  }

  function buildDelayTaps(delaySeconds = 0.3, feedback = 0.3) {
    const taps = [];
    const count = 4;
    for (let i = 1; i <= count; i++) {
      const position = (delaySeconds * i) / 1.5;
      const x = Math.min(1, position);
      const amp = Math.pow(feedback || 0.3, i - 1);
      taps.push({ x, amp });
    }
    return taps;
  }

  function buildReverbDecayBars(roomSize = 0.4, damping = 0.4, width = 220, height = 70) {
    const base = 0.3 + roomSize * 0.7;
    const highScale = 1 - damping * 0.7;
    const bars = [
      { label: 'Low', value: base },
      { label: 'Mid', value: base * (0.85 + highScale * 0.15) },
      { label: 'High', value: base * (0.55 + highScale * 0.35) },
    ];
    const barWidth = width / (bars.length * 2);
    return bars.map((bar, idx) => ({
      ...bar,
      x: width * 0.18 + idx * barWidth * 1.6,
      y: height - bar.value * height,
      h: bar.value * height,
      w: barWidth,
    }));
  }

  function buildReverbRoom(roomSize = 0.4, damping = 0.4, width = 220, height = 80) {
    const roomWidth = width * (0.55 + roomSize * 0.35);
    const roomHeight = height * 0.55;
    const roomX = (width - roomWidth) / 2;
    const roomY = height * 0.18;
    const reflectionsBase = [
      { x: 0.15, y: 0.2 },
      { x: 0.75, y: 0.18 },
      { x: 0.2, y: 0.75 },
      { x: 0.7, y: 0.7 },
      { x: 0.45, y: 0.35 },
      { x: 0.6, y: 0.5 },
      { x: 0.35, y: 0.6 },
      { x: 0.8, y: 0.45 },
    ];
    const count = Math.max(3, Math.min(reflectionsBase.length, Math.round(3 + roomSize * 5)));
    const reflections = reflectionsBase.slice(0, count).map((pt) => ({
      x: roomX + pt.x * roomWidth,
      y: roomY + pt.y * roomHeight,
    }));
    return {
      roomX,
      roomY,
      roomWidth,
      roomHeight,
      reflections,
      glow: Math.max(0.1, (1 - damping) * 0.8),
    };
  }

  function renderParam(pluginName, value, path = []) {
    if (typeof value === 'number') {
      return [{ pluginName, value, path }];
    }
    if (Array.isArray(value)) {
      return value.flatMap((item, idx) => renderParam(pluginName, item, [...path, idx]));
    }
    if (typeof value === 'object' && value !== null) {
      return Object.entries(value).flatMap(([key, val]) =>
        renderParam(pluginName, val, [...path, key])
      );
    }
    return [];
  }

  function flattenParams(pluginName, pluginParams) {
    return Object.entries(pluginParams).flatMap(([key, value]) =>
      renderParam(pluginName, value, [key])
    );
  }

  function getControlId(pluginName, path) {
    const safePlugin = String(pluginName).replace(/[^a-zA-Z0-9_-]/g, '-');
    const safePath = path.map((part) => String(part).replace(/[^a-zA-Z0-9_-]/g, '-')).join('-');
    return `fx-${safePlugin}-${safePath}`;
  }

  $: plugins = params ? Object.entries(params) : [];
  $: stateColor = displayState === 'interpolation' ? 'var(--accent-3)'
    : displayState === 'selected' ? 'var(--success)'
    : displayState === 'hover' ? 'var(--accent)'
    : 'var(--muted-2)';
</script>

<section class="unified-fx-panel" class:bypass={fxBypass} style="--state-color: {stateColor}">
  <div class="panel-header">
    <div class="header-left">
      <span class="panel-icon"></span>
      <span class="panel-title">FX Panel</span>
    </div>
    <div class="header-right">
      <button
        type="button"
        class="bypass-toggle"
        on:click={handleBypassToggle}
        aria-pressed={fxBypass}
      >
        {fxBypass ? 'FX Off' : 'FX On'}
      </button>
      {#if displayState === 'interpolation'}
        <span class="state-pill interpolation">INTERP</span>
      {:else if displayState === 'selected'}
        <span class="state-pill selected">LIVE</span>
      {:else if displayState === 'hover'}
        <span class="state-pill hover">PREVIEW</span>
      {/if}
      {#if sampleInfo}
        <span class="sample-label">{sampleInfo.name || `#${sampleInfo.index}`}</span>
      {/if}
    </div>
  </div>

  {#if params && Object.keys(params).length > 0}
    <div class="fx-grid">
      {#each plugins as [pluginName, pluginParams]}
        {@const kind = getFxKind(pluginName)}
        {@const label = getFxLabel(pluginName)}
        <section class={`fx-card ${kind === 'eq' ? 'fx-card-eq' : ''} ${kind === 'reverb' ? 'fx-card-reverb' : ''}`}>
          <header class="fx-card-header">
            <div>
              <p class="fx-label">{label}</p>
              <p class="fx-id">{pluginName}</p>
            </div>
            <span class="fx-kind">{kind.toUpperCase()}</span>
          </header>

          <div class="fx-body">
            <div class={`fx-viz ${kind}`}>
              {#if kind === 'eq'}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT * 0.5} L${VIS_WIDTH} ${VIS_HEIGHT * 0.5}`} />
                  <path
                    class="viz-line"
                    d={buildEqCurvePath(pluginParams.bands || [], VIS_WIDTH, VIS_HEIGHT)}
                  />
                </svg>
              {:else if kind === 'compressor'}
                {@const attackNorm = normalizeRange(pluginParams.attack_ms, PARAM_BOUNDS.attack_ms.min, PARAM_BOUNDS.attack_ms.max)}
                {@const releaseNorm = normalizeRange(pluginParams.release_ms, PARAM_BOUNDS.release_ms.min, PARAM_BOUNDS.release_ms.max)}
                {@const thresholdNorm = normalizeRange(pluginParams.threshold_db, PARAM_BOUNDS.threshold_db.min, PARAM_BOUNDS.threshold_db.max)}
                {@const thresholdX = thresholdNorm * VIS_WIDTH}
                {@const thresholdY = VIS_HEIGHT - thresholdNorm * VIS_HEIGHT}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT} L${VIS_WIDTH} 0`} />
                  <rect class="viz-region" x={thresholdX} y="0" width={VIS_WIDTH - thresholdX} height={thresholdY} />
                  <line class="viz-marker" x1={thresholdX} x2={thresholdX} y1="0" y2={VIS_HEIGHT} />
                  <line class="viz-marker" x1="0" x2={VIS_WIDTH} y1={thresholdY} y2={thresholdY} />
                  <path
                    class="viz-line"
                    d={buildCompressorCurvePath(pluginParams.threshold_db, pluginParams.ratio, VIS_WIDTH, VIS_HEIGHT)}
                  />
                  <text class="viz-label" x={VIS_WIDTH - 44} y="14">R {formatParamValue(pluginParams.ratio || 0)}</text>
                  <rect class="viz-bar attack" x="6" y={VIS_HEIGHT - 16} width={Math.max(6, attackNorm * (VIS_WIDTH - 12))} height="4" />
                  <rect class="viz-bar release" x="6" y={VIS_HEIGHT - 8} width={Math.max(6, releaseNorm * (VIS_WIDTH - 12))} height="4" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 18}>A</text>
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 10}>R</text>
                </svg>
              {:else if kind === 'gate'}
                {@const attackNorm = normalizeRange(pluginParams.attack_ms, PARAM_BOUNDS.attack_ms.min, PARAM_BOUNDS.attack_ms.max)}
                {@const releaseNorm = normalizeRange(pluginParams.release_ms, PARAM_BOUNDS.release_ms.min, PARAM_BOUNDS.release_ms.max)}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT} L${VIS_WIDTH} 0`} />
                  <path
                    class="viz-line"
                    d={buildGateCurvePath(pluginParams.threshold_db, pluginParams.ratio, VIS_WIDTH, VIS_HEIGHT)}
                  />
                  <rect class="viz-bar attack" x="6" y={VIS_HEIGHT - 16} width={Math.max(6, attackNorm * (VIS_WIDTH - 12))} height="4" />
                  <rect class="viz-bar release" x="6" y={VIS_HEIGHT - 8} width={Math.max(6, releaseNorm * (VIS_WIDTH - 12))} height="4" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 18}>A</text>
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 10}>R</text>
                </svg>
              {:else if kind === 'limiter'}
                {@const releaseNorm = normalizeRange(pluginParams.release_ms, PARAM_BOUNDS.release_ms.min, PARAM_BOUNDS.release_ms.max)}
                {@const thresholdNorm = normalizeRange(pluginParams.threshold_db, PARAM_BOUNDS.threshold_db.min, PARAM_BOUNDS.threshold_db.max)}
                {@const ceilingY = VIS_HEIGHT - thresholdNorm * VIS_HEIGHT}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT} L${VIS_WIDTH} 0`} />
                  <rect class="viz-region" x="0" y="0" width={VIS_WIDTH} height={ceilingY} />
                  <line class="viz-marker" x1="0" x2={VIS_WIDTH} y1={ceilingY} y2={ceilingY} />
                  <path
                    class="viz-line"
                    d={buildCompressorCurvePath(pluginParams.threshold_db, 20, VIS_WIDTH, VIS_HEIGHT)}
                  />
                  <rect class="viz-bar release" x="6" y={VIS_HEIGHT - 10} width={Math.max(6, releaseNorm * (VIS_WIDTH - 12))} height="4" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 12}>R</text>
                </svg>
              {:else if kind === 'distortion'}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT * 0.5} L${VIS_WIDTH} ${VIS_HEIGHT * 0.5}`} />
                  <path
                    class="viz-line"
                    d={buildDistortionCurvePath(pluginParams.drive_db, VIS_WIDTH, VIS_HEIGHT)}
                  />
                </svg>
              {:else if kind === 'chorus'}
                {@const delayNorm = normalizeRange(pluginParams.centre_delay_ms, PARAM_BOUNDS.centre_delay_ms.min, PARAM_BOUNDS.centre_delay_ms.max)}
                {@const feedbackNorm = normalizeRange(pluginParams.feedback, PARAM_BOUNDS.feedback.min, PARAM_BOUNDS.feedback.max)}
                {@const mixNorm = normalizeRange(pluginParams.mix, PARAM_BOUNDS.mix.min, PARAM_BOUNDS.mix.max)}
                {@const chorusLines = buildChorusWaveformLines(pluginParams.centre_delay_ms, pluginParams.depth, pluginParams.rate_hz, pluginParams.mix, VIS_WIDTH, VIS_HEIGHT)}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="chorus-dry-line" d={chorusLines.dry} />
                  {#each chorusLines.voices as voice}
                    <path class="chorus-voice-line" d={voice.d} style={`opacity:${voice.opacity};`} />
                  {/each}
                  <text class="viz-label" x="8" y="12">Dry</text>
                  <text class="viz-label" x={VIS_WIDTH - 36} y="12">Voices</text>
                  <rect class="viz-bar delay" x="6" y={VIS_HEIGHT - 18} width={Math.max(6, delayNorm * (VIS_WIDTH - 12))} height="4" />
                  <rect class="viz-bar feedback" x="6" y={VIS_HEIGHT - 12} width={Math.max(6, feedbackNorm * (VIS_WIDTH - 12))} height="4" />
                  <rect class="viz-bar mix" x="6" y={VIS_HEIGHT - 6} width={Math.max(6, mixNorm * (VIS_WIDTH - 12))} height="3" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 20}>D</text>
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 14}>F</text>
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 8}>M</text>
                </svg>
              {:else if kind === 'phaser'}
                {@const feedbackNorm = normalizeRange(pluginParams.feedback, PARAM_BOUNDS.feedback.min, PARAM_BOUNDS.feedback.max)}
                {@const mixNorm = normalizeRange(pluginParams.mix, PARAM_BOUNDS.mix.min, PARAM_BOUNDS.mix.max)}
                {@const phaserCurve = buildPhaserCurvePath(pluginParams.depth, pluginParams.centre_frequency_hz || 800, VIS_WIDTH, VIS_HEIGHT)}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT * 0.7} L${VIS_WIDTH} ${VIS_HEIGHT * 0.7}`} />
                  <path class="viz-line" d={phaserCurve.path} />
                  {#each phaserCurve.notches as notchX}
                    <path class="phaser-notch" d={`M${notchX - 6} ${VIS_HEIGHT * 0.62} L${notchX} ${VIS_HEIGHT * 0.7} L${notchX + 6} ${VIS_HEIGHT * 0.62}`} />
                  {/each}
                  <text class="viz-label" x="8" y={VIS_HEIGHT * 0.82}>100</text>
                  <text class="viz-label" x={VIS_WIDTH * 0.42} y={VIS_HEIGHT * 0.82}>1k</text>
                  <text class="viz-label" x={VIS_WIDTH * 0.78} y={VIS_HEIGHT * 0.82}>10k</text>
                  <rect class="viz-bar feedback" x="6" y={VIS_HEIGHT - 12} width={Math.max(6, feedbackNorm * (VIS_WIDTH - 12))} height="4" />
                  <rect class="viz-bar mix" x="6" y={VIS_HEIGHT - 6} width={Math.max(6, mixNorm * (VIS_WIDTH - 12))} height="3" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 14}>F</text>
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 8}>M</text>
                  <text class="viz-label" x={Math.min(VIS_WIDTH - 16, toLogX(pluginParams.centre_frequency_hz || 800, VIS_WIDTH) + 4)} y="12">CF</text>
                </svg>
              {:else if kind === 'delay'}
                {@const mixNorm = normalizeRange(pluginParams.mix, PARAM_BOUNDS.mix.min, PARAM_BOUNDS.mix.max)}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT * 0.75} L${VIS_WIDTH} ${VIS_HEIGHT * 0.75}`} />
                  {#each buildDelayTaps(pluginParams.delay_seconds, pluginParams.feedback) as tap}
                    <circle
                      cx={tap.x * VIS_WIDTH}
                      cy={VIS_HEIGHT * 0.75 - tap.amp * 30}
                      r={4 + tap.amp * 4}
                      class="viz-dot"
                    />
                  {/each}
                  <rect class="viz-bar mix" x="6" y={VIS_HEIGHT - 8} width={Math.max(6, mixNorm * (VIS_WIDTH - 12))} height="4" />
                  <text class="viz-label" x="6" y={VIS_HEIGHT - 10}>Mix</text>
                </svg>
              {:else if kind === 'reverb'}
                <div class="reverb-viz">
                  <div
                    class="reverb-room"
                    style={`--room:${Math.max(0.2, pluginParams.room_size || 0.3)}; --damp:${Math.max(0.1, pluginParams.damping || 0.3)}; --width:${Math.max(0.2, pluginParams.width || 0.6)}; --wet:${Math.max(0, pluginParams.wet_level || 0)}; --dry:${Math.max(0, pluginParams.dry_level || 0.7)}`}
                  >
                    <div class="room-core"></div>
                    <div class="room-walls"></div>
                    <div class="room-reflections"></div>
                    <div class="room-width"></div>
                  </div>
                  <div class="reverb-bars">
                    <div class="bar">
                      <span>Room</span>
                      <div class="bar-fill" style={`width:${Math.min(100, (pluginParams.room_size || 0) * 100)}%`}></div>
                    </div>
                    <div class="bar">
                      <span>Damp</span>
                      <div class="bar-fill" style={`width:${Math.min(100, (pluginParams.damping || 0) * 100)}%`}></div>
                    </div>
                    <div class="bar">
                      <span>Wet/Dry</span>
                      <div class="bar-fill" style={`width:${Math.min(100, ((pluginParams.wet_level || 0) / Math.max(0.01, (pluginParams.wet_level || 0) + (pluginParams.dry_level || 0.7))) * 100)}%`}></div>
                    </div>
                  </div>
                </div>
              {:else if kind === 'highpass' || kind === 'lowpass'}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <path
                    class="viz-line"
                    d={buildFilterPath(kind, pluginParams.cutoff_hz || 1000, VIS_WIDTH, VIS_HEIGHT)}
                  />
                </svg>
              {:else if kind === 'gain'}
                {@const gainNorm = normalizeRange(pluginParams.gain_db, PARAM_BOUNDS.gain_db.min, PARAM_BOUNDS.gain_db.max)}
                <svg viewBox={`0 0 ${VIS_WIDTH} ${VIS_HEIGHT}`} class="viz-svg">
                  <rect class="viz-bar gain" x="6" y={VIS_HEIGHT * 0.6} width={Math.max(6, gainNorm * (VIS_WIDTH - 12))} height={VIS_HEIGHT * 0.18} />
                  <path class="viz-grid" d={`M0 ${VIS_HEIGHT * 0.6} L${VIS_WIDTH} ${VIS_HEIGHT * 0.6}`} />
                  <text class="viz-label" x="6" y={VIS_HEIGHT * 0.55}>Gain</text>
                </svg>
              {:else}
                <div class="fallback-viz">FX Preview</div>
              {/if}
            </div>

            <div class="fx-controls">
              {#if kind === 'eq'}
                {#each pluginParams.bands || [] as band, idx}
                  <div class="band-row">
                    <p class="band-label">Band {idx + 1}</p>
                    <div class="control-row">
                      <label for={getControlId(pluginName, ['bands', idx, 'freq_hz'])}>Freq</label>
                      <input
                        id={getControlId(pluginName, ['bands', idx, 'freq_hz'])}
                        type="range"
                        min={getFxParamBounds('eq', 'freq_hz').min}
                        max={getFxParamBounds('eq', 'freq_hz').max}
                        step={getFxParamBounds('eq', 'freq_hz').step}
                        value={band.freq_hz}
                        disabled={readonly || fxBypass}
                        on:input={(e) => emitParamChange(pluginName, ['bands', idx, 'freq_hz'], parseFloat(e.target.value))}
                      />
                      <span>{formatParamValue(band.freq_hz)} Hz</span>
                    </div>
                    <div class="control-row">
                      <label for={getControlId(pluginName, ['bands', idx, 'gain_db'])}>Gain</label>
                      <input
                        id={getControlId(pluginName, ['bands', idx, 'gain_db'])}
                        type="range"
                        min={getFxParamBounds('eq', 'gain_db').min}
                        max={getFxParamBounds('eq', 'gain_db').max}
                        step={getFxParamBounds('eq', 'gain_db').step}
                        value={band.gain_db}
                        disabled={readonly || fxBypass}
                        on:input={(e) => emitParamChange(pluginName, ['bands', idx, 'gain_db'], parseFloat(e.target.value))}
                      />
                      <span>{formatParamValue(band.gain_db)} dB</span>
                    </div>
                    <div class="control-row">
                      <label for={getControlId(pluginName, ['bands', idx, 'q'])}>Q</label>
                      <input
                        id={getControlId(pluginName, ['bands', idx, 'q'])}
                        type="range"
                        min={getFxParamBounds('eq', 'q').min}
                        max={getFxParamBounds('eq', 'q').max}
                        step={getFxParamBounds('eq', 'q').step}
                        value={band.q}
                        disabled={readonly || fxBypass}
                        on:input={(e) => emitParamChange(pluginName, ['bands', idx, 'q'], parseFloat(e.target.value))}
                      />
                      <span>{formatParamValue(band.q)}</span>
                    </div>
                  </div>
                {/each}
              {:else}
                {#each Object.entries(pluginParams) as [key, value]}
                  {#if typeof value === 'number'}
                    {@const bounds = getFxParamBounds(kind, key)}
                    {@const isKnob = ['mix', 'depth', 'wet_level', 'dry_level', 'width', 'feedback', 'drive_db', 'room_size', 'damping'].includes(key)}
                    <div class={`control-row ${isKnob ? 'knob' : 'slider'}`}>
                      <label for={getControlId(pluginName, [key])}>{formatLabel(key)}</label>
                      {#if isKnob}
                        <div class="knob-visual" class:readonly={readonly}>
                          <input
                            id={getControlId(pluginName, [key])}
                            type="range"
                            min={bounds.min}
                            max={bounds.max}
                            step={bounds.step}
                            value={value}
                            disabled={readonly || fxBypass}
                            class="knob-slider"
                            on:input={(e) => emitParamChange(pluginName, [key], parseFloat(e.target.value))}
                          />
                          <div class="knob-indicator" style="transform: rotate({((value - bounds.min) / (bounds.max - bounds.min)) * 270 - 135}deg)"></div>
                        </div>
                        <span>{formatParamValue(value)}</span>
                      {:else}
                        <input
                          id={getControlId(pluginName, [key])}
                          type="range"
                          min={bounds.min}
                          max={bounds.max}
                          step={bounds.step}
                          value={value}
                          disabled={readonly || fxBypass}
                          on:input={(e) => emitParamChange(pluginName, [key], parseFloat(e.target.value))}
                        />
                        <span>{formatParamValue(value)}</span>
                      {/if}
                    </div>
                  {/if}
                {/each}
              {/if}
            </div>
          </div>

          <details class="fx-all param-details">
            <summary class="expand-toggle">
              <span class="toggle-icon">▶</span>
              All parameters
            </summary>
            <div class="param-list">
              {#each flattenParams(pluginName, pluginParams) as param}
                {@const bounds = getFxParamBounds(getFxKind(param.pluginName), param.path[param.path.length - 1])}
                <div class="param-row">
                  <span class="param-key">{param.path.join(' › ')}</span>
                  <input
                    type="number"
                    aria-label={`${getFxLabel(param.pluginName)} ${param.path.join(' ')}`}
                    min={bounds.min}
                    max={bounds.max}
                    step={bounds.step}
                    value={param.value}
                    disabled={readonly || fxBypass}
                    class:readonly={readonly || fxBypass}
                    on:input={(e) => emitParamChange(param.pluginName, param.path, parseFloat(e.target.value))}
                  />
                </div>
              {/each}
            </div>
          </details>
        </section>
      {/each}
    </div>
  {:else}
    <div class="empty-state">
      <p class="empty-message">Hover or select a sample to view FX parameters</p>
    </div>
  {/if}
</section>

<style>
  .unified-fx-panel {
    background: linear-gradient(to bottom, #0f0f0f 0%, #0a0a0a 100%);
    border: 1px solid #1f2937;
    border-radius: 10px;
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #1f2937;
    background: rgba(15, 15, 15, 0.5);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .panel-icon {
    font-size: 1.2rem;
  }

  .panel-title {
    font-size: 0.9rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #e5e7eb;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .bypass-toggle {
    border: 1px solid #334155;
    background: rgba(15, 23, 42, 0.8);
    color: #e2e8f0;
    padding: 0.25rem 0.55rem;
    border-radius: 999px;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
  }

  .bypass-toggle:hover {
    border-color: #94a3b8;
  }

  .unified-fx-panel.bypass .fx-body,
  .unified-fx-panel.bypass .fx-all {
    opacity: 0.45;
    filter: grayscale(0.4);
  }

  .state-pill {
    font-size: 0.65rem;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .state-pill.hover {
    background: rgba(59, 130, 246, 0.2);
    color: var(--accent);
    border: 1px solid rgba(59, 130, 246, 0.4);
  }

  .state-pill.selected {
    background: rgba(16, 185, 129, 0.2);
    color: var(--success);
    border: 1px solid rgba(16, 185, 129, 0.4);
    animation: pulse 2s ease-in-out infinite;
  }

  .state-pill.interpolation {
    background: rgba(168, 85, 247, 0.2);
    color: var(--accent-3);
    border: 1px solid rgba(168, 85, 247, 0.4);
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .sample-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #9ca3af;
  }

  .fx-grid {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .fx-card {
    border: 1px solid #1f2937;
    border-radius: 12px;
    background: rgba(8, 8, 10, 0.6);
    overflow: hidden;
  }

  .fx-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: rgba(12, 12, 16, 0.8);
    border-bottom: 1px solid #1f2937;
  }

  .fx-label {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--state-color);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .fx-id {
    margin: 0.25rem 0 0;
    font-size: 0.75rem;
    color: var(--muted-2);
  }

  .fx-kind {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.4);
    color: #cbd5f5;
  }

  .fx-body {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.8rem;
    padding: 0.9rem 1rem 1rem;
  }

  @media (min-width: 960px) {
    .fx-body {
      grid-template-columns: 1fr;
      align-items: start;
    }
  }

  .fx-viz {
    background: rgba(9, 9, 12, 0.8);
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 0.6rem;
    min-height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .fx-viz.eq {
    min-height: 56px;
    padding: 0.15rem;
  }

  .fx-card-eq .fx-controls {
    gap: 0.45rem;
  }

  .fx-card-eq .fx-body {
    gap: 0.2rem;
    padding-top: 0.4rem;
    align-items: start;
    grid-template-columns: 1fr;
  }

  .fx-card-eq .fx-viz {
    margin-bottom: 0;
    align-self: start;
    height: auto;
  }

  .viz-svg {
    width: 100%;
    height: 100%;
  }

  .viz-grid {
    stroke: rgba(148, 163, 184, 0.3);
    stroke-width: 1;
    fill: none;
  }

  .viz-line {
    stroke: var(--state-color);
    stroke-width: 2;
    fill: none;
  }

  .viz-voice {
    stroke: rgba(248, 250, 252, 0.95);
    stroke-width: 2.2;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .chorus-orbit {
    stroke: rgba(148, 163, 184, 0.4);
    stroke-width: 1.5;
    fill: none;
  }

  .chorus-orbit.inner {
    stroke: rgba(148, 163, 184, 0.25);
    stroke-dasharray: 4 4;
  }

  .chorus-center {
    fill: rgba(248, 250, 252, 0.85);
  }

  .chorus-voice {
    fill: rgba(59, 130, 246, 0.9);
  }

  .chorus-width-track {
    fill: rgba(148, 163, 184, 0.25);
  }

  .chorus-width-fill {
    fill: rgba(59, 130, 246, 0.6);
  }

  .chorus-centerline {
    stroke: rgba(248, 250, 252, 0.7);
    stroke-width: 1.2;
  }

  .chorus-voice-bar {
    fill: rgba(59, 130, 246, 0.85);
  }

  .chorus-dry-line {
    stroke: rgba(248, 250, 252, 0.9);
    stroke-width: 1.6;
    fill: none;
  }

  .chorus-voice-line {
    stroke: rgba(59, 130, 246, 0.85);
    stroke-width: 1.4;
    fill: none;
  }



  .viz-notch {
    stroke: rgba(96, 165, 250, 0.95);
    stroke-width: 2.4;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .phaser-notch {
    fill: rgba(96, 165, 250, 0.95);
  }

  .viz-bar {
    fill: rgba(148, 163, 184, 0.35);
  }

  .viz-region {
    fill: rgba(56, 189, 248, 0.12);
  }

  .viz-bar.attack {
    fill: rgba(56, 189, 248, 0.7);
  }

  .viz-bar.release {
    fill: rgba(248, 113, 113, 0.7);
  }

  .viz-bar.delay {
    fill: rgba(34, 211, 238, 0.7);
  }

  .viz-bar.feedback {
    fill: rgba(59, 130, 246, 0.7);
  }

  .viz-bar.mix {
    fill: rgba(251, 191, 36, 0.7);
  }

  .viz-bar.gain {
    fill: rgba(34, 197, 94, 0.7);
  }

  .viz-label {
    font-size: 8px;
    fill: #cbd5f5;
  }

  .viz-tick {
    fill: rgba(226, 232, 240, 0.7);
  }

  .viz-marker {
    stroke: rgba(226, 232, 240, 0.7);
    stroke-width: 1.5;
    stroke-dasharray: 3 3;
  }

  .viz-dot {
    fill: var(--state-color);
    opacity: 0.85;
  }

  .fallback-viz {
    font-size: 0.8rem;
    color: #94a3b8;
  }

  .reverb-decay {
    border-radius: 8px;
  }

  .reverb-bg {
    fill: rgba(10, 10, 14, 0.6);
  }

  .reverb-bar {
    fill: rgba(59, 130, 246, 0.7);
  }

  .reverb-tail {
    stroke: rgba(148, 163, 184, 0.5);
    stroke-width: 1.6;
    fill: none;
  }

  .reverb-impulse {
    stroke: rgba(59, 130, 246, 0.9);
    stroke-width: 2;
    fill: none;
  }

  .reverb-time-axis {
    stroke: rgba(148, 163, 184, 0.35);
    stroke-width: 1;
  }

  .reverb-etc {
    stroke: rgba(14, 165, 233, 0.85);
    stroke-width: 1.4;
    fill: none;
  }

  .reverb-shell {
    fill: rgba(8, 8, 10, 0.7);
    stroke: rgba(148, 163, 184, 0.25);
    stroke-width: 1;
  }

  .reverb-source {
    fill: rgba(248, 250, 252, 0.85);
  }

  .reverb-reflection {
    fill: rgba(148, 163, 184, 0.6);
  }

  .reverb-glow {
    fill: rgba(59, 130, 246, 0.45);
  }


  .reverb-viz {
    width: 100%;
    display: grid;
    gap: 0.6rem;
  }

  .reverb-room {
    position: relative;
    height: 80px;
    border-radius: 12px;
    background: radial-gradient(circle at 30% 30%, rgba(59, 130, 246, 0.25), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(148, 163, 184, 0.25);
    overflow: hidden;
  }

  .room-core {
    position: absolute;
    inset: 18% 22%;
    border-radius: 10px;
    background: rgba(14, 165, 233, calc(0.15 + var(--wet) * 0.6));
    transform: scale(calc(0.5 + var(--room)));
    box-shadow: 0 0 calc(8px + var(--damp) * 18px) rgba(59, 130, 246, 0.35);
  }

  .room-walls {
    position: absolute;
    inset: 10% 14%;
    border-radius: 12px;
    border: 1px dashed rgba(148, 163, 184, 0.4);
    transform: scale(calc(0.6 + var(--room) * 0.7));
  }

  .room-reflections {
    position: absolute;
    inset: 12% 12%;
    background: radial-gradient(circle at 20% 30%, rgba(148, 163, 184, 0.35), transparent 40%),
      radial-gradient(circle at 80% 20%, rgba(148, 163, 184, 0.25), transparent 38%),
      radial-gradient(circle at 30% 80%, rgba(59, 130, 246, 0.25), transparent 45%),
      radial-gradient(circle at 70% 75%, rgba(59, 130, 246, 0.18), transparent 50%);
    filter: blur(calc(1px + var(--damp) * 3px));
    opacity: calc(0.2 + (1 - var(--damp)) * 0.6);
  }

  .room-width {
    position: absolute;
    left: 50%;
    top: 50%;
    width: calc(40% + var(--width) * 50%);
    height: 4px;
    background: linear-gradient(90deg, rgba(56, 189, 248, 0.2), rgba(56, 189, 248, 0.8));
    transform: translate(-50%, -50%);
    border-radius: 999px;
  }

  .reverb-bars {
    display: grid;
    gap: 0.5rem;
  }

  .reverb-bars .bar {
    display: grid;
    grid-template-columns: 50px 1fr;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.75rem;
    color: #94a3b8;
  }

  .bar-fill {
    height: 8px;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(59, 130, 246, 0.6), rgba(167, 139, 250, 0.8));
  }

  .fx-controls {
    display: grid;
    gap: 0.65rem;
  }

  .band-row {
    border: 1px solid #1f2937;
    border-radius: 8px;
    padding: 0.6rem;
    background: rgba(12, 12, 16, 0.6);
    display: grid;
    gap: 0.45rem;
  }

  .band-label {
    margin: 0;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #cbd5f5;
  }

  .control-row {
    display: grid;
    grid-template-columns: 80px 1fr 70px;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: #cbd5f5;
  }

  .control-row.knob {
    grid-template-columns: 80px auto 1fr;
  }

  .control-row input[type='range'] {
    width: 100%;
  }

  .control-row span {
    text-align: right;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #9ca3af;
  }

  .knob-visual {
    position: relative;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1a1a1e 0%, #0f0f12 100%);
    border: 2px solid #3a3a3a;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.4);
  }

  .knob-visual.readonly {
    opacity: 0.5;
    border-color: #2a2a2a;
  }

  .knob-slider {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
    border-radius: 50%;
  }

  .knob-indicator {
    position: absolute;
    top: 8%;
    left: 50%;
    width: 3px;
    height: 40%;
    background: var(--state-color);
    border-radius: 2px;
    transform-origin: bottom center;
    margin-left: -1.5px;
  }

  .fx-all {
    border-top: 1px solid #1f2937;
    padding: 0.6rem 1rem 1rem;
  }

  .param-details {
    margin: 0;
  }

  .param-details summary {
    list-style: none;
  }

  .param-details summary::-webkit-details-marker {
    display: none;
  }

  .expand-toggle {
    width: 100%;
    background: transparent;
    border: none;
    color: #9ca3af;
    text-align: left;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
    padding: 0.25rem 0;
  }

  .toggle-icon {
    color: var(--state-color);
    display: inline-block;
    transition: transform 0.2s ease;
  }

  .param-details[open] .toggle-icon {
    transform: rotate(90deg);
  }

  .param-list {
    margin-top: 0.6rem;
    display: grid;
    gap: 0.4rem;
  }

  .param-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.5rem;
    background: rgba(20, 20, 24, 0.3);
    border-radius: 4px;
  }

  .param-key {
    font-size: 0.75rem;
    color: #9ca3af;
    flex: 1;
  }

  .param-row input[type='number'] {
    width: 90px;
    padding: 0.25rem 0.35rem;
    border-radius: 4px;
    border: 1px solid #2f2f2f;
    background: #0f0f0f;
    color: #f8fafc;
    font-size: 0.75rem;
  }

  .param-row input[type='number'].readonly,
  .param-row input[type='number']:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: #1a1a1a;
    border-color: #252525;
    color: #9ca3af;
  }

  .empty-state {
    padding: 2rem 1.5rem;
    text-align: center;
  }

  .empty-message {
    margin: 0;
    color: var(--muted-2);
    font-size: 0.875rem;
  }
</style>
