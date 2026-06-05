<script>
  import { onMount, afterUpdate, createEventDispatcher } from 'svelte';
  import { DEFAULT_MODE, VIEW_PAD, ZOOM_ANIMATION_SPEED } from '../lib/constants.js';
  import { getChainKeyFromParams } from '../lib/fxUtils.js';
  import { isDryParams } from '../lib/interpolationUtils.js';
  
  export let coords = [];
  export let samples = [];

  export let currentMode = DEFAULT_MODE;
  export let searchResults = [];
  export let virtualPoints = [];
  export let selectedSample = null;
  export let hoveredSample = null;
  export let showOverlays = true;
  export let interpolationPointA = null;
  export let interpolationPointB = null;
  export let interpolationActive = false;
  export let keyboardInterpolationMode = false;
  export let interpolationChainKey = null;
  export let interpolationPointAIndex = null;
  export let interpolationPointBIndex = null;
  export let interpolationGhost = null;
  export let editGhost = null;
  export let editGhostLoading = false;

  const dispatch = createEventDispatcher();

  let canvas;
  let ctx;
  let width = 800;
  let height = 600;
  let hoveredIndex = null;

  // Visual constants
  const POINT_RADIUS = 6;
  const HOVER_RADIUS = 10;
  const SELECTED_RADIUS = 12;
  const VIRTUAL_RADIUS = 5;
  const CLAMP_MIN = -0.1;
  const CLAMP_MAX = 1.1;
  const ZOOM_MIN = 0.6;
  const ZOOM_MAX = 6.0;
  const ZOOM_WHEEL_FACTOR = 1.12;
  const ZOOM_KEY_FACTOR = 1.18;

  let viewBounds = { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  const CHAIN_COLORS = [
    '#d1432e',
    '#1f8a70',
    '#2d6cdf',
    '#f2a000',
    '#7d4cc2',
    '#0096c7',
    '#b14f7a',
    '#2e7d32',
    '#ff6f3c',
  ];
  const chainColorMap = new Map();

  // Zoom and pan state
  let zoomActive = false;
  let zoomLevel = 1.0;
  let zoomCenterX = 0.5;  // Normalized [0,1]
  let zoomCenterY = 0.5;
  let zoomPadding = 0.25; // 25% padding around interpolation points
  let zoomEmphasis = false; // Only true for interpolation zoom (dims non-interpolation points)

  // Animation state
  let animationFrame = null;
  let targetZoomLevel = 1.0;
  let targetZoomCenterX = 0.5;
  let targetZoomCenterY = 0.5;

  $: viewBounds = computeBounds(coords);

  onMount(() => {
    ctx = canvas.getContext('2d');
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    window.addEventListener('keydown', handleZoomKeys);
    
    return () => {
      window.removeEventListener('resize', updateDimensions);
      window.removeEventListener('keydown', handleZoomKeys);
    };
  });

  function updateDimensions() {
    const container = canvas.parentElement;
    width = container.clientWidth;
    height = container.clientHeight;
    canvas.width = width;
    canvas.height = height;
    draw();
  }

  function computeBounds(points) {
    if (!Array.isArray(points) || points.length === 0) {
      return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    points.forEach((p) => {
      if (!p) return;
      const x = typeof p.x === 'number' ? p.x : 0;
      const y = typeof p.y === 'number' ? p.y : 0;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    });
    if (!isFinite(minX) || !isFinite(maxX) || !isFinite(minY) || !isFinite(maxY)) {
      return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
    }
    if (minX === maxX) {
      minX -= 1;
      maxX += 1;
    }
    if (minY === maxY) {
      minY -= 1;
      maxY += 1;
    }
    return {
      minX: minX - (maxX - minX) * VIEW_PAD,
      maxX: maxX + (maxX - minX) * VIEW_PAD,
      minY: minY - (maxY - minY) * VIEW_PAD,
      maxY: maxY + (maxY - minY) * VIEW_PAD,
    };
  }

  function getChainKey(sample, coord) {
    if (sample?.type === 'dry' || coord?.type === 'dry') return 'dry';
    const paramsChain = sample?.params?.chain;
    if (Array.isArray(paramsChain) && paramsChain.length > 0) {
      return paramsChain.map((entry) => entry?.type || entry).join('>');
    }
    const rawChain = sample?.chain;
    if (Array.isArray(rawChain) && rawChain.length > 0) {
      return rawChain.map((entry) => entry?.type || entry).join('>');
    }
    return 'unknown';
  }

  function getInterpolationEligibility(sample, coord) {
    const anchorParams = interpolationPointA?.params || interpolationPointB?.params || {};
    const baseKey = interpolationChainKey || getChainKeyFromParams(anchorParams);
    if (!baseKey) return true;
    if (baseKey === 'dry') return true;
    const rawCandidateParams = sample?.params?.plugins || sample?.params || {};
    const candidateKey = isDryParams(rawCandidateParams)
      ? 'dry'
      : getChainKeyFromParams(rawCandidateParams);
    if (candidateKey === 'dry') return true;
    return candidateKey === baseKey;
  }

  function getChainColor(chainKey) {
    if (!chainKey || chainKey === 'dry') return '#f97316';
    if (!chainColorMap.has(chainKey)) {
      const idx = chainColorMap.size % CHAIN_COLORS.length;
      chainColorMap.set(chainKey, CHAIN_COLORS[idx]);
    }
    return chainColorMap.get(chainKey);
  }

  // Animation loop for smooth zoom
  function animateZoom() {
    const deltaZoom = targetZoomLevel - zoomLevel;
    const deltaCenterX = targetZoomCenterX - zoomCenterX;
    const deltaCenterY = targetZoomCenterY - zoomCenterY;

    // Check if animation is complete (close enough to target)
    const threshold = 0.001;
    if (Math.abs(deltaZoom) < threshold &&
        Math.abs(deltaCenterX) < threshold &&
        Math.abs(deltaCenterY) < threshold) {
      // Snap to final values
      zoomLevel = targetZoomLevel;
      zoomCenterX = targetZoomCenterX;
      zoomCenterY = targetZoomCenterY;
      animationFrame = null;
      draw();
      return;
    }

    // Smooth interpolation
    zoomLevel += deltaZoom * ZOOM_ANIMATION_SPEED;
    zoomCenterX += deltaCenterX * ZOOM_ANIMATION_SPEED;
    zoomCenterY += deltaCenterY * ZOOM_ANIMATION_SPEED;

    draw();
    animationFrame = requestAnimationFrame(animateZoom);
  }

  // Zoom control functions (exposed to parent)
  export function zoomToPoints(indexA, indexB) {
    if (!coords || coords.length === 0) return;

    const pointA = coords[indexA];
    const pointB = coords[indexB];

    if (!pointA || !pointB) return;

    // Calculate target center point between A and B
    targetZoomCenterX = (pointA.x + pointB.x) / 2;
    targetZoomCenterY = (pointA.y + pointB.y) / 2;

    // Calculate required zoom level - less dramatic, accounts for bottom panel
    const dx = Math.abs(pointA.x - pointB.x);
    const dy = Math.abs(pointA.y - pointB.y);
    const distance = Math.max(dx, dy);

    // More conservative zoom - line takes up ~50% of screen with padding
    // Larger padding = less zoom = can see more context
    targetZoomLevel = distance > 0 ? 1 / (distance + zoomPadding) : 2.0;
    targetZoomLevel = Math.max(1.2, Math.min(targetZoomLevel, 3.0)); // Clamp 1.2x-3x (avoid clipping)

    // Shift center slightly up to account for bottom FX panel
    targetZoomCenterY = targetZoomCenterY - 0.05; // Move view up 5% to avoid bottom panel

    zoomActive = true;
    zoomEmphasis = true;

    // Cancel any existing animation
    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
    }

    // Start animation
    animationFrame = requestAnimationFrame(animateZoom);
  }

  export function resetZoom() {
    // Animate back to default view
    targetZoomLevel = 1.0;
    targetZoomCenterX = 0.5;
    targetZoomCenterY = 0.5;

    // Cancel any existing animation
    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
    }

    zoomEmphasis = false;
    // Start animation
    animationFrame = requestAnimationFrame(() => {
      animateZoom();
      // Once animation completes, disable zoom mode
      const checkComplete = () => {
        if (!animationFrame) {
          zoomActive = false;
          draw();
        } else {
          requestAnimationFrame(checkComplete);
        }
      };
      checkComplete();
    });
  }

  afterUpdate(() => {
    if (ctx && coords.length > 0) {
      draw();
    }
  });

  function draw() {
    if (!ctx) return;

    // Clear canvas
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, width, height);

    // Draw grid
    drawGrid();

    // Draw all regular points
    coords.forEach((coord, index) => {
      const isHovered = hoveredIndex === index;
      const isSelected = selectedSample?.index === index;
      const isSearchResult = searchResults.some((r) => r.idx === index);
      const isInterpolationA = interpolationPointAIndex === index;
      const isInterpolationB = interpolationPointBIndex === index;
      const isDry = samples?.[index]?.type === 'dry' || coord?.type === 'dry';
      const chainKey = getChainKey(samples?.[index], coord);
      const chainColor = getChainColor(chainKey);
      const { px, py } = transformCoord(coord.x, coord.y);
      const isEligible = getInterpolationEligibility(samples?.[index], coord);

      // Dim non-interpolation points when in zoom mode
      let opacity = 1.0;
      if (zoomEmphasis) {
        const isInterpolationPoint = isInterpolationA || isInterpolationB;
        opacity = isInterpolationPoint ? 1.0 : 0.3;
      }

      ctx.globalAlpha = isEligible ? opacity : opacity * 0.2;

      // Draw larger, glowing circles for interpolation points during keyboard mode
      if (zoomEmphasis && (isInterpolationA || isInterpolationB)) {
        const color = isInterpolationA ? '#c56b52' : '#8fa772';

        // Glow effect
        ctx.shadowBlur = 15;
        ctx.shadowColor = color;

        // Larger radius
        ctx.beginPath();
        ctx.arc(px, py, 12, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        // Reset shadow
        ctx.shadowBlur = 0;
      } else {
        // Normal point rendering
        drawPoint(
          px,
          py,
          isSelected,
          isHovered,
          isSearchResult,
          false,
          isInterpolationA,
          isInterpolationB,
          isDry,
          chainColor,
          isEligible ? 1 : 0.2
        );
      }

      ctx.globalAlpha = 1.0; // Reset opacity

      if (isInterpolationA) drawInterpolationLabel(px, py, 'A');
      if (isInterpolationB) drawInterpolationLabel(px, py, 'B');
    });

    // Draw virtual points from repopulation
    virtualPoints.forEach(point => {
      const { px: vx, py: vy } = transformCoord(point?.coords?.[0] ?? 0, point?.coords?.[1] ?? 0);
      drawPoint(
        vx,
        vy,
        false,
        false,
        false,
        true,
        false,
        false,
        false,
        null,
        1
      );
      if (point?.text) {
        drawVirtualLabel(vx, vy, point.text);
      }
    });

    if (hasInterpolationPair()) {
      drawInterpolationConnector();
    }
    if (interpolationGhost) {
      const { px: gx, py: gy } = transformCoord(interpolationGhost.x, interpolationGhost.y);
      drawGhostPoint(gx, gy, 'interpolation');
    }
    if (editGhost) {
      const { px: gx, py: gy } = transformCoord(editGhost.x, editGhost.y);
      drawGhostPoint(gx, gy, 'edit');
    }

    // Draw labels for search results
    if (searchResults.length > 0) {
      drawSearchResultLabels();
    }
  }

  function drawGrid() {
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = 1;

    // Vertical lines
    for (let i = 0; i <= 10; i++) {
      const x = (i / 10) * width;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Horizontal lines
    for (let i = 0; i <= 10; i++) {
      const y = (i / 10) * height;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
  }

  function drawPoint(x, y, isSelected, isHovered, isSearchResult, isVirtual, isInterpolationA, isInterpolationB, isDry, baseColor, dimFactor = 1) {
    ctx.save();

    let radius = POINT_RADIUS;
    let color = baseColor || '#4a5568';
    let alpha = 0.6;
    const isInterpolation = isInterpolationA || isInterpolationB;

    if (isVirtual) {
      radius = VIRTUAL_RADIUS;
      color = '#f59e0b';
      alpha = 0.4;
    } else if (isDry) {
      color = '#f97316';
      alpha = 0.9;
    } else if (isInterpolation) {
      radius = Math.max(radius, SELECTED_RADIUS);
      color = isInterpolationA ? '#d6a36a' : '#8fa772';
      alpha = 1;
    } else if (isSelected) {
      radius = SELECTED_RADIUS;
      color = '#b68b5e';
      alpha = 1.0;
    } else if (isHovered) {
      radius = HOVER_RADIUS;
      color = '#c0976b';
      alpha = 0.9;
    } else if (isSearchResult) {
      color = '#10b981';
      alpha = 0.8;
    }

    // Outer glow for selected/hovered
    if (isSelected || isHovered) {
      ctx.shadowColor = color;
      ctx.shadowBlur = 15;
    }

    // Draw point
    ctx.fillStyle = color;
    ctx.globalAlpha = alpha * dimFactor;
    if (isDry) {
      const size = radius * 1.9;
      ctx.fillRect(x - size / 2, y - size / 2, size, size);
      ctx.strokeStyle = '#fff7ed';
      ctx.lineWidth = 2;
      ctx.strokeRect(x - size / 2, y - size / 2, size, size);
    } else {
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
    }

    if (isInterpolation) {
      ctx.strokeStyle = isInterpolationA ? '#d6a36a' : '#8fa772';
      ctx.lineWidth = 3;
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      ctx.arc(x, y, radius + 4, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Ring for search results
    if (isSearchResult) {
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.globalAlpha = 1.0;
      ctx.beginPath();
      ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawVirtualLabel(x, y, label) {
    const text = String(label || '').slice(0, 40);
    if (!text) return;
    ctx.save();
    ctx.font = '11px sans-serif';
    ctx.fillStyle = '#fbbf24';
    ctx.textAlign = 'center';
    ctx.fillText(text, x, y - 12);
    ctx.restore();
  }
  
  function drawInterpolationLabel(x, y, label) {
    ctx.save();
    ctx.font = 'bold 11px sans-serif';
    ctx.fillStyle = label === 'A' ? '#d6a36a' : '#8fa772';
    ctx.textAlign = 'center';
    ctx.fillText(label, x, y - 16);
    ctx.restore();
  }

  function hasInterpolationPair() {
    if (typeof interpolationPointAIndex !== 'number' || typeof interpolationPointBIndex !== 'number') return false;
    return Boolean(coords[interpolationPointAIndex] && coords[interpolationPointBIndex]);
  }

  function drawInterpolationConnector() {
    if (!hasInterpolationPair()) return;
    const pointA = coords[interpolationPointAIndex];
    const pointB = coords[interpolationPointBIndex];
    const { px: ax, py: ay } = transformCoord(pointA.x, pointA.y);
    const { px: bx, py: by } = transformCoord(pointB.x, pointB.y);

    ctx.save();
    ctx.strokeStyle = 'rgba(199, 139, 90, 0.4)';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 6]);
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
    ctx.restore();
  }

  function drawGhostPoint(x, y, type = 'interpolation') {
    ctx.save();
    const styles = type === 'edit'
      ? { fill: 'rgba(255, 255, 255, 0.08)', stroke: '#10b981', outer: '#34d399' }
      : { fill: 'rgba(255, 255, 255, 0.05)', stroke: '#f472b6', outer: '#facc15' };
    ctx.fillStyle = styles.fill;
    ctx.strokeStyle = styles.stroke;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 11, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.strokeStyle = styles.outer;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(x, y, 16, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }


  function drawSearchResultLabels() {
    ctx.save();
    ctx.font = '12px sans-serif';
    ctx.fillStyle = '#10b981';
    ctx.textAlign = 'center';

    searchResults.slice(0, 5).forEach((result, i) => {
      const coord = coords[result.idx];
      if (coord) {
        const { px: x, py: y } = transformCoord(coord.x, coord.y);
        
        // Draw rank label
        ctx.fillText(`#${i + 1}`, x, y - 15);
        
        // Draw similarity score
        ctx.font = '10px sans-serif';
        ctx.fillText(result.similarity.toFixed(2), x, y - 3);
        ctx.font = '12px sans-serif';
      }
    });

    ctx.restore();
  }

  function getCanvasCoordinates(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top
    };
  }

  function findNearestPoint(canvasX, canvasY) {
    let nearestIndex = null;
    let minDist = HOVER_RADIUS + 5;

    coords.forEach((coord, index) => {
      const { px, py } = transformCoord(coord.x, coord.y);
      const dist = Math.sqrt((px - canvasX) ** 2 + (py - canvasY) ** 2);

      if (dist < minDist) {
        minDist = dist;
        nearestIndex = index;
      }
    });

    return nearestIndex;
  }

  function handleMouseMove(event) {
    const { x, y } = getCanvasCoordinates(event);
    const nearestIndex = findNearestPoint(x, y);
    const selectingInterpolationPoint = (interpolationPointA && !interpolationPointB) || (interpolationPointB && !interpolationPointA);
    const restrictHover = selectingInterpolationPoint && !interpolationActive && !keyboardInterpolationMode;

    // "stick" to current sample unless a new one is close enough
    if (nearestIndex !== null && nearestIndex !== hoveredIndex) {
      if (restrictHover) {
        const sample = samples[nearestIndex];
        const coord = coords[nearestIndex];
        if (!getInterpolationEligibility(sample, coord)) {
          return;
        }
      }
      hoveredIndex = nearestIndex;
      const sample = samples[nearestIndex];
      const coord = coords[nearestIndex];
      dispatch('sampleHover', { sample, coord, index: nearestIndex });
      draw();
    }
  }

  function handleMouseLeave() {
    hoveredIndex = null;
    dispatch('sampleLeave');
    // Keep the last hovered sample active until a new one is hovered.
    // Still trigger a redraw to avoid stale tooltips if the window resizes.
    draw();
  }

  function handleClick(event) {
    const { x, y } = getCanvasCoordinates(event);
    const nearestIndex = findNearestPoint(x, y);

    if (nearestIndex !== null) {
      const sample = samples[nearestIndex];
      const coord = coords[nearestIndex];
      dispatch('sampleClick', { sample, coord, index: nearestIndex });
      draw();
    }
  }

  const clampCoord = (value) => Math.max(CLAMP_MIN, Math.min(CLAMP_MAX, value));
  const clampZoom = (value) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));
  const clampCenter = (value) => Math.max(0, Math.min(1, value));

  const fitCoord = (value, min, max) => {
    const denom = max - min;
    if (denom <= 1e-9) return 0.5;
    const normalized = (value - min) / denom;
    return clampCoord(normalized);
  };

  // Transform coordinates with optional zoom
  const transformCoord = (coordX, coordY) => {
    if (zoomActive) {
      // Normalize to [0,1]
      const normX = fitCoord(coordX, viewBounds.minX, viewBounds.maxX);
      const normY = fitCoord(coordY, viewBounds.minY, viewBounds.maxY);

      // Apply zoom and pan (center on zoomCenter)
      const px = ((normX - zoomCenterX) * zoomLevel + 0.5) * width;
      const py = ((normY - zoomCenterY) * zoomLevel + 0.5) * height;
      return { px, py };
    } else {
      // Standard view
      const px = fitCoord(coordX, viewBounds.minX, viewBounds.maxX) * width;
      const py = fitCoord(coordY, viewBounds.minY, viewBounds.maxY) * height;
      return { px, py };
    }
  };

  function zoomAround(canvasX, canvasY, nextZoomLevel) {
    const nextLevel = clampZoom(nextZoomLevel);
    if (Math.abs(nextLevel - zoomLevel) < 1e-4) return;

    const normX = ((canvasX / width - 0.5) / zoomLevel) + zoomCenterX;
    const normY = ((canvasY / height - 0.5) / zoomLevel) + zoomCenterY;

    targetZoomLevel = nextLevel;
    targetZoomCenterX = normX - (canvasX / width - 0.5) / nextLevel;
    targetZoomCenterY = normY - (canvasY / height - 0.5) / nextLevel;

    zoomActive = true;
    zoomEmphasis = false;

    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
    }
    animationFrame = requestAnimationFrame(animateZoom);
  }

  function handleWheel(event) {
    if (!width || !height) return;
    event.preventDefault();

    if (event.ctrlKey || event.metaKey) {
      const { x, y } = getCanvasCoordinates(event);
      const direction = event.deltaY > 0 ? -1 : 1;
      const factor = direction > 0 ? ZOOM_WHEEL_FACTOR : 1 / ZOOM_WHEEL_FACTOR;
      zoomAround(x, y, zoomLevel * factor);
      return;
    }

    const panX = event.deltaX / (width * zoomLevel);
    const panY = event.deltaY / (height * zoomLevel);

    targetZoomCenterX = clampCenter(zoomCenterX + panX);
    targetZoomCenterY = clampCenter(zoomCenterY + panY);
    zoomActive = true;
    zoomEmphasis = false;

    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
    }
    animationFrame = requestAnimationFrame(animateZoom);
  }

  function handleZoomKeys(event) {
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key;
    if (key !== '+' && key !== '=' && key !== '-' && key !== '_') return;
    event.preventDefault();

    const factor = (key === '+' || key === '=') ? ZOOM_KEY_FACTOR : 1 / ZOOM_KEY_FACTOR;
    zoomAround(width * 0.5, height * 0.5, zoomLevel * factor);
  }
</script>

<div class="visualization-container">
  <canvas
    bind:this={canvas}
    on:mousemove={handleMouseMove}
    on:mouseleave={handleMouseLeave}
    on:click={handleClick}
    on:wheel={handleWheel}
  ></canvas>

  <!-- Hover tooltip -->
  {#if hoveredSample}
    <div class="tooltip">
      <div class="tooltip-title">{hoveredSample.name}</div>
      <div class="tooltip-meta">
        <span class="badge">{hoveredSample.type}</span>
        <span class="coords">
          x: {coords[hoveredSample.index]?.x.toFixed(3)}, 
          y: {coords[hoveredSample.index]?.y.toFixed(3)}
        </span>
      </div>
    </div>
  {/if}

  <!-- Legend -->
  <!-- Legend removed -->

  <!-- Mode indicator -->
  <div class="mode-badge">
    {currentMode.toUpperCase()}
  </div>

  {#if showOverlays && !keyboardInterpolationMode && !interpolationActive}
    <div class="key-hints">
      <p><strong>Interpolation:</strong> hover a point, press <code>1</code>/<code>2</code> to set A/B, then <code>M</code> to start.</p>
      <p><strong>Clear:</strong> <code>Backspace</code>/<code>Delete</code> cancels edits or clears interpolation points.</p>
      <p><strong>Jump:</strong> <code>[</code>/<code>]</code> steps through special points.</p>
    </div>
  {/if}

  <!-- Stats -->
  <div class="stats">
    {coords.length} samples
    {#if virtualPoints.length > 0}
      + {virtualPoints.length} virtual
    {/if}
  </div>

  {#if editGhostLoading}
    <div class="ghost-loading">Updating edit ghost…</div>
  {/if}
</div>

<style>
  .visualization-container {
    width: 100%;
    height: 100%;
    position: relative;
    cursor: crosshair;
  }

  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }

  .tooltip {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: rgba(26, 26, 26, 0.95);
    border: 1px solid #333;
    border-radius: 8px;
    padding: 1rem;
    pointer-events: none;
    backdrop-filter: blur(10px);
    max-width: 300px;
  }

  .tooltip-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: var(--text-strong);
  }

  .tooltip-meta {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.875rem;
    color: var(--muted);
  }

  .badge {
    background: var(--accent);
    color: white;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
  }

  .coords {
    font-family: 'Courier New', monospace;
    font-size: 0.75rem;
  }

  .mode-badge {
    position: absolute;
    top: 1rem;
    left: 1rem;
    background: var(--accent);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-weight: 600;
    font-size: 0.875rem;
    letter-spacing: 0.05em;
  }

  .stats {
    position: absolute;
    bottom: 1rem;
    right: 1rem;
    background: rgba(36, 28, 21, 0.95);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    color: var(--muted);
    backdrop-filter: blur(10px);
  }

  .key-hints {
    position: absolute;
    right: 1rem;
    bottom: 4.4rem;
    max-width: min(360px, 70vw);
    background: rgba(36, 28, 21, 0.88);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    font-size: 0.78rem;
    color: var(--text);
    line-height: 1.35;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    pointer-events: none;
  }

  .key-hints p {
    margin: 0 0 0.35rem;
  }

  .key-hints p:last-child {
    margin-bottom: 0;
  }

  .key-hints code {
    font-family: "Courier New", monospace;
    color: var(--text-strong);
  }

  .ghost-loading {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.5);
    color: #6ee7b7;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }
</style>
