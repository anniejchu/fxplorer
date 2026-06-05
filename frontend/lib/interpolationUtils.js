// Normalize plugin ID by removing numeric suffix (e.g., "chorus_0" -> "chorus", "eq_6_0" -> "eq_6")
function normalizePluginId(pluginId) {
  // Match pattern: word_number at the end (e.g., "chorus_0", "phaser_1")
  // Keep patterns like "eq_6" but remove final "_0" suffix
  return pluginId.replace(/_(\d+)$/, '');
}

export function isDryParams(params) {
  if (!params) return true;
  const plugins = params.plugins;
  if (plugins && Object.keys(plugins).length === 0) return true;
  const keys = Object.keys(params);
  if (keys.length === 0) return true;
  if (keys.length === 1 && keys[0] === 'chain') {
    return Array.isArray(params.chain) && params.chain.length === 0;
  }
  return false;
}

export function haveSameFxChain(paramsA, paramsB) {
  const keysA = Object.keys(paramsA || {}).map(normalizePluginId).sort();
  const keysB = Object.keys(paramsB || {}).map(normalizePluginId).sort();
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key, idx) => key === keysB[idx]);
}

export function canPairInterpolation(paramsA, paramsB) {
  if (isDryParams(paramsA) || isDryParams(paramsB)) return true;
  return haveSameFxChain(paramsA, paramsB);
}
