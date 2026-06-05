/**
 * Pedalboard > Tone.js Parameter Conversion
 * ref: https://github.com/spotify/pedalboard
 * Converts backend Pedalboard FX parameters into Tone.js audio nodes.
 * NOT bit-perfect - applies compensations for implementation differences.
 *
 * Pedalboard:
 * https://github.com/spotify/pedalboard/tree/master/pedalboard/plugins
 * 
 * Tone.js:
 * https://tonejs.github.io/docs/15.1.22/index.html
 * 

 */

import * as Tone from "tone";

// Utility functions for unit conversion
const clamp = (v, min = 0, max = 1) => Math.min(Math.max(v, min), max);
const msToSeconds = (ms) => (ms ?? 0) / 1000;  // Convert milliseconds to seconds
const dBToGain = (db) => Tone.dbToGain(db ?? 0);  // Convert decibels to linear gain

/**
 * Main conversion function - maps backend plugin params to Tone.js FX chain
 * @param {Object} params - Pedalboard parameters ({ plugins: { PluginName: {...} } })
 * @returns {Array} Array of Tone.js audio nodes ready to connect
 */
export function mapBackendParamsToTone(params) {
  const plugins = params?.plugins ?? params ?? {};
  const chain = [];
  const nodeMap = {};

  for (const [pid, p] of Object.entries(plugins)) {
    try {
    if (pid.startsWith("gain")) {
        const node = new Tone.Gain({ gain: dBToGain(p.gain_db) });
        chain.push(node);
        nodeMap[pid] = { type: "gain", node };
        continue;
      }

    // Highpass / lowpass
    if (pid.startsWith("highpass")) {
      const node = new Tone.Filter({
          type: "highpass",
          frequency: clamp(p.cutoff_hz ?? 1000, 20, 20000),
          Q: 0.3, // gentler slope (closer to Pedalboard's 6dB/oct)
        });
      chain.push(node);
      nodeMap[pid] = { type: "filter", node, filterType: "highpass" };
      continue;
    }

    if (pid.startsWith("lowpass")) {
      const node = new Tone.Filter({
          type: "lowpass",
          frequency: clamp(p.cutoff_hz ?? 5000, 20, 20000),
          Q: 0.3, // match Pedalboard's gentle LP filters
        });
      chain.push(node);
      nodeMap[pid] = { type: "filter", node, filterType: "lowpass" };
      continue;
    }

    // EQ: Pedalboard PeakFilter is sharper than WebAudio.
    // We boost Q and gain ~10–20% to mimic the tighter analog curve.
    if (pid.startsWith("eq")) {
      const bands = Array.isArray(p.bands) ? p.bands : [];
      const eqBands = [];
      bands.forEach((band) => {
        const node = new Tone.Filter({
            type: "peaking",
            frequency: clamp(band.freq_hz ?? 1000, 20, 20000),
            gain: clamp((band.gain_db ?? 0) * 1.15, -40, 40), // PB peaks are slightly stronger
            Q: clamp((band.q ?? 1) * 1.25, 0.01, 20), // PB Q is tighter -> sharper resonance
          });
        chain.push(node);
        eqBands.push(node);
      });
      nodeMap[pid] = { type: "eq", bands: eqBands };
      continue;
    }

    // Compressor: Pedalboard is smooth soft-knee JUCE style.
    // Tone.js/WebAudio = harsher; we soften it manually.
    if (pid.startsWith("compressor")) {
      // Clamp attack/release before conversion to prevent invalid values
      const attackMs = clamp(p.attack_ms ?? 10, 0.001, 500); // Max 500ms
      const releaseMs = clamp(p.release_ms ?? 100, 1, 1000);  // Max 1000ms

      const node = new Tone.Compressor({
          threshold: clamp(p.threshold_db ?? -20, -100, 0),
          ratio: clamp(p.ratio ?? 2, 1, 20),
          knee: 20, // closer to JUCE-style soft knee
          attack: clamp(msToSeconds(attackMs), 0.0001, 1),
          release: clamp(msToSeconds(releaseMs), 0.001, 2),
        });
      chain.push(node);
      nodeMap[pid] = { type: "compressor", node };
      continue;
    }

    // Limiter: Pedalboard is transparent and mildly oversampled.
    // WebAudio limiter is simple; we add a pre-compressor for smoothness.
    if (pid.startsWith("limiter")) {
      const limiterReleaseMs = clamp(p.release_ms ?? 40, 5, 500);
      // Pre-conditioner: smooth the peaks before the hard limit
      const pre = new Tone.Compressor({
          threshold: (p.threshold_db ?? -6) - 6,
          ratio: 20,
          attack: 0.001,
          release: clamp(msToSeconds(limiterReleaseMs), 0.005, 1),
          knee: 10,
        });
      const limiter = new Tone.Limiter({
        threshold: p.threshold_db ?? -6,
      });
      chain.push(pre);
      chain.push(limiter);
      nodeMap[pid] = { type: "limiter", pre, limiter };
      continue;
    }

    // Gate: Pedalboard NoiseGate ~= downward expander.
    // Tone.js doesn’t have a gate > approximate with soft-knee comp.
    if (pid.startsWith("gate")) {
      const node = new Tone.Compressor({
          threshold: p.threshold_db ?? -40,
          ratio: clamp(p.ratio ?? 10, 2, 30),
          knee: 30,
          attack: msToSeconds((p.attack_ms ?? 5) * 2),
          release: msToSeconds((p.release_ms ?? 100) * 2),
        });
      chain.push(node);
      nodeMap[pid] = { type: "gate", node };
      continue;
    }

    // Chorus: Pedalboard is subtle, Tone.js can be stronger.
    // Fixed: Reduced feedback multiplier to prevent ringing artifacts
    // Compensations: depth +10%, feedback -5%, mix +15% (single pass, no stacking)
    if (pid.startsWith("chorus")) {
      // Backend: 3-20ms centre_delay, map to Tone.js delayTime (3-20ms)
      const delayMs = clamp(p.centre_delay_ms ?? 7, 3, 20);
      const rawDepth = p.depth ?? 0.3;
      const rawFeedback = p.feedback ?? 0;
      const rawMix = p.mix ?? 0.5;

      // Apply compensations (single pass to avoid stacking)
      const depth = clamp(rawDepth, 0, 1);
      const feedback = clamp(rawFeedback, 0, 0.95);
      const mix = clamp(rawMix, 0, 1);
      const spread = clamp(60 + depth * 180, 40, 240);

      const node = new Tone.Chorus({
          frequency: clamp(p.rate_hz ?? 1, 0.05, 12),
          delayTime: delayMs,
          depth,
          feedback,
          spread,
          wet: mix,  // Already compensated, don't multiply again
        }).start();
      chain.push(node);
      nodeMap[pid] = { type: "chorus", node };
      continue;
    }

    // Phaser: Pedalboard stages feel gentler.
    // Tone.js Phaser is intense >> we scale parameters for wider range
    // Fixed: Reduced Q scaling to prevent harsh whistling
    if (pid.startsWith("phaser")) {
      // Backend: rate 0.01-12 Hz, depth 0.05-1.0, centre_freq 80-6000 Hz, feedback 0-0.85

      // Map depth to octaves: 0.05→0.5 octaves (subtle), 1.0→6 octaves (intense)
      const octaves = clamp(0.5 + (p.depth ?? 0.5) * 5.5, 0.5, 6);

      // Map feedback to Q: 0→2.5 (gentle), 0.75→11.5 (resonant without whistling)
      const Q = clamp(2.5 + (p.feedback ?? 0) * 12, 2.5, 16);

      const phaser = new Tone.Phaser({
        frequency: clamp(p.rate_hz ?? 1, 0.01, 20),
        octaves,
        baseFrequency: clamp(p.centre_frequency_hz ?? 800, 80, 6000),
        Q,
      });
      phaser.wet.value = clamp(p.mix ?? 0.5, 0, 1);
      chain.push(phaser);
      nodeMap[pid] = { type: "phaser", node: phaser };
      continue;
    }

    // Delay: Tone.js FeedbackDelay is close to Pedalboard Delay.
    if (pid.startsWith("delay")) {
      const node = new Tone.FeedbackDelay({
          delayTime: clamp(p.delay_seconds ?? 0.25, 0.001, 1.0),
          feedback: clamp(p.feedback ?? 0.3, 0, 0.98),
          wet: clamp(p.mix ?? 0.3, 0, 1),
        });
      chain.push(node);
      nodeMap[pid] = { type: "delay", node };
      continue;
    }

    // Reverb: Pedalboard is Freeverb-like; Tone.js is convolution-based.
    // Map room_size to decay time with wider perceptual range
    if (pid.startsWith("reverb")) {
      const rs = clamp(p.room_size ?? 0.3, 0.01, 0.99);

      // Improved decay mapping: 0.1→0.1s (tiny room), 0.99→30s (cathedral)
      // Using exponential curve for better perceptual spread
      const decay = clamp(0.1 + Math.pow(rs, 1.8) * 29.9, 0.1, 30);

      const preDelay = clamp(0.005 + rs * 0.02, 0.005, 0.04);
      const reverb = new Tone.Reverb({
        decay,
        preDelay,
      });

      // Pedalboard uses wet_level + dry_level, Tone.js uses single wet control
      // Convert to equivalent wet value
      const wetLevel = clamp(p.wet_level ?? 0.3, 0, 1);
      const dryLevel = clamp(p.dry_level ?? 0.75, 0, 1);

      // Approximate the wet/dry mix
      if (dryLevel > 0) {
        reverb.wet.value = clamp(wetLevel / (wetLevel + dryLevel), 0, 1);
      } else {
        reverb.wet.value = 1; // All wet if no dry signal
      }

      chain.push(reverb);
      const damping = clamp(p.damping ?? 0.5, 0, 1);
      const cutoff = 1200 + (1 - damping) * 10000;
      const dampFilter = new Tone.Filter({ type: "lowpass", frequency: cutoff, Q: 0.7 });
      chain.push(dampFilter);
      const width = clamp(p.width ?? 0.5, 0, 1);
      const widener = new Tone.StereoWidener({ width });
      chain.push(widener);
      nodeMap[pid] = { type: "reverb", reverb, dampFilter, widener };
      continue;
    }

    // Distortion: Pedalboard uses tanh waveshaping with dB drive.
    // Tone.js distortion curve is harsher → we use a soft exp curve
    if (pid.startsWith("distortion")) {
      const db = clamp(p.drive_db ?? 0, 0, 40);

      // Improved curve: maps 0dB→0, 35dB→0.95 for better utilization
      // Formula: amount = tanh(db/20) adjusted to reach 0.95 at 35dB
      const amount = clamp(Math.tanh(db / 18), 0, 0.99);

      const node = new Tone.Distortion({ distortion: amount, oversample: "4x" });
      chain.push(node);
      nodeMap[pid] = { type: "distortion", node };
      continue;
    }

    } catch (err) {
      console.error(`Failed to create Tone.js node for plugin "${pid}":`, err, p);
      // Skip this plugin and continue with the rest of the chain
    }
  }

  return { nodes: chain, nodeMap };
}

const rampParam = (param, value, rampTime) => {
  if (!param) return;
  if (typeof param.rampTo === "function") {
    param.rampTo(value, rampTime);
  } else if (typeof param.value !== "undefined") {
    param.value = value;
  }
};

export function applyParamsToToneNodes(params, nodeMap, rampTime = 0.15) {
  const plugins = params?.plugins ?? params ?? {};
  Object.entries(plugins).forEach(([pid, p]) => {
    const entry = nodeMap?.[pid];
    if (!entry) return;
    switch (entry.type) {
      case "gain": {
        rampParam(entry.node.gain, dBToGain(p.gain_db ?? 0), rampTime);
        break;
      }
      case "filter": {
        rampParam(entry.node.frequency, clamp(p.cutoff_hz ?? 1000, 20, 20000), rampTime);
        break;
      }
      case "eq": {
        const bands = Array.isArray(p.bands) ? p.bands : [];
        bands.forEach((band, idx) => {
          const node = entry.bands[idx];
          if (!node) return;
          rampParam(node.frequency, clamp(band.freq_hz ?? 1000, 20, 20000), rampTime);
          rampParam(node.gain, clamp((band.gain_db ?? 0) * 1.15, -40, 40), rampTime);
          rampParam(node.Q, clamp((band.q ?? 1) * 1.25, 0.01, 20), rampTime);
        });
        break;
      }
      case "compressor": {
        const attackMs = clamp(p.attack_ms ?? 10, 0.001, 500);
        const releaseMs = clamp(p.release_ms ?? 100, 1, 1000);
        rampParam(entry.node.threshold, clamp(p.threshold_db ?? -20, -100, 0), rampTime);
        rampParam(entry.node.ratio, clamp(p.ratio ?? 2, 1, 20), rampTime);
        rampParam(entry.node.attack, clamp(msToSeconds(attackMs), 0.0001, 1), rampTime);
        rampParam(entry.node.release, clamp(msToSeconds(releaseMs), 0.001, 2), rampTime);
        break;
      }
      case "limiter": {
        const limiterReleaseMs = clamp(p.release_ms ?? 40, 5, 500);
        rampParam(entry.pre.threshold, (p.threshold_db ?? -6) - 6, rampTime);
        rampParam(entry.pre.release, clamp(msToSeconds(limiterReleaseMs), 0.005, 1), rampTime);
        rampParam(entry.limiter.threshold, p.threshold_db ?? -6, rampTime);
        break;
      }
      case "gate": {
        rampParam(entry.node.threshold, p.threshold_db ?? -40, rampTime);
        rampParam(entry.node.ratio, clamp(p.ratio ?? 10, 2, 30), rampTime);
        rampParam(entry.node.attack, msToSeconds((p.attack_ms ?? 5) * 2), rampTime);
        rampParam(entry.node.release, msToSeconds((p.release_ms ?? 100) * 2), rampTime);
        break;
      }
      case "chorus": {
        const feedback = clamp(p.feedback ?? 0, 0, 0.95);
        const mix = clamp(p.mix ?? 0.5, 0, 1);
        const delayMs = clamp(p.centre_delay_ms ?? 7, 3, 20);
        const depth = clamp(p.depth ?? 0.3, 0, 1);
        const spread = clamp(60 + depth * 180, 40, 240);
        rampParam(entry.node.frequency, clamp(p.rate_hz ?? 1, 0.05, 12), rampTime);
        entry.node.delayTime = delayMs;
        entry.node.depth = depth;
        entry.node.spread = spread;
        if (entry.node.feedback?.rampTo) {
          entry.node.feedback.rampTo(feedback, rampTime);
        } else if (entry.node.feedback?.value !== undefined) {
          entry.node.feedback.value = feedback;
        }
        if (entry.node.wet?.rampTo) {
          entry.node.wet.rampTo(mix, rampTime);
        } else if (entry.node.wet?.value !== undefined) {
          entry.node.wet.value = mix;
        }
        break;
      }
      case "phaser": {
        const octaves = clamp(0.5 + (p.depth ?? 0.5) * 5.5, 0.5, 6);
        const Q = clamp(2.5 + (p.feedback ?? 0) * 12, 2.5, 16);
        rampParam(entry.node.frequency, clamp(p.rate_hz ?? 1, 0.01, 20), rampTime);
        if (entry.node.octaves?.rampTo) {
          entry.node.octaves.rampTo(octaves, rampTime);
        } else if (entry.node.octaves?.value !== undefined) {
          entry.node.octaves.value = octaves;
        } else {
          entry.node.octaves = octaves;
        }
        const baseFrequency = clamp(p.centre_frequency_hz ?? 800, 80, 6000);
        if (entry.node.baseFrequency?.rampTo) {
          entry.node.baseFrequency.rampTo(baseFrequency, rampTime);
        } else if (entry.node.baseFrequency?.value !== undefined) {
          entry.node.baseFrequency.value = baseFrequency;
        } else {
          entry.node.baseFrequency = baseFrequency;
        }
        if (entry.node.Q?.rampTo) {
          entry.node.Q.rampTo(Q, rampTime);
        } else if (entry.node.Q?.value !== undefined) {
          entry.node.Q.value = Q;
        } else {
          entry.node.Q = Q;
        }
        if (entry.node.wet?.rampTo) {
          entry.node.wet.rampTo(clamp(p.mix ?? 0.5, 0, 1), rampTime);
        } else if (entry.node.wet?.value !== undefined) {
          entry.node.wet.value = clamp(p.mix ?? 0.5, 0, 1);
        }
        break;
      }
      case "delay": {
        rampParam(entry.node.delayTime, clamp(p.delay_seconds ?? 0.25, 0.001, 1.0), rampTime);
        if (entry.node.feedback?.rampTo) {
          entry.node.feedback.rampTo(clamp(p.feedback ?? 0.3, 0, 0.98), rampTime);
        } else if (entry.node.feedback?.value !== undefined) {
          entry.node.feedback.value = clamp(p.feedback ?? 0.3, 0, 0.98);
        }
        if (entry.node.wet?.rampTo) {
          entry.node.wet.rampTo(clamp(p.mix ?? 0.3, 0, 1), rampTime);
        } else if (entry.node.wet?.value !== undefined) {
          entry.node.wet.value = clamp(p.mix ?? 0.3, 0, 1);
        }
        break;
      }
      case "reverb": {
        const rs = clamp(p.room_size ?? 0.3, 0.01, 0.99);
        const decay = clamp(0.1 + Math.pow(rs, 1.8) * 29.9, 0.1, 30);
        const preDelay = clamp(0.005 + rs * 0.02, 0.005, 0.04);
        entry.reverb.decay = decay;
        if (entry.reverb.preDelay?.rampTo) {
          entry.reverb.preDelay.rampTo(preDelay, rampTime);
        } else {
          entry.reverb.preDelay = preDelay;
        }
        const wetLevel = clamp(p.wet_level ?? 0.3, 0, 1);
        const dryLevel = clamp(p.dry_level ?? 0.75, 0, 1);
        const wet = dryLevel > 0 ? clamp(wetLevel / (wetLevel + dryLevel), 0, 1) : 1;
        if (entry.reverb.wet?.rampTo) {
          entry.reverb.wet.rampTo(wet, rampTime);
        } else if (entry.reverb.wet?.value !== undefined) {
          entry.reverb.wet.value = wet;
        }
        const damping = clamp(p.damping ?? 0.5, 0, 1);
        const cutoff = 1200 + (1 - damping) * 10000;
        rampParam(entry.dampFilter.frequency, cutoff, rampTime);
        rampParam(entry.widener.width, clamp(p.width ?? 0.5, 0, 1), rampTime);
        break;
      }
      case "distortion": {
        const db = clamp(p.drive_db ?? 0, 0, 40);
        const amount = clamp(Math.tanh(db / 18), 0, 0.99);
        entry.node.distortion = amount;
        break;
      }
      default:
        break;
    }
  });
}
