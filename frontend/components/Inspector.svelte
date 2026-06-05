<script>
  import { createEventDispatcher } from 'svelte';
  import PresetManager from './PresetManager.svelte';
  import UnifiedFxPanel from './UnifiedFxPanel.svelte';

  export let selectedSample = null;
  export let hoveredSample = null;
  export let editableParams = null;
  export let interpolationPreviewEntries = [];
  export let interpolationActive = false;
  export let interpolationPointA = null;
  export let interpolationPointB = null;
  export let keyboardInterpolationMode = false;
  export let interpolationPreviewPercent = 0;
  export let isEditingParams = false;
  export let fxParams = null;
  export let fxDisplayState = 'none';
  export let fxSampleInfo = null;
  export let fxReadonly = false;
  export let fxBypass = false;
  export let presetRefreshToken = 0;

  const dispatch = createEventDispatcher();

  // Determine which state to show in the unified parameter panel
  $: displayState = interpolationActive && interpolationPreviewEntries.length > 0
    ? 'interp.'
    : selectedSample
    ? 'selected'
    : hoveredSample
    ? 'hover'
    : 'none';

  // Compute displayParams based on state
  $: displayParams = (() => {
    if (displayState === 'interpolation' && interpolationPreviewEntries.length > 0) {
      return convertInterpolationPreviewToParams(interpolationPreviewEntries);
    }
    if (displayState === 'selected' && editableParams) {
      return editableParams;
    }
    // For hover or when no editableParams, use the sample's original params
    if (selectedSample?.params?.plugins) {
      return selectedSample.params.plugins;
    }
    if (selectedSample?.params) {
      return selectedSample.params;
    }
    if (hoveredSample?.params?.plugins) {
      return hoveredSample.params.plugins;
    }
    if (hoveredSample?.params) {
      return hoveredSample.params;
    }
    return null;
  })();

  function convertInterpolationPreviewToParams(entries) {
    // interpolationPreviewEntries is a flat list like [{ path: "Gain › gain_db", value: 3.5 }]
    // We need to reconstruct nested structure
    const result = {};
    entries.forEach(entry => {
      const pathParts = entry.path.split(' › ');
      let current = result;
      for (let i = 0; i < pathParts.length - 1; i++) {
        const part = pathParts[i].replace(/\[|\]/g, ''); // Remove array brackets
        if (!current[part]) {
          current[part] = {};
        }
        current = current[part];
      }
      const lastKey = pathParts[pathParts.length - 1];
      current[lastKey] = entry.value;
    });
    return result;
  }

  const handlePresetLoad = (event) => {
    const { preset } = event.detail;
    dispatch('presetLoad', { params: preset.params });
  };

  const handleFxParamChange = (event) => {
    dispatch('paramChange', event.detail);
  };

  const handleFxBypassChange = (event) => {
    dispatch('fxBypassChange', event.detail);
  };

  let nameInput = '';
  let interpolationNameInput = '';
  let lastSelectedIndex = null;
  let wasEditingParams = false;

  $: if (selectedSample && selectedSample.index !== lastSelectedIndex) {
    nameInput = selectedSample.customName || selectedSample.name || '';
    lastSelectedIndex = selectedSample.index;
  }

  $: if (isEditingParams && !wasEditingParams) {
    nameInput = '';
    wasEditingParams = true;
  } else if (!isEditingParams && wasEditingParams) {
    wasEditingParams = false;
  }

  const handleNameCommit = () => {
    if (!selectedSample) return;
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    dispatch('nameChange', {
      index: selectedSample.index,
      name: trimmed,
      isEditingParams
    });
  };

  const handleInterpolationSave = () => {
    const trimmed = interpolationNameInput.trim();
    if (!trimmed) return;
    dispatch('interpolationSave', {
      name: trimmed,
      pointA: interpolationPointA,
      pointB: interpolationPointB,
      percent: interpolationPreviewPercent
    });
    interpolationNameInput = '';
  };

  const handleNameKeydown = (event) => {
    if (event.key === 'Enter') {
      handleNameCommit();
    }
  };

  const handleInterpolationNameKeydown = (event) => {
    if (event.key === 'Enter') {
      handleInterpolationSave();
    }
  };

  // Determine if we can save a preset (have params to save)
  $: canSavePreset = Boolean(displayParams && Object.keys(displayParams).length > 0);
</script>

<section class="inspector">
  <header class="inspector-header">
    <h2>FX Inspector</h2>
    <p>Monitor, interpolate, and edit from one panel.</p>
  </header>

  <div class="inspector-sections">
    <section class="info-card">
      <div class="section-title">
        <h3>Selection Overview</h3>
        {#if hoveredSample}
          <span class="hover-chip">Hover: #{hoveredSample.index}</span>
        {/if}
      </div>
      {#if selectedSample}
        <div class="selection-meta">
          <div>
            <p class="label">Active</p>
            <p class="value">{selectedSample.customName || selectedSample.name}</p>
          </div>
          <div>
            <p class="label">Type</p>
            <p class="value badge">{selectedSample.type}</p>
          </div>
          <div>
            <p class="label">Index</p>
            <p class="value mono">#{selectedSample.index}</p>
          </div>
        </div>
        {#if isEditingParams}
          <div class="derived-info">
            <p class="label">Editing From</p>
            <p class="value mono">#{selectedSample.index}</p>
          </div>
        {/if}
        <div class="name-editor">
          <p class="label">Rename</p>
          <div class="name-input-row">
            <input
              type="text"
              class="name-input"
              bind:value={nameInput}
              on:keydown={handleNameKeydown}
              placeholder="Enter a custom name"
            />
            <button class="name-save" on:click={handleNameCommit}>Save</button>
          </div>
        </div>
        <p class="inline-hint">Interpolation: hover + <code>1</code>/<code>2</code> to set A/B. FX bypass: <code>B</code>.</p>
        {#if (interpolationPointA || interpolationPointB) && !keyboardInterpolationMode && !interpolationActive}
          <p class="inline-hint">Press <code>M</code> to start interpolating (then <code>←</code>/<code>→</code> to blend).</p>
        {/if}
      {:else}
        <p class="placeholder">Click a point on the map to load its FX settings.</p>
      {/if}
    </section>

    {#if interpolationActive && interpolationPointA && interpolationPointB}
      <section class="info-card interpolation-save-card">
        <div class="section-title">
          <h3>Save Interpolation...</h3>
        </div>
        <div class="interpolation-info">
          <p class="interpolation-desc">
            Interpolating between <strong>#{interpolationPointA.index}</strong> and <strong>#{interpolationPointB.index}</strong> at {interpolationPreviewPercent}%
          </p>
        </div>
        <div class="name-editor">
          <p class="label">Name Your Interpolation</p>
          <div class="name-input-row">
            <input
              type="text"
              class="name-input"
              bind:value={interpolationNameInput}
              on:keydown={handleInterpolationNameKeydown}
              placeholder="e.g., Warm Delay Mix"
            />
            <button class="name-save" on:click={handleInterpolationSave}>Save</button>
          </div>
        </div>
        <p class="inline-hint">Mode switch: <code>M</code> enter, <code>←</code>/<code>→</code> blend, <code>ESC</code> exit.</p>
      </section>
    {/if}

    <section class="fx-panel-card">
      <UnifiedFxPanel
        params={fxParams}
        displayState={fxDisplayState}
        sampleInfo={fxSampleInfo}
        readonly={fxReadonly}
        {fxBypass}
        on:paramChange={handleFxParamChange}
        on:fxBypassChange={handleFxBypassChange}
      />
    </section>

    <PresetManager
      currentParams={displayParams}
      canSave={canSavePreset}
      refreshToken={presetRefreshToken}
      on:presetLoad={handlePresetLoad}
      on:presetSaved={handlePresetSaved}
    />
  </div>
</section>

<style>
  .inspector {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1.25rem;
  }

  .inspector-header h2 {
    margin: 0;
    font-size: 1.1rem;
  }

  .inspector-header p {
    margin: 0.15rem 0 0;
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .inline-hint {
    margin: 0.5rem 0 0;
    color: #9aa0a6;
    font-size: 0.8rem;
  }

  .inline-hint code {
    font-family: "Courier New", monospace;
    color: #e5e5e5;
  }

  .inspector-sections {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .info-card {
    background: #0f0f0f;
    border: 1px solid #1f2933;
    border-radius: 10px;
    padding: 1rem;
  }

  .fx-panel-card {
    background: #0f0f0f;
    border: 1px solid #1f2933;
    border-radius: 10px;
    padding: 0.75rem;
  }

  .section-title {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }

  .section-title h3 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #cbd5f5;
  }

  .hover-chip {
    font-size: 0.7rem;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    border: 1px solid #374151;
    color: #9ca3af;
  }

  .selection-meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .derived-info {
    margin-top: 0.6rem;
    padding: 0.5rem 0.75rem;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 8px;
  }

  .name-editor {
    margin-top: 0.75rem;
  }

  .name-input-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.5rem;
    margin-top: 0.35rem;
  }

  .name-input {
    background: #0a0a0a;
    border: 1px solid #1f2933;
    border-radius: 8px;
    color: #e0e0e0;
    padding: 0.4rem 0.6rem;
    font-size: 0.85rem;
  }

  .name-save {
    background: #10b981;
    color: #0b0b0b;
    border: none;
    border-radius: 8px;
    padding: 0.4rem 0.75rem;
    font-weight: 600;
    cursor: pointer;
  }

  .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b7280;
    margin: 0;
  }

  .value {
    margin: 0.15rem 0 0;
    font-size: 0.9rem;
  }

  .badge {
    color: #93c5fd;
  }

  .mono {
    font-family: 'IBM Plex Mono', SFMono-Regular, Menlo, monospace;
  }

  .placeholder {
    color: #6b7280;
    font-size: 0.85rem;
    margin: 0;
  }

  .interpolation-save-card {
    background: rgba(139, 92, 246, 0.1);
    border-color: rgba(139, 92, 246, 0.3);
  }

  .interpolation-info {
    margin-bottom: 0.75rem;
  }

  .interpolation-desc {
    font-size: 0.85rem;
    color: #cbd5f5;
    margin: 0;
    line-height: 1.5;
  }

  .interpolation-desc strong {
    color: var(--accent-3);
    font-weight: 600;
  }
</style>
