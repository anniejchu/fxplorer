/**
 * Perceptual FX parameter interpolation engine.
 *
 * Provides FX-aware parameter blending between 2 sets (of the same Fx chain, cross-chain not supported).

 * For each parameter, determine if it's frequency-like, time-like, or linear
 * Apply appropriate interpolation:
 *    - Frequency: exp((1-t)*log(freqA) + t*log(freqB))
 *    - Time: exp((1-t)*log(timeA) + t*log(timeB))
 *    - Linear: (1-t)*valA + t*valB
 *
 */

const LOG_EPS = 1e-6;
const FREQ_KEYS = ["freq", "frequency", "cutoff", "_hz", "hz"];
const TIME_KEYS = ["attack", "release", "decay", "predelay", "delay", "_ms", "_seconds", "ms", "sec"];
const MODULE_KINDS = {
  EQ: "eq",
  COMPRESSOR: "compressor",
  REVERB: "reverb",
  DELAY: "delay",
  CHORUS: "chorus",
  DISTORTION: "distortion",
  GAIN: "gain",
  DEFAULT: "default",
};

// cloneValue() ensures we never mutate incoming parameter trees while blending/scaling.
const cloneValue = (value) => {
  if (Array.isArray(value)) {
    return value.map((entry) => cloneValue(entry));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, cloneValue(v)])
    );
  }
  return value;
};

// isFreqKey() detects frequency-like parameter names so we can log-interpolate.
export function isFreqKey(key) {
  if (!key) return false;
  const lower = key.toLowerCase();
  return FREQ_KEYS.some((token) => lower.includes(token));
}

// isTimeKey() detects time-like parameter names so we can log-interpolate.
export function isTimeKey(key) {
  if (!key) return false;
  const lower = key.toLowerCase();
  return TIME_KEYS.some((token) => lower.includes(token));
}

// clamp01() bounds ratios between 0 and 1 for ease-of-use.
const clamp01 = (value) => Math.min(Math.max(value, 0), 1);

// scaleNumber() applies the perceptual exponent while scaling toward zero.
const scaleNumber = (value, alpha, exponent = 1) => {
  if (typeof value !== "number" || !isFinite(value)) return value;
  const scaled = Math.pow(alpha, exponent);
  return scaled * value;
};

// scaleArray() scales each numeric element in an array-based parameter.
const scaleArray = (arr, alpha, exponent = 1) =>
  arr.map((entry) => {
    if (typeof entry === "number") return scaleNumber(entry, alpha, exponent);
    if (entry && typeof entry === "object") return cloneValue(entry);
    return entry;
  });

// detectModuleKind() infers the FX type based on plugin id/params so we can apply heuristics.
const detectModuleKind = (moduleName = "", moduleParams = {}) => {
  const norm = (moduleName || "").toLowerCase();
  const keys = Object.keys(moduleParams || {}).map((key) => key.toLowerCase());
  const hasKey = (token) =>
    keys.some((key) => key.includes(token.toLowerCase()));

  if (norm.includes("eq") || Array.isArray(moduleParams?.bands)) {
    return MODULE_KINDS.EQ;
  }
  if (norm.includes("comp") || hasKey("threshold_db")) {
    return MODULE_KINDS.COMPRESSOR;
  }
  if (
    norm.includes("reverb") ||
    hasKey("room_size") ||
    hasKey("wet_level") ||
    hasKey("damping")
  ) {
    return MODULE_KINDS.REVERB;
  }
  if (norm.includes("delay") || hasKey("delay_seconds")) {
    return MODULE_KINDS.DELAY;
  }
  if (norm.includes("chorus") || hasKey("depth") || hasKey("rate_hz")) {
    return MODULE_KINDS.CHORUS;
  }
  if (norm.includes("distortion") || hasKey("drive")) {
    return MODULE_KINDS.DISTORTION;
  }
  if (norm.includes("gain") || (hasKey("gain_db") && !hasKey("bands"))) {
    return MODULE_KINDS.GAIN;
  }
  return MODULE_KINDS.DEFAULT;
};

// scaleEqParams() attenuates EQ gain bands toward the neutral point.
function scaleEqParams(moduleParams = {}, alpha) {
  const out = { ...moduleParams };
  if (Array.isArray(moduleParams.bands)) {
    out.bands = moduleParams.bands.map((band) => {
      const next = { ...band };
      if (typeof band.gain_db === "number") {
        next.gain_db = scaleNumber(band.gain_db, alpha);
      }
      return next;
    });
  }
  return out;
}

// scaleCompressorParams() applies bespoke exponents to attack/release/threshold/knee.
function scaleCompressorParams(moduleParams = {}, alpha) {
  const out = {};
  Object.entries(moduleParams).forEach(([param, value]) => {
    const key = param.toLowerCase();
    if (key === "ratio") {
      const base = typeof value === "number" ? value : 1;
      out[param] = 1 + (base - 1) * alpha;
    } else {
      out[param] = typeof value === "number" ? value : cloneValue(value);
    }
  });
  return out;
}

// scaleReverbParams() tapers wet/mix/decay to keep ambience natural during interpolations.
function scaleReverbParams(moduleParams = {}, alpha) {
  const out = {};
  Object.entries(moduleParams).forEach(([param, value]) => {
    const key = param.toLowerCase();
    if (key.includes("wet") || key === "mix") {
      out[param] = scaleNumber(value, alpha);
    } else {
      out[param] = typeof value === "number" ? value : cloneValue(value);
    }
  });
  return out;
}

// scaleDelayParams() scales delay mix/feedback while preserving timing.
function scaleDelayParams(moduleParams = {}, alpha) {
  const out = {};
  Object.entries(moduleParams).forEach(([param, value]) => {
    const key = param.toLowerCase();
    if (key.includes("mix") || key.includes("wet") || key === "feedback") {
      out[param] = scaleNumber(value, alpha);
    } else {
      out[param] = typeof value === "number" ? value : cloneValue(value);
    }
  });
  return out;
}

// scaleChorusParams() smooths modulation depth/mix combos.
function scaleChorusParams(moduleParams = {}, alpha) {
  const out = {};
  Object.entries(moduleParams).forEach(([param, value]) => {
    const key = param.toLowerCase();
    if (["depth", "mix"].includes(key)) {
      out[param] = scaleNumber(value, alpha);
    } else {
      out[param] = typeof value === "number" ? value : cloneValue(value);
    }
  });
  return out;
}

// scaleDistortionParams() softens drive/gain to avoid harsh transitions.
function scaleDistortionParams(moduleParams = {}, alpha) {
  const out = {};
  Object.entries(moduleParams).forEach(([param, value]) => {
    if (param.toLowerCase().includes("drive")) {
      out[param] = scaleNumber(value, alpha);
    } else {
      out[param] = typeof value === "number" ? value : cloneValue(value);
    }
  });
  return out;
}

// scaleModuleParams() routes each plugin through its specific scaler or the generic fallback.
function scaleModuleParams(moduleName, moduleParams, alpha) {
  const kind = detectModuleKind(moduleName, moduleParams);
  switch (kind) {
    case MODULE_KINDS.EQ:
      return scaleEqParams(moduleParams, alpha);
    case MODULE_KINDS.COMPRESSOR:
      return scaleCompressorParams(moduleParams, alpha);
    case MODULE_KINDS.REVERB:
      return scaleReverbParams(moduleParams, alpha);
    case MODULE_KINDS.DELAY:
      return scaleDelayParams(moduleParams, alpha);
    case MODULE_KINDS.CHORUS:
      return scaleChorusParams(moduleParams, alpha);
    case MODULE_KINDS.DISTORTION:
    case MODULE_KINDS.GAIN:
      return scaleDistortionParams(moduleParams, alpha);
    default: {
      const out = {};
      Object.entries(moduleParams || {}).forEach(([param, value]) => {
        if (typeof value === "number") {
          out[param] = isFreqKey(param) ? value : scaleNumber(value, alpha);
        } else if (Array.isArray(value)) {
          out[param] = scaleArray(value, alpha);
        } else {
          out[param] = cloneValue(value);
        }
      });
      return out;
    }
  }
}

// applyPerFxInterpolation() scales every plugin toward silence/dry based on alpha.
function applyPerFxInterpolation(params = {}, alpha = 1) {
  const clamped = clamp01(alpha);
  const out = {};
  Object.entries(params || {}).forEach(([module, moduleParams]) => {
    out[module] = scaleModuleParams(module, moduleParams, clamped);
  });
  return out;
}

// blendScalars() averages two numeric parameters with log treatment for frequencies.
const blendScalars = (a, b, w1, w2, key) => {
  if (typeof a !== "number" || typeof b !== "number") {
    return w2 >= w1 ? b : a;
  }
  const total = w1 + w2 || 1;
  if (isFreqKey(key) || isTimeKey(key)) {
    const logA = Math.log(Math.max(a, LOG_EPS));
    const logB = Math.log(Math.max(b, LOG_EPS));
    return Math.exp((w1 * logA + w2 * logB) / total);
  }
  return (w1 * a + w2 * b) / total;
};

// scaleValue() attenuates a value tree when one side of a blend is missing.
const scaleValue = (value, weight, keyHint = "") => {
  if (typeof value === "number") {
    return isFreqKey(keyHint) ? value : scaleNumber(value, weight);
  }
  if (Array.isArray(value)) {
    return value.map((entry) => scaleValue(entry, weight, keyHint));
  }
  if (value && typeof value === "object") {
    const out = {};
    Object.entries(value).forEach(([k, v]) => {
      out[k] = scaleValue(v, weight, k);
    });
    return out;
  }
  return cloneValue(value);
};

// blendArrays() walks paired arrays and blends each slot recursively.
const blendArrays = (arrA, arrB, w1, w2, key) => {
  if (!Array.isArray(arrA) || !Array.isArray(arrB)) {
    return w2 >= w1 ? cloneValue(arrB) : cloneValue(arrA);
  }
  const length = Math.max(arrA.length, arrB.length);
  const blended = [];
  const total = w1 + w2 || 1;
  const weightA = w1 / total;
  const weightB = w2 / total;
  for (let i = 0; i < length; i++) {
    const va = arrA[i];
    const vb = arrB[i];
    if (va === undefined && vb !== undefined) {
      blended.push(scaleValue(vb, weightB, key));
      continue;
    }
    if (vb === undefined && va !== undefined) {
      blended.push(scaleValue(va, weightA, key));
      continue;
    }
    if (typeof va === "number" && typeof vb === "number") {
      blended.push(blendScalars(va, vb, w1, w2, key));
    } else if (va && vb && typeof va === "object" && typeof vb === "object") {
      blended.push(blendModuleEntries(va, vb, w1, w2));
    } else {
      blended.push(w2 >= w1 ? cloneValue(vb) : cloneValue(va));
    }
  }
  return blended;
};

// blendModuleEntries() recursively combines object trees for modules present in both samples.
function blendModuleEntries(objA = {}, objB = {}, w1, w2) {
  const keys = new Set([...Object.keys(objA || {}), ...Object.keys(objB || {})]);
  const out = {};
  keys.forEach((key) => {
    const va = objA[key];
    const vb = objB[key];
    if (typeof va === "number" && typeof vb === "number") {
      out[key] = blendScalars(va, vb, w1, w2, key);
    } else if (Array.isArray(va) && Array.isArray(vb)) {
      out[key] = blendArrays(va, vb, w1, w2, key);
    } else if (va && vb && typeof va === "object" && typeof vb === "object") {
      out[key] = blendModuleEntries(va, vb, w1, w2);
    } else if (vb !== undefined && vb !== null) {
      out[key] = cloneValue(vb);
    } else {
      out[key] = cloneValue(va);
    }
  });
  return out;
}

// blendParamsPerceptually() is the same-chain code path: weighted interpolation for every plugin/key.
function blendParamsPerceptually(paramsA = {}, weightA = 0.5, paramsB = {}, weightB = 0.5) {
  const total = weightA + weightB || 1;
  const w1 = weightA / total;
  const w2 = weightB / total;
  const modules = new Set([
    ...Object.keys(paramsA || {}),
    ...Object.keys(paramsB || {}),
  ]);
  const out = {};
  modules.forEach((module) => {
    const moduleA = paramsA[module];
    const moduleB = paramsB[module];
    if (moduleA && moduleB) {
      out[module] = blendModuleEntries(moduleA, moduleB, w1, w2);
    } else if (moduleB) {
      out[module] = cloneValue(moduleB);
    } else {
      out[module] = cloneValue(moduleA);
    }
  });
  return out;
}

// NOTE: cross-chain interpolating is currently disabled in App.svelte.
// Normalize plugin ID by removing numeric suffix (e.g., "chorus_0" -> "chorus", "eq_6_0" -> "eq_6")
function normalizePluginId(pluginId) {
  // Match pattern: word_number at the end (e.g., "chorus_0", "phaser_1")
  // Keep patterns like "eq_6" but remove final "_0" suffix
  return pluginId.replace(/_(\d+)$/, '');
}

// NOTE: cross-chain interpolating is currently disabled in App.svelte.
// haveSameChain() checks whether both samples share identical plugin types (ignoring instance IDs).
function haveSameChain(paramsA = {}, paramsB = {}) {
  const keysA = Object.keys(paramsA || {}).map(normalizePluginId);
  const keysB = Object.keys(paramsB || {}).map(normalizePluginId);
  if (keysA.length !== keysB.length) return false;
  const setB = new Set(keysB);
  return keysA.every((key) => setB.has(key));
}


// Master interpolation engine
export function interpolateBetween(paramA = {}, paramB = {}, t = 0.5) {
  const ratio = clamp01(t);

  if (!paramA || Object.keys(paramA).length === 0) return cloneValue(paramB);
  if (!paramB || Object.keys(paramB).length === 0) return cloneValue(paramA);

  if (haveSameChain(paramA, paramB)) {
    const blended = blendParamsPerceptually(paramA, 1 - ratio, paramB, ratio);
    return blended;
  }

  // NOTE: cross-chain interpolating is currently disabled in App.svelte.
  throw new Error("Cross-chain interpolating is not supported (yet??)");
}

// scaleParamsForDryWet() scales a single FX chain toward dry using perceptual curves.
export function scaleParamsForDryWet(params = {}, t = 0.5) {
  const alpha = Math.max(clamp01(t), 0.05);
  const curved = Math.pow(alpha, 0.7);
  return applyPerFxInterpolation(params, curved);
}
