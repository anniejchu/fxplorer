<script>
  import { createEventDispatcher } from 'svelte';

  export let visible = false;
  export let pointA = null;  // {index, name}
  export let pointB = null;
  export let percent = 0;     // 0-100
  export let sidebarWidth = 0;

  const dispatch = createEventDispatcher();
  let dragActive = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  const DRAG_KEY_STEP = 10;
  const SLIDER_KEY_STEP = 1;

  const normalizePluginId = (pluginId = '') => String(pluginId).replace(/_(\d+)$/, '');
  const getFxModules = (point) => {
    const params = point?.params;
    const pluginParams = params?.plugins ?? params;
    const keys = pluginParams ? Object.keys(pluginParams) : [];
    if (keys.length === 0) return ['dry'];
    return keys
      .map((key) => normalizePluginId(key))
      .map((key) => key.replace(/_/g, ' '));
  };
  const formatIndexLabel = (point, fallback) => {
    if (!point) return fallback;
    return typeof point.index === 'number'
      ? `#${point.index}`
      : (point.type === 'preset' ? 'Preset' : (point.name || fallback));
  };

  $: leftLabel = formatIndexLabel(pointA, 'A');
  $: rightLabel = formatIndexLabel(pointB, 'B');
  $: chainModules = pointA ? getFxModules(pointA) : getFxModules(pointB);

  let isDragging = false;
  let progressContainer;

  function handleMouseDown(event) {
    isDragging = true;
    updateSliderFromMouse(event);
  }

  function handleMouseMove(event) {
    if (!isDragging) return;
    updateSliderFromMouse(event);
  }

  function handleMouseUp() {
    isDragging = false;
  }

  function updateSliderFromMouse(event) {
    if (!progressContainer) return;
    const rect = progressContainer.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const newPercent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    dispatch('change', { percent: newPercent });
  }

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

  function handleDragKeyDown(event) {
    if (event.key === 'Home') {
      dragOffsetX = 0;
      dragOffsetY = 0;
    } else if (event.key === 'ArrowLeft') {
      dragOffsetX -= DRAG_KEY_STEP;
    } else if (event.key === 'ArrowRight') {
      dragOffsetX += DRAG_KEY_STEP;
    } else if (event.key === 'ArrowUp') {
      dragOffsetY -= DRAG_KEY_STEP;
    } else if (event.key === 'ArrowDown') {
      dragOffsetY += DRAG_KEY_STEP;
    } else {
      return;
    }
    event.preventDefault();
  }

  function handleSliderKeyDown(event) {
    const step = event.shiftKey ? SLIDER_KEY_STEP * 10 : SLIDER_KEY_STEP;
    let nextPercent = percent;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') nextPercent -= step;
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') nextPercent += step;
    else if (event.key === 'Home') nextPercent = 0;
    else if (event.key === 'End') nextPercent = 100;
    else return;

    event.preventDefault();
    dispatch('change', { percent: Math.max(0, Math.min(100, nextPercent)) });
  }
</script>

<svelte:window
  on:mousemove={(event) => {
    handleMouseMove(event);
    handleDragMove(event);
  }}
  on:mouseup={(event) => {
    handleMouseUp(event);
    stopDrag();
  }}
/>

{#if visible}
  <div
    class="interpolation-indicator"
    style={`left: calc(50% + ${sidebarWidth / 2}px); transform: translate(-50%, 0) translate(${dragOffsetX}px, ${dragOffsetY}px);`}
  >
    <button
      type="button"
      class="indicator-header"
      on:mousedown={startDrag}
      on:keydown={handleDragKeyDown}
      aria-label="Move interpolation panel. Use arrow keys to reposition it; press Home to reset."
    >
      <span class="mode-label">INTERPOLATE MODE</span>
      <span class="chain-row">
        <span class="chain-flow">
          {#each chainModules as mod, i}
            <span class="flow-node fx-node">{mod}</span>
            {#if i < chainModules.length - 1}
              <span class="flow-arrow">→</span>
            {/if}
          {/each}
        </span>
      </span>
    </button>
    <div class="indicator-bar">
      <span class="index-label left">{leftLabel}</span>
      <div
        class="progress-container"
        bind:this={progressContainer}
        on:mousedown={handleMouseDown}
        on:keydown={handleSliderKeyDown}
        role="slider"
        tabindex="0"
        aria-label="Interpolation blend"
        aria-valuenow={percent}
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuetext={`${percent}% between ${leftLabel} and ${rightLabel}`}
      >
        <div class="progress-track"></div>
        <div class="progress-fill" style="width: {percent}%"></div>
        <div class="progress-handle" style="left: {percent}%"></div>
      </div>
      <span class="index-label right">{rightLabel}</span>
    </div>

    <div class="indicator-meta">
      <span class="percent-label">{percent}%</span>
      <span class="hint">Drag slider or use ← → arrows • ESC to exit</span>
    </div>
  </div>
{/if}

<style>
  .interpolation-indicator {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 500;

    background: rgba(26, 26, 26, 0.95);
    border: 1px solid var(--border-strong);
    border-radius: 12px;
    padding: 1rem 1.5rem;
    box-shadow: 0 4px 20px rgba(192, 132, 252, 0.3);
    backdrop-filter: blur(10px);

    min-width: 400px;
    max-width: 600px;
  }

  .indicator-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.5rem;
  }

  .indicator-header {
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    color: inherit;
    cursor: move;
    font: inherit;
    text-align: left;
    gap: 1rem;
    margin-bottom: 0.75rem;
    cursor: move;
    user-select: none;
  }

  .chain-row {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    font-size: 0.78rem;
  }

  .chain-flow {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    flex-wrap: wrap;
  }

  .flow-node {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.6rem;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    position: relative;
  }

  .fx-node {
    background: linear-gradient(135deg, #2a2a2a, #1a1a1a);
    border: 2px solid #444;
    color: #e5e7eb;
  }

  .flow-arrow {
    color: var(--accent);
    font-size: 1rem;
    user-select: none;
  }

  .index-label {
    font-weight: 700;
    color: #e5e7eb;
    font-size: 0.85rem;
    min-width: 48px;
    text-align: center;
  }

  .index-label.left {
    color: var(--error);
  }

  .index-label.right {
    color: var(--success);
  }

  .mode-label {
    font-size: 0.7rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--accent-3);
  }

  .progress-container {
    flex: 1;
    position: relative;
    height: 24px;
    cursor: pointer;
    padding: 8px 0;
  }

  .progress-container:hover .progress-handle {
    transform: translate(-50%, -50%) scale(1.2);
  }

  .progress-container:active .progress-handle {
    transform: translate(-50%, -50%) scale(1.3);
  }

  .progress-track {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 100%;
    height: 8px;
    background: linear-gradient(to right, var(--error), var(--accent), var(--success));
    border-radius: 4px;
    opacity: 0.3;
  }

  .progress-fill {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    height: 8px;
    background: linear-gradient(to right, var(--error), var(--accent));
    border-radius: 4px;
    transition: width 0.1s ease-out;
  }

  .progress-handle {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 16px;
    height: 16px;
    background: var(--accent-3);
    border: 2px solid white;
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    transition: left 0.1s ease-out;
  }

  .indicator-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }

  .percent-label {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--accent-3);
  }

  .hint {
    font-size: 0.75rem;
    color: #9ca3af;
  }
</style>
