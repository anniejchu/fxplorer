<script>
  import { createEventDispatcher } from 'svelte';
  import { presetStore } from '../lib/presetStore.js';

  export let currentParams = null;
  export let canSave = false;
  export let refreshToken = 0;

  const dispatch = createEventDispatcher();

  let presets = presetStore.getAllPresets();
  let showSaveDialog = false;
  let presetName = '';
  let saveError = '';
  let lastRefreshToken = refreshToken;

  function refreshPresets() {
    presets = presetStore.getAllPresets();
  }

  $: if (refreshToken !== lastRefreshToken) {
    lastRefreshToken = refreshToken;
    refreshPresets();
  }

  function openSaveDialog() {
    showSaveDialog = true;
    presetName = '';
    saveError = '';
  }

  function closeSaveDialog() {
    showSaveDialog = false;
    presetName = '';
    saveError = '';
  }

  function handleSave() {
    if (!presetName.trim()) {
      saveError = 'Please enter a preset name';
      return;
    }
    if (!currentParams || Object.keys(currentParams).length === 0) {
      saveError = 'No FX parameters to save';
      return;
    }

    try {
      presetStore.savePreset(presetName.trim(), currentParams);
      refreshPresets();
      closeSaveDialog();
      dispatch('presetSaved', { name: presetName });
    } catch (err) {
      saveError = err.message || 'Failed to save preset';
    }
  }

  function handleLoad(preset) {
    dispatch('presetLoad', { preset });
  }

  function handleDelete(presetId) {
    if (confirm('Delete this preset?')) {
      presetStore.deletePreset(presetId);
      refreshPresets();
    }
  }

  function handleExport() {
    const json = presetStore.exportPresets();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fx-presets-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleImport(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const success = presetStore.importPresets(e.target.result);
      if (success) {
        refreshPresets();
        alert('Presets imported successfully!');
      } else {
        alert('Failed to import presets. Check file format.');
      }
    };
    reader.readAsText(file);
  }
</script>

<section class="preset-manager">
  <div class="section-header">
    <h3>Saved Presets</h3>
    <button class="save-btn" on:click={openSaveDialog} disabled={!canSave}>
      💾 Save
    </button>
  </div>

  {#if presets.length > 0}
    <div class="preset-list">
      {#each presets as preset (preset.id)}
        <div class="preset-item">
          <div class="preset-info">
            <span class="preset-name">{preset.name}</span>
            <span class="preset-date">{new Date(preset.createdAt).toLocaleDateString()}</span>
          </div>
          <div class="preset-actions">
            <button class="load-btn" on:click={() => handleLoad(preset)} title="Load preset">
              ▶️
            </button>
            <button class="delete-btn" on:click={() => handleDelete(preset.id)} title="Delete">
              🗑️
            </button>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <p class="empty-message">No saved presets yet</p>
  {/if}

  <div class="preset-tools">
    <button class="tool-btn" on:click={handleExport} disabled={presets.length === 0}>
      Export All
    </button>
    <label class="tool-btn">
      Import
      <input type="file" accept=".json" on:change={handleImport} style="display: none;" />
    </label>
  </div>
</section>

{#if showSaveDialog}
  <div class="modal-overlay" on:click={closeSaveDialog}>
    <div class="modal-content" on:click|stopPropagation>
      <h3>Save Preset</h3>
      <input
        type="text"
        placeholder="Preset name (e.g., Warm Reverb)"
        bind:value={presetName}
        on:keydown={(e) => e.key === 'Enter' && handleSave()}
        autofocus
      />
      {#if saveError}
        <p class="error">{saveError}</p>
      {/if}
      <div class="modal-actions">
        <button class="primary" on:click={handleSave}>Save</button>
        <button class="secondary" on:click={closeSaveDialog}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .preset-manager {
    padding: 1rem;
    border-top: 1px solid #333;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .section-header h3 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #cbd5f5;
  }

  .save-btn {
    padding: 0.35rem 0.6rem;
    border-radius: 6px;
    border: 1px solid #10b981;
    background: rgba(16, 185, 129, 0.15);
    color: #6ee7b7;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .save-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .preset-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 300px;
    overflow-y: auto;
  }

  .preset-item {
    background: #0f0f0f;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 0.6rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .preset-info {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    flex: 1;
  }

  .preset-name {
    font-size: 0.85rem;
    color: #e5e7eb;
    font-weight: 500;
  }

  .preset-date {
    font-size: 0.7rem;
    color: #6b7280;
  }

  .preset-actions {
    display: flex;
    gap: 0.4rem;
  }

  .load-btn,
  .delete-btn {
    padding: 0.3rem 0.5rem;
    border: 1px solid #2f2f2f;
    background: transparent;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
  }

  .load-btn:hover {
    background: rgba(16, 185, 129, 0.1);
    border-color: #10b981;
  }

  .delete-btn:hover {
    background: rgba(239, 68, 68, 0.1);
    border-color: #ef4444;
  }

  .empty-message {
    text-align: center;
    padding: 2rem 1rem;
    color: #6b7280;
    font-size: 0.85rem;
  }

  .preset-tools {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #2a2a2a;
  }

  .tool-btn {
    flex: 1;
    padding: 0.4rem 0.6rem;
    border-radius: 6px;
    border: 1px solid #2f2f2f;
    background: #1a1a1a;
    color: #9ca3af;
    cursor: pointer;
    font-size: 0.8rem;
  }

  .tool-btn:hover {
    border-color: #444;
    background: #222;
  }

  .tool-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* Modal */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-content {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 12px;
    padding: 1.5rem;
    min-width: 320px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  .modal-content h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #e5e7eb;
  }

  .modal-content input {
    width: 100%;
    padding: 0.6rem;
    border-radius: 6px;
    border: 1px solid #2f2f2f;
    background: #0f0f0f;
    color: #e5e7eb;
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }

  .modal-content .error {
    color: #f87171;
    font-size: 0.85rem;
    margin: 0.5rem 0;
  }

  .modal-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  .modal-actions button {
    flex: 1;
    padding: 0.6rem;
    border-radius: 6px;
    border: 1px solid #2f2f2f;
    cursor: pointer;
    font-weight: 600;
  }

  .modal-actions .primary {
    background: rgba(16, 185, 129, 0.2);
    border-color: #10b981;
    color: #6ee7b7;
  }

  .modal-actions .secondary {
    background: transparent;
    color: #9ca3af;
  }
</style>
