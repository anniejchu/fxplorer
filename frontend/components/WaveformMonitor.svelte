<script>
export let state = { mode: 'idle', position: 0, duration: 0, label: '', hoverMode: 'smooth', fxBypass: false };
  export let waveform = [];
  export let loading = false;

  const viewWidth = 120;
  const viewHeight = 56;

  $: progress =
    state.duration > 0 ? ((state.position % state.duration) / state.duration) : 0;

  $: areaPath = waveform?.length ? buildAreaPath(waveform, viewWidth, viewHeight) : '';

  function buildAreaPath(data, width, height) {
    if (!data.length) return '';

    const upper = [];
    const lower = [];
    const denom = Math.max(1, data.length - 1);

    data.forEach((point, i) => {
      const x = (i / denom) * width;
      const yMax = (1 - point.max) * 0.5 * height;
      const yMin = (1 - point.min) * 0.5 * height;
      upper.push(`${x},${yMax}`);
      lower.push(`${x},${yMin}`);
    });

    const upperPath = upper
      .map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt}`)
      .join(' ');
    const lowerPath = lower
      .reverse()
      .map((pt) => `L${pt}`)
      .join(' ');

    return `${upperPath} ${lowerPath} Z`;
  }


  function formatTime(seconds) {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  $: modeLabel =
    state.mode === 'full'
      ? 'Selected'
      : state.mode === 'preview'
      ? 'Hover'
      : 'Idle';

  $: fxLabel = state.fxBypass ? 'Dry' : 'FX';

  let dragActive = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  function startDrag(event) {
    if (event.button !== 0) return;
    dragActive = true;
    dragStartX = event.clientX - dragOffsetX;
    dragStartY = event.clientY - dragOffsetY;
  }

  function handleDragMove(event) {
    if (!dragActive) return;
    dragOffsetX = event.clientX - dragStartX;
    dragOffsetY = event.clientY - dragStartY;
  }

  function stopDrag() {
    dragActive = false;
  }
</script>

<svelte:window
  on:mousemove={handleDragMove}
  on:mouseup={stopDrag}
/>

<div
  class="waveform-monitor"
  style={`transform: translate(-50%, 0) translate(${dragOffsetX}px, ${dragOffsetY}px);`}
>
  <div class="header" on:mousedown={startDrag}>
    <div class="title">
      <span class="dot {state.mode}"></span>
      <span>Playback map</span>
    </div>
    <div class="time">
      {formatTime(state.position)} / {formatTime(state.duration)}
    </div>
  </div>

  <div class="label-row">
    <div class="mode-pill {state.mode}">{modeLabel}</div>
    <div class="desc">
      {#if state.mode === 'preview'}
        Hover · {state.label || 'Previewing'} · {state.hoverMode === 'restart' ? 'Restart' : 'Smooth'} · {fxLabel}
      {:else if state.mode === 'full'}
        Selected · {state.label || 'Playing sample'} · {fxLabel}
      {:else}
        Hover or click a point to see the playhead
      {/if}
    </div>
  </div>

  <div class="waveform-shell">
    {#if loading}
      <div class="placeholder">Loading waveform…</div>
    {:else if waveform?.length}
      <svg viewBox={`0 0 ${viewWidth} ${viewHeight}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="wfFill" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.15" />
            <stop offset="100%" stop-color="var(--accent-3)" stop-opacity="0.18" />
          </linearGradient>
        </defs>
        <path
          d={areaPath}
          fill="url(#wfFill)"
          stroke="var(--accent)"
          stroke-opacity="0.5"
          stroke-width="0.6"
        />
        <line
          x1={viewWidth * progress}
          x2={viewWidth * progress}
          y1="0"
          y2={viewHeight}
          stroke="#fbbf24"
          stroke-width="1.4"
        />
      </svg>
    {:else}
      <div class="placeholder">No waveform yet</div>
    {/if}
  </div>
</div>

<style>
  .waveform-monitor {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    width: 520px;
    max-width: calc(100% - 2rem);
    background: rgba(14, 14, 18, 0.92);
    border: 1px solid #1f2937;
    border-radius: 12px;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    padding: 0.75rem 1rem;
    color: #e5e7eb;
    pointer-events: auto;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.9rem;
    color: #9ca3af;
    cursor: move;
    user-select: none;
  }

  .title {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    color: #e5e7eb;
    font-weight: 600;
  }

  .time {
    font-family: 'Courier New', monospace;
    color: #a5b4fc;
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.08);
  }

  .dot.preview {
    background: #22d3ee;
    box-shadow: 0 0 0 6px rgba(34, 211, 238, 0.1);
  }

  .dot.full {
    background: var(--accent-3);
    box-shadow: 0 0 0 6px rgba(167, 139, 250, 0.12);
  }

  .dot.idle {
    background: #4b5563;
    box-shadow: 0 0 0 6px rgba(75, 85, 99, 0.12);
  }

  .label-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0.4rem 0 0.6rem 0;
  }

  .mode-pill {
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border: 1px solid #1f2937;
    background: #111827;
    color: #cdd5f5;
  }

  .mode-pill.preview {
    color: #22d3ee;
    border-color: rgba(34, 211, 238, 0.35);
    background: rgba(34, 211, 238, 0.1);
  }

  .mode-pill.full {
    color: #c4b5fd;
    border-color: rgba(167, 139, 250, 0.4);
    background: rgba(167, 139, 250, 0.12);
  }

  .desc {
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .waveform-shell {
    border: 1px solid #1f2937;
    background: radial-gradient(circle at 20% 20%, rgba(99, 102, 241, 0.08), transparent 40%),
      #0b0c10;
    border-radius: 10px;
    height: 96px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
  }

  .placeholder {
    color: #6b7280;
    font-size: 0.9rem;
  }
</style>
