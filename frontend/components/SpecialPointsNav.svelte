<script>
  export let specialPoints = [];
  export let specialPointsIndex = -1;
  export let showSpecialPointsNav = false;
  export let onToggle = () => {};
  export let onPrev = () => {};
  export let onNext = () => {};
</script>

{#if specialPoints.length > 0}
  <div class="special-points-nav" class:expanded={showSpecialPointsNav}>
    <button
      class="nav-toggle"
      on:click={onToggle}
      title="Navigate special points (interpolated/renamed)"
    >
      $ {specialPoints.length}
    </button>

    {#if showSpecialPointsNav}
      <div class="nav-controls">
        <button class="nav-btn" on:click={onPrev} title="Previous">
          ◀
        </button>
        <div class="nav-info">
          <span class="nav-counter">{specialPointsIndex + 1} / {specialPoints.length}</span>
          <span class="nav-label">
            {specialPoints[specialPointsIndex]?.customName || specialPoints[specialPointsIndex]?.name || 'Unnamed'}
          </span>
        </div>
        <button class="nav-btn" on:click={onNext} title="Next">
          ▶
        </button>
      </div>
      <div class="nav-hint">Use <code>[</code> / <code>]</code> to jump</div>
    {/if}
  </div>
{/if}

<style>
  .special-points-nav {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid #2a2a2a;
  }

  .nav-toggle {
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    border: 1px solid #444;
    background: linear-gradient(135deg, rgba(251, 191, 36, 0.15), rgba(245, 158, 11, 0.1));
    color: #fbbf24;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.875rem;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .nav-toggle:hover {
    background: linear-gradient(135deg, rgba(251, 191, 36, 0.25), rgba(245, 158, 11, 0.15));
    border-color: #fbbf24;
    transform: translateY(-1px);
  }

  .nav-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(10, 10, 10, 0.6);
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 0.5rem;
  }

  .nav-btn {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 6px;
    color: #fbbf24;
    padding: 0.4rem 0.75rem;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
    min-width: 2.5rem;
  }

  .nav-btn:hover {
    background: #252525;
    border-color: #fbbf24;
    transform: scale(1.05);
  }

  .nav-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
  }

  .nav-counter {
    font-size: 0.75rem;
    color: #888;
    font-family: 'Courier New', monospace;
  }

  .nav-label {
    font-size: 0.85rem;
    color: #e5e5e5;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nav-hint {
    font-size: 0.75rem;
    color: #8b8b8b;
  }

  .nav-hint code {
    font-family: "Courier New", monospace;
    color: #f5f5f5;
  }
</style>
