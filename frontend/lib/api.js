/**
 * Backend API client.
 *
 * Wraps all Flask backend API endpoints for the frontend.
 * Handles fetch requests, error handling, and response parsing.
 *
 * ENDPOINTS:
 * - /health - Server health check
 * - /modes - Available embedding modes (CLAP, AFx-Rep)
 * - /coords?mode=<mode> - 2D coordinates for visualization
 * - /manifest - Sample metadata + FX parameters
 * - /audio/<idx> - Stream audio file by index
 * - /text_point - Project text query into 2D space (CLAP)
 * - /ghost_point - Project edited params to 2D (render → embed → project)
 * - /session/run_pipeline - Trigger full pipeline from upload
 *
 * CONFIGURATION:
 * API base URL can be set via VITE_API_URL environment variable
 * Default: http://localhost:5000/api
 */

// Read base from Vite env or fall back to localhost. Normalize for safety:
const _rawApiBase = (import.meta.env.VITE_API_URL || 'http://localhost:5000/api').trim();
import { DEFAULT_MODE, DEFAULT_EMBED_MODES_STR } from './constants.js';

const API_BASE = (() => {
  try {
    let b = _rawApiBase;
    // If user provided a host without scheme, assume http
    if (!b.startsWith('http://') && !b.startsWith('https://')) {
      b = 'http://' + b;
    }
    // remove trailing slash so concatenation is safe
    if (b.endsWith('/')) b = b.slice(0, -1);
    return b;
  } catch (e) {
    return 'http://localhost:5000/api';
  }
})();

class APIService {
  // Generic request wrapper with error handling
  async request(endpoint, options = {}) {
    // Ensure endpoint is joined correctly to the normalized base
    const url = endpoint.startsWith('/') ? `${API_BASE}${endpoint}` : `${API_BASE}/${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Request failed' }));
        throw new Error(error.error || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.error(`API Error (${endpoint}):`, err);
      throw err;
    }
  }

  // Server status

  async getHealth() {
    return this.request('/health');
  }

  // Embedding modes

  async getModes() {
    return this.request('/modes');  // Returns: { modes: ['clap', 'afx-rep'], default: 'afxrep' }
  }

  // Get configs
  async getConfigs() {
    return this.request('/configs');
  }

  // Get coordinates for a mode
  async getCoords(mode) {
    return this.request(`/coords?mode=${mode}`);
  }

  // Get full manifest
  async getManifest() {
    return this.request('/manifest');
  }

  // Get sample details
  async getSample(idx, mode = DEFAULT_MODE) {
    return this.request(`/sample/${idx}?mode=${mode}`);
  }

  // Get audio URL for a sample
  getAudioUrl(idx) {
    return `${API_BASE}/audio/${idx}`;
  }

  // Get dry audio URL
  getDryAudioUrl(cacheBust = false) {
    if (!cacheBust) return `${API_BASE}/dry`;
    return `${API_BASE}/dry?ts=${Date.now()}`;
  }

  // Text search (CLAP)
  async searchText(mode, query, k = 10) {
    return this.request('/search', {
      method: 'POST',
      body: JSON.stringify({
        mode,
        query,
        k,
      }),
    });
  }

  // Audio file search (AFx-Rep)
  async searchAudio(file, k = 10) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('k', k.toString());

    const url = `${API_BASE}/search?mode=afxrep`;
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Search failed' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    return await response.json();
  }

  // Run full pipeline with new audio
  async runPipeline(
    file,
    configId = 'random_chain',
    embedModes = DEFAULT_EMBED_MODES_STR,
    targetSamples = null,
    allowedFx = null,
    reductionMethod = 'pca',
    explorationMode = null,
    sampleCounts = null,
    selectedFx = null,
    combinations = null
  ) {
    const embedParam = Array.isArray(embedModes) ? embedModes.join(',') : embedModes;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('config_id', configId);
    formData.append('embed_modes', embedParam || DEFAULT_EMBED_MODES_STR);
    formData.append('reduction_method', reductionMethod || 'pca');
    if (targetSamples) {
      formData.append('target_samples', String(targetSamples));
    }
    if (allowedFx && allowedFx.length) {
      const fxParam = Array.isArray(allowedFx) ? allowedFx.join(',') : String(allowedFx);
      formData.append('allowed_fx', fxParam);
    }
    if (explorationMode) {
      formData.append('exploration_mode', explorationMode);
    }
    if (sampleCounts) {
      formData.append('sample_counts', JSON.stringify(sampleCounts));
    }
    if (selectedFx) {
      formData.append('selected_fx', JSON.stringify(selectedFx));
    }
    if (combinations) {
      formData.append('combinations', JSON.stringify(combinations));
    }

    const url = `${API_BASE}/session/run_pipeline`;
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Pipeline failed' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    return await response.json();
  }

  // Project free-form text into CLAP 2D space
  async projectTextPoint(text, mode = 'clap', k = 5) {
    return this.request('/text_point', {
      method: 'POST',
      body: JSON.stringify({
        text,
        mode,
        k,
      }),
    });
  }

  // Accurate ghost point projection from rendered audio params
  async calculateGhostPoint(mode, params) {
    return this.request('/ghost_point', {
      method: 'POST',
      body: JSON.stringify({
        mode,
        params,
      }),
    });
  }
}

export const api = new APIService();
