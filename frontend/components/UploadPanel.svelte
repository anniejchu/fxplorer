<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { DEFAULT_EMBED_MODES } from '../lib/constants.js';
  import { AVAILABLE_FX, MAX_FX } from '../lib/fxCatalog.js';

  const dispatch = createEventDispatcher();

  const defaultEmbedModes = DEFAULT_EMBED_MODES;
  const defaultReductionMethod = 'pca';

  // Available FX types (all supported by both backend and Tone.js)

  let configId = 'random_chain';
  let explorationStrategy = 'single'; // 'single', 'chain', or 'groups'
  let explorationMode = 'separate'; // 'separate' or 'chain'
  let selectedFx = []; // Up to 3 FX selected
  let showChainCustomization = false; // Accordion state
  let file = null;
  let loading = false;
  let error = '';
  let status = '';
  let progress = 0;
  let progressTimer = null;
  let stageTimeouts = [];

  // Sample counts - maps FX combo key to sample count
  // For separate mode: {'eq:6': 20, 'reverb': 30, ...}
  // For chain mode: {'eq:6,reverb': 15, 'eq:6': 10, 'reverb': 10, '': 1}
  let sampleCounts = {};

  onMount(async () => {
    try {
      const res = await api.getConfigs();
      const configs = (res?.configs || []).filter((c) => c.exists);
      if (configs.length && !configs.find((c) => c.id === configId)) {
        configId = configs[0].id;
      }
    } catch (e) {
      error = 'Could not load FX presets.';
      console.error(e);
    }
  });

  // Generate all FX combinations for chain mode
  function generateCombinations(fxList) {
    if (fxList.length === 0) return [];

    const combos = [];
    const n = fxList.length;

    // Generate all subsets (2^n combinations)
    for (let i = 1; i < (1 << n); i++) { // Start from 1 to exclude empty set
      const combo = [];
      for (let j = 0; j < n; j++) {
        if (i & (1 << j)) {
          combo.push(fxList[j]);
        }
      }
      combos.push(combo);
    }

    // Sort by length descending (full chain first)
    return combos.sort((a, b) => b.length - a.length);
  }

  // Reactive combinations based on selected FX and mode
  $: combinations = explorationMode === 'chain'
    ? generateCombinations(selectedFx)
    : selectedFx.map(fx => [fx]); // Separate mode: each FX is its own combo

  // Initialize sample counts when combinations change
  $: {
    if (combinations.length > 0) {
      const newCounts = {};

      // Always include dry
      newCounts[''] = 1;

      // Set default count of 10 for each combination
      combinations.forEach(combo => {
        const key = combo.join(',');
        if (!(key in sampleCounts)) {
          newCounts[key] = 10;
        } else {
          newCounts[key] = sampleCounts[key];
        }
      });

      sampleCounts = newCounts;
    } else {
      sampleCounts = { '': 1 }; // Only dry
    }
  }

  // Calculate totals (exclude dry point from display)
  $: totalSamplesInternal = Object.values(sampleCounts).reduce((sum, count) => sum + count, 0);
  $: totalSamplesDisplay = Object.entries(sampleCounts)
    .filter(([key]) => key !== '')
    .reduce((sum, [, count]) => sum + count, 0);

  function handleFileChange(event) {
    const files = event.target.files;
    file = files && files.length ? files[0] : null;
    status = '';
    error = '';
  }

  function handleModeChange(mode) {
    explorationMode = mode;
    error = '';
    // Regenerate combinations with new mode
  }

  function handleGenerate() {
    if (!file) {
      error = 'Upload a dry audio file first.';
      return;
    }

    if (selectedFx.length === 0 && explorationStrategy !== 'groups') {
      error = 'Select at least 1 FX.';
      return;
    }

    const usesPerceptualGroups = explorationStrategy === 'groups';

    loading = true;
    status = 'Running pipeline...';
    error = '';
    startProgress();

    dispatch('generate', {
      file,
      configId,
      targetSamples: usesPerceptualGroups ? null : totalSamplesInternal,
      sampleCounts: usesPerceptualGroups ? null : sampleCounts,
      explorationMode: usesPerceptualGroups ? null : explorationMode,
      selectedFx: usesPerceptualGroups ? null : selectedFx,
      combinations: usesPerceptualGroups ? null : combinations,
      embedModes: defaultEmbedModes,
      reductionMethod: defaultReductionMethod,
      onComplete: (msg) => {
        status = msg || '';
        progress = 100;
        stopProgress();
        loading = false;
      },
      onError: (msg) => {
        error = msg || 'Pipeline failed.';
        progress = 0;
        stopProgress();
        loading = false;
      }
    });
  }

  function toggleFx(id) {
    if (selectedFx.includes(id)) {
      selectedFx = selectedFx.filter(fx => fx !== id);
    } else if (selectedFx.length < MAX_FX) {
      selectedFx = [...selectedFx, id];
    } else {
      error = `Maximum ${MAX_FX} FX`;
    }
  }

  function updateSampleCount(comboKey, value) {
    const count = Math.max(1, Math.min(100, Number(value) || 1));
    sampleCounts = { ...sampleCounts, [comboKey]: count };
  }

  function startProgress() {
    stopProgress();
    progress = 4;
    let target = 18;
    status = 'Uploading + staging...';

    progressTimer = setInterval(() => {
      if (progress < target) {
        progress = Math.min(progress + 1, target);
      }
    }, 500);

    stageTimeouts = [
      setTimeout(() => {
        target = 45;
        status = 'Generating FX variations...';
      }, 3000),
      setTimeout(() => {
        target = 72;
        status = 'Embedding...';
      }, 8000),
      setTimeout(() => {
        target = 90;
        status = 'Projecting to 2D...';
      }, 13000),
    ];
  }

  function stopProgress() {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    stageTimeouts.forEach((t) => clearTimeout(t));
    stageTimeouts = [];
  }
</script>

<section class="upload-panel">
  <div class="header">
    <div>
      <p class="eyebrow">FX Explorer</p>
      <h2>Generate Samples</h2>
      <p class="subtext">Upload audio and explore FX variations in semantic space.</p>
    </div>
    <span class="pill">INPUT</span>
  </div>

  <div class="field">
    <label for="dry-input">Dry audio</label>
    <input id="dry-input" type="file" accept="audio/*" on:change={handleFileChange} disabled={loading} />
    {#if file}
      <p class="file-meta">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</p>
    {/if}
  </div>

  <!-- Exploration Strategy -->
  <div class="field">
    <p class="field-label">What do you want to explore?</p>
    <div class="strategy-toggle">
      <button
        class="strategy-btn"
        class:active={explorationStrategy === 'single'}
        on:click={() => {
          explorationStrategy = 'single';
          configId = 'random_chain';
          selectedFx = [];
          showChainCustomization = false;
        }}
        disabled={loading}
      >
        <div class="strategy-content">
          <strong>Explore 1 FX</strong>
          <span class="strategy-desc">Deep dive into one effect's parameter space</span>
        </div>
      </button>
      <button
        class="strategy-btn"
        class:active={explorationStrategy === 'chain'}
        on:click={() => {
          explorationStrategy = 'chain';
          configId = 'random_chain';
          selectedFx = [];
          showChainCustomization = false;
        }}
        disabled={loading}
      >
        <div class="strategy-content">
          <strong>Explore FX Chain</strong>
          <span class="strategy-desc">Compare multiple effects or combinations</span>
        </div>
      </button>
      <button
        class="strategy-btn"
        class:active={explorationStrategy === 'groups'}
        on:click={() => {
          explorationStrategy = 'groups';
          configId = 'perceptual_groups';
          selectedFx = [];
          showChainCustomization = false;
        }}
        disabled={loading}
      >
        <div class="strategy-content">
          <strong>Macro Groups</strong>
          <span class="strategy-desc">Macro categories for clean, bright/dark, space, motion</span>
        </div>
      </button>
    </div>
  </div>

  <!-- FX Selection -->
  {#if explorationStrategy === 'single'}
    <div class="field">
      <p class="field-label">Pick One Effect</p>
      <div class="chip-grid">
        {#each AVAILABLE_FX as fx}
          <button
            class:active={selectedFx.includes(fx.id)}
            on:click={() => {
              selectedFx = [fx.id];
            }}
            disabled={loading}
            title={fx.id}
          >
            {fx.label}
          </button>
        {/each}
      </div>
    </div>
  {:else if explorationStrategy === 'chain'}
    <div class="field">
      <p class="field-label">Pick Effects to Chain (max {MAX_FX})</p>
      <div class="chip-grid">
        {#each AVAILABLE_FX as fx}
          <button
            class:active={selectedFx.includes(fx.id)}
            on:click={() => toggleFx(fx.id)}
            disabled={loading}
            title={fx.id}
          >
            {fx.label}
          </button>
        {/each}
      </div>
    </div>

    <!-- Chain Customization Accordion -->
    {#if selectedFx.length > 0}
      <div class="field">
        <button
          class="accordion-toggle"
          on:click={() => showChainCustomization = !showChainCustomization}
        >
          <span class="accordion-icon">{showChainCustomization ? '▼' : '▶'}</span>
          Advanced: Chain Options
        </button>

        {#if showChainCustomization}
          <div class="accordion-content">
            <p class="field-label">Chain Mode</p>
            <div class="mode-toggle">
              <button
                class="mode-btn"
                class:active={explorationMode === 'separate'}
                on:click={() => handleModeChange('separate')}
                disabled={loading}
              >
                Separate FX
              </button>
              <button
                class="mode-btn"
                class:active={explorationMode === 'chain'}
                on:click={() => handleModeChange('chain')}
                disabled={loading}
              >
                All Combos
              </button>
            </div>
            <p class="meta">
              {#if explorationMode === 'separate'}
                Each FX applied individually to your audio.
              {:else}
                Generate all ON/OFF combinations of the selected FX chain.
              {/if}
            </p>
          </div>
        {/if}
      </div>
    {/if}
  {:else if explorationStrategy === 'groups'}
    <div class="field">
      <p class="field-label">Preset Categories</p>
      <div class="chip-grid">
        <button class="disabled" disabled>Clean / Enhance</button>
        <button class="disabled" disabled>Bright / Presence</button>
        <button class="disabled" disabled>Dark / Muffled</button>
        <button class="disabled" disabled>Space / Depth</button>
        <button class="disabled" disabled>Motion</button>
        <button class="disabled" disabled>Grit / Lo-Fi</button>
        <button class="disabled" disabled>Transient Control</button>
      </div>
      <p class="meta">This preset auto-generates samples within each category.</p>
    </div>
  {/if}

  {#if selectedFx.length > 0}
    <!-- STEP 3: Configure Sample Counts -->
    <div class="field">
      <p class="field-label">Sample Counts</p>
      <p class="meta">Adjust samples for each combination below.</p>

      <div class="combos-list">
        {#each combinations as combo}
          {@const key = combo.join(',')}
          {@const fxObjects = combo.map(id => AVAILABLE_FX.find(f => f.id === id))}
          <div class="combo-row">
            <div class="combo-flow-container">
              <div class="combo-mini-flow">
                <div class="mini-node input">In</div>
                {#each fxObjects as fx}
                  <span class="mini-arrow">→</span>
                  <div class="mini-node fx">{fx?.label}</div>
                {/each}
                <span class="mini-arrow">→</span>
                <div class="mini-node output">Out</div>
              </div>
              <div class="combo-meta">
                <span class="combo-label-text">
                  {fxObjects.map(fx => fx?.label).join(' + ')}
                </span>
              </div>
            </div>
            <input
              type="number"
              min="1"
              max="100"
              value={sampleCounts[key]}
              on:input={(e) => updateSampleCount(key, e.target.value)}
              disabled={loading}
              class="combo-count-input"
            />
          </div>
        {/each}
      </div>

      <div class="total-row">
        <span class="total-label">Total Samples:</span>
        <span class="total-value">{totalSamplesDisplay}</span>
      </div>
    </div>
  {/if}

  <button
    class="primary"
    on:click={handleGenerate}
    disabled={loading || !file || (selectedFx.length === 0 && explorationStrategy !== 'groups')}
  >
    {#if loading}Working…{:else}Generate & Populate{/if}
  </button>

  {#if loading}
    <div class="progress">
      <div class="bar" style={`width:${progress}%`}></div>
    </div>
  {/if}

  {#if status}<p class="status">{status}</p>{/if}
  {#if error}<p class="error">{error}</p>{/if}
</section>

<style>
  .upload-panel {
    padding: 1.1rem;
    border-bottom: 1px solid #333;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(24, 24, 27, 0.9));
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .eyebrow {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    color: #9ca3af;
    text-transform: uppercase;
  }

  h2 {
    margin: 0.1rem 0;
    font-size: 1rem;
  }

  .subtext {
    margin: 0;
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .pill {
    padding: 0.2rem 0.6rem;
    border: 1px solid #333;
    border-radius: 999px;
    font-size: 0.75rem;
    color: #a5b4fc;
    background: rgba(99, 102, 241, 0.1);
  }

  .field {
    margin-top: 0.85rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .field label {
    font-size: 0.9rem;
    color: #d1d5db;
  }

  .field-label {
    margin: 0;
    font-size: 0.9rem;
    color: #d1d5db;
  }

  input[type="file"],
  input[type="number"] {
    background: #0f0f12;
    color: #e5e7eb;
    border: 1px solid #2d2d35;
    border-radius: 6px;
    padding: 0.55rem 0.65rem;
  }

  .file-meta,
  .meta {
    margin: 0;
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .strategy-toggle {
    display: flex;
    gap: 0.5rem;
  }

  .strategy-btn {
    flex: 1;
    padding: 0.85rem;
    background: #0f0f12;
    border: 1px solid #2d2d35;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }

  .strategy-btn:hover:not(:disabled) {
    border-color: var(--accent);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
  }

  .strategy-btn.active {
    border-color: var(--accent);
    background: rgba(99, 102, 241, 0.1);
    box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.2);
  }

  .strategy-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .strategy-content {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .strategy-content strong {
    color: #e5e7eb;
    font-size: 0.9rem;
    font-weight: 600;
  }

  .strategy-desc {
    color: #9ca3af;
    font-size: 0.8rem;
    line-height: 1.3;
  }

  .accordion-toggle {
    width: 100%;
    padding: 0.65rem 0.75rem;
    background: #0a0a0c;
    border: 1px solid #2d2d35;
    border-radius: 6px;
    color: #a5b4fc;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .accordion-toggle:hover {
    border-color: var(--accent);
    background: rgba(99, 102, 241, 0.05);
  }

  .accordion-icon {
    font-size: 0.7rem;
    color: var(--accent);
    transition: transform 0.2s;
  }

  .accordion-content {
    margin-top: 0.75rem;
    padding: 0.85rem;
    background: #0a0a0c;
    border: 1px solid #2d2d35;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .chip-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.4rem;
  }

  .chip-grid button {
    padding: 0.55rem;
    background: #111;
    border: 1px solid #2f2f36;
    color: #cdd0d8;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .chip-grid button:hover:not(:disabled) {
    border-color: var(--accent);
    transform: translateY(-1px);
  }

  .chip-grid button.active {
    border-color: var(--accent);
    background: rgba(99, 102, 241, 0.15);
    color: #e5e7eb;
  }

  .chip-grid button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .chip-grid button.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .mode-toggle {
    display: flex;
    gap: 0.5rem;
  }

  .mode-btn {
    flex: 1;
    padding: 0.55rem;
    background: #0f0f12;
    color: #9ca3af;
    border: 1px solid #2d2d35;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .mode-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: #e5e7eb;
  }

  .mode-btn.active {
    border-color: var(--accent);
    background: rgba(99, 102, 241, 0.15);
    color: #e5e7eb;
  }

  .mode-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .primary {
    width: 100%;
    margin-top: 1rem;
    padding: 0.75rem;
    border: none;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--accent-3));
    color: white;
    font-weight: 600;
    cursor: pointer;
  }

  .primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .status {
    margin: 0.75rem 0 0 0;
    color: #a7f3d0;
    font-size: 0.9rem;
  }

  .error {
    margin: 0.75rem 0 0 0;
    color: #fca5a5;
    font-size: 0.9rem;
  }

  .progress {
    margin-top: 0.75rem;
    height: 8px;
    background: #151515;
    border: 1px solid #2d2d35;
    border-radius: 999px;
    overflow: hidden;
  }

  .progress .bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-3));
    transition: width 0.2s ease;
  }

  .combos-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .combo-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.5rem 0.65rem;
    background: #0a0a0c;
    border: 1px solid #2d2d35;
    border-radius: 6px;
  }

  .combo-flow-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-width: 0;
  }

  .combo-mini-flow {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .mini-node {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .mini-node.input,
  .mini-node.output {
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid var(--accent);
    color: #a5b4fc;
  }

  .mini-node.fx {
    background: linear-gradient(135deg, #2a2a2a, #1a1a1a);
    border: 1px solid #444;
    color: #e5e7eb;
    padding: 0.25rem 0.5rem;
  }

  .mini-arrow {
    color: var(--accent);
    font-size: 0.85rem;
    user-select: none;
  }

  .combo-meta {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .combo-label-text {
    font-size: 0.8rem;
    font-weight: 500;
    color: #9ca3af;
  }

  .combo-count-input {
    width: 64px;
    padding: 0.35rem 0.5rem;
    background: #0f0f12;
    border: 1px solid #2d2d35;
    border-radius: 6px;
    color: #e5e7eb;
    font-size: 0.8rem;
    text-align: center;
  }

  .combo-count-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .total-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #2d2d35;
  }

  .total-label {
    font-size: 0.9rem;
    font-weight: 600;
    color: #a5b4fc;
  }

  .total-value {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent);
  }
</style>
