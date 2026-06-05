export const cloneParams = (params = {}) => {
  try {
    return structuredClone(params);
  } catch (err) {
    return JSON.parse(JSON.stringify(params || {}));
  }
};

export const setValueAtPath = (target, path, value) => {
  if (!path || path.length === 0) {
    return value;
  }
  const [head, ...rest] = path;
  const clone = Array.isArray(target)
    ? target.slice()
    : { ...(target ?? {}) };
  const current = clone[head];
  if (rest.length === 0) {
    clone[head] = value;
    return clone;
  }
  clone[head] = setValueAtPath(
    current !== undefined ? current : (typeof rest[0] === 'number' ? [] : {}),
    rest,
    value
  );
  return clone;
};

const collectPreviewEntries = (node, trail, acc, maxEntries) => {
  if (acc.length >= maxEntries) return;
  if (node === null || node === undefined) return;

  if (typeof node === 'number') {
    acc.push({ path: [...trail], value: node });
    return;
  }

  if (Array.isArray(node)) {
    node.forEach((value, idx) => {
      if (acc.length >= maxEntries) return;
      collectPreviewEntries(value, [...trail, `[${idx}]`], acc, maxEntries);
    });
    return;
  }

  if (typeof node === 'object') {
    Object.entries(node).forEach(([key, value]) => {
      if (acc.length >= maxEntries) return;
      collectPreviewEntries(value, [...trail, key], acc, maxEntries);
    });
    return;
  }

  acc.push({ path: [...trail], value: node });
};

export const buildPreviewEntries = (params, maxEntries = 12) => {
  if (!params) return [];
  const acc = [];
  Object.entries(params).forEach(([plugin, pluginParams]) => {
    if (acc.length >= maxEntries) return;
    collectPreviewEntries(pluginParams, [plugin], acc, maxEntries);
  });
  return acc.slice(0, maxEntries).map((entry) => ({
    path: entry.path.join(' › '),
    value: entry.value,
  }));
};

export const computeInterpolationGhostCoords = (coordsList, indexA, indexB, sliderValue) => {
  if (!Array.isArray(coordsList) || typeof indexA !== 'number' || typeof indexB !== 'number') {
    return null;
  }
  const pointA = coordsList[indexA];
  const pointB = coordsList[indexB];
  if (!pointA || !pointB) return null;
  const t = Math.min(Math.max(sliderValue ?? 0, 0), 1);
  return {
    x: pointA.x + (pointB.x - pointA.x) * t,
    y: pointA.y + (pointB.y - pointA.y) * t,
  };
};

export const getSampleParams = (sample) => sample?.params?.plugins || sample?.params || null;

export const buildEditGhostParams = (selectedSample, editableParams) => {
  if (!selectedSample || !editableParams) return null;
  const baseParams = selectedSample?.params || {};
  const chain = baseParams.chain || [];
  if (!Array.isArray(chain) || chain.length === 0) {
    return null;
  }
  return {
    ...baseParams,
    chain,
    plugins: cloneParams(editableParams)
  };
};

export const calculateGhostPoint = async (api, mode, params) => {
  if (!params || !mode) return null;
  try {
    const response = await api.calculateGhostPoint(mode, params);
    if (!response || typeof response.x !== 'number' || typeof response.y !== 'number') {
      return null;
    }
    return { x: response.x, y: response.y };
  } catch (err) {
    console.error('Ghost point calculation failed:', err);
    return null;
  }
};
