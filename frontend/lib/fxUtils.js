// Normalize plugin ID by removing numeric suffix (e.g., "chorus_0" -> "chorus", "eq_6_0" -> "eq_6")
function normalizePluginId(pluginId) {
  // Match pattern: word_number at the end (e.g., "chorus_0", "phaser_1")
  // Keep patterns like "eq_6" but remove final "_0" suffix
  return pluginId.replace(/_(\d+)$/, '');
}

export function getChainKeyFromParams(params = {}) {
  const keys = Object.keys(params || {});
  if (keys.length === 0) return 'dry';

  // Normalize plugin IDs to ignore instance suffixes, then sort for consistent comparison
  const normalizedKeys = keys.map(normalizePluginId).sort();
  return normalizedKeys.join('|');
}
