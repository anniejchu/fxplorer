/**
 * Preset Store - Manages user-saved FX presets with localStorage persistence
 */

const STORAGE_KEY = 'fxplorer_presets';

export class PresetStore {
  constructor() {
    this.presets = this.loadFromStorage();
  }

  loadFromStorage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (err) {
      console.error('Failed to load presets from storage:', err);
      return [];
    }
  }

  saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.presets));
    } catch (err) {
      console.error('Failed to save presets to storage:', err);
    }
  }

  /**
   * Save a new preset or update existing
   * @param {string} name - Preset name
   * @param {object} params - FX parameters
   * @param {object} metadata - Optional metadata (sample index, mode, etc.)
   */
  savePreset(name, params, metadata = {}) {
    const preset = {
      id: Date.now().toString(),
      name,
      params,
      metadata,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    // Check if preset with this name already exists
    const existingIndex = this.presets.findIndex(p => p.name === name);
    if (existingIndex >= 0) {
      // Update existing
      preset.id = this.presets[existingIndex].id;
      preset.createdAt = this.presets[existingIndex].createdAt;
      this.presets[existingIndex] = preset;
    } else {
      // Add new
      this.presets.push(preset);
    }

    this.saveToStorage();
    return preset;
  }

  /**
   * Get all presets
   */
  getAllPresets() {
    return [...this.presets];
  }

  /**
   * Get preset by ID
   */
  getPreset(id) {
    return this.presets.find(p => p.id === id);
  }

  /**
   * Delete preset by ID
   */
  deletePreset(id) {
    this.presets = this.presets.filter(p => p.id !== id);
    this.saveToStorage();
  }

  /**
   * Rename preset
   */
  renamePreset(id, newName) {
    const preset = this.presets.find(p => p.id === id);
    if (preset) {
      preset.name = newName;
      preset.updatedAt = new Date().toISOString();
      this.saveToStorage();
    }
  }

  /**
   * Export presets as JSON
   */
  exportPresets() {
    return JSON.stringify(this.presets, null, 2);
  }

  /**
   * Import presets from JSON
   */
  importPresets(jsonString) {
    try {
      const imported = JSON.parse(jsonString);
      if (Array.isArray(imported)) {
        this.presets = imported;
        this.saveToStorage();
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to import presets:', err);
      return false;
    }
  }
}

// Singleton instance
export const presetStore = new PresetStore();
