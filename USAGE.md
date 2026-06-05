# Usage Guide

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `H` | Toggle floating controls visibility |
| `1` / `2` | Assign hovered sample to interpolation point A / B |
| `M` | Enter keyboard interpolation mode |
| `← →` | Adjust interpolation slider (3% steps, interpolation mode only) |
| `ESC` | Exit keyboard interpolation mode |
| `[` / `]` | Navigate special points (prev / next) |

## Generating a Population

1. Upload a dry audio file (or use the default `assets/salsa_piano.wav`)
2. Pick up to 3 FX from the grid (EQ, Reverb, Compressor, Delay, etc.)
3. Choose exploration mode:
   - **Single / Chain** — each effect or ordered chain applied individually
   - **Groups** — preset category combos
4. Adjust per-combination sample counts (30–50 recommended)
5. Click **Generate & Populate** — the 3-stage pipeline runs (~20–60 seconds)

## Hover & Preview

- Hover over any point to preview (60% volume, 5-second clip)
- **In-Situ Playback** (default): crossfade between samples on hover
- **Restart**: immediate switch on hover

## Select & Edit

- Click a point to select it (full looping playback at 80% volume)
- Edit parameters live in the FX Panel (DAW knobs or numeric inputs)
- A green **edit ghost** shows the projected 2D position of your edits
- Save the edited FX as a new named sample

## Interpolate Between Samples

1. Hover sample A → press `1`; hover sample B → press `2`
2. Press `M` to enter keyboard interpolation mode:
   - View zooms to the interpolation line with a smooth animation
   - `← →` blends between A and B; audio updates in real-time (50ms debounce)
   - The top overlay shows a gradient interpolation indicator
3. Press `ESC` to exit and reset zoom

You can also use sidebar sliders to blend manually.

## Search

**Text search (CLAP mode):** Type a description ("warm analog reverb", "bright compressed drums"). Orange virtual points appear on canvas; top matches are highlighted with rank labels.

**Audio reference (AFx-Rep mode):** Upload a reference audio file. Top k=10 perceptually similar FX chains are highlighted with similarity scores.

## Presets

- **Save** — capture current FX parameters with a custom name
- **Load** — apply a preset (presets can also serve as interpolation endpoints)
- **Export / Import** — share preset collections as JSON
- Stored in browser LocalStorage; no backend required

## Special Points Navigation

Press `H` to show the floating controls, then open the special points navigator (⭐ button) or use `[` / `]` to jump between interpolated, edited, and renamed samples.
