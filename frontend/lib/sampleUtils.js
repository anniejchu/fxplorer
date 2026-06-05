export function deriveSampleIndex(sample, samples = []) {
  if (typeof sample?.idx === 'number') return sample.idx;
  if (typeof sample?.index === 'number') return sample.index;
  if (Array.isArray(samples) && samples.length) {
    const byId = samples.findIndex((item) => item?.id && item.id === sample?.id);
    if (byId >= 0) return byId;
    const byAudio = samples.findIndex((item) => item?.audio_path && item.audio_path === sample?.audio_path);
    if (byAudio >= 0) return byAudio;
    const byName = samples.findIndex((item) => item?.name === sample?.name);
    if (byName >= 0) return byName;
  }
  return null;
}
