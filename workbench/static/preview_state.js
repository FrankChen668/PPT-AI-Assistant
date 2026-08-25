(function () {
  const PREVIEW_BASE_WIDTH = 1280;
  const PREVIEW_BASE_HEIGHT = 720;
  const DEFAULT_ZOOM_OPTIONS = [0.75, 1, 1.25, 1.5, 2];

  function normalizedZoomOptions(options) {
    const values = Array.isArray(options) && options.length ? options : DEFAULT_ZOOM_OPTIONS;
    return values.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
  }

  function closestScale(scale, options) {
    const sorted = normalizedZoomOptions(options);
    return sorted.reduce(
      (closest, value) => (Math.abs(value - scale) < Math.abs(closest - scale) ? value : closest),
      sorted[0] || scale,
    );
  }

  function computeFitScale(width, height, padding = 28) {
    const availableWidth = Math.max(240, Number(width || 0) - padding);
    const availableHeight = Math.max(160, Number(height || 0) - padding);
    const scale = Math.min(availableWidth / PREVIEW_BASE_WIDTH, availableHeight / PREVIEW_BASE_HEIGHT);
    return Math.max(0.2, Number(scale.toFixed(4)));
  }

  function busyMessage(message) {
    return message || "正在处理...";
  }

  function createPreviewState() {
    let mode = "fit";
    let manualScale = 1;
    let hasContent = false;

    return {
      get mode() {
        return mode;
      },
      get manualScale() {
        return manualScale;
      },
      get hasContent() {
        return hasContent;
      },
      loadPrefs(saved, options) {
        if (saved?.mode === "manual") mode = "manual";
        else mode = "fit";
        const value = Number(saved?.scale);
        manualScale = Number.isFinite(value) && value > 0 ? value : 1;
        const sorted = normalizedZoomOptions(options);
        if (!sorted.includes(manualScale)) manualScale = 1;
        return { mode, manualScale };
      },
      savePrefs() {
        return { mode, scale: manualScale };
      },
      setHasContent(value) {
        hasContent = Boolean(value);
      },
      setMode(nextMode, scale = manualScale) {
        mode = nextMode === "manual" ? "manual" : "fit";
        if (mode === "manual") manualScale = scale;
        return { mode, manualScale };
      },
      currentScale(fitScale) {
        return mode === "fit" ? fitScale : manualScale;
      },
      closestScale(scale, options) {
        return closestScale(scale, options);
      },
      nextZoomScale(direction, current, options) {
        const sorted = normalizedZoomOptions(options);
        if (!sorted.length) return manualScale;
        const anchor = closestScale(current, sorted);
        let index = sorted.findIndex((value) => value === anchor);
        if (index < 0) index = sorted.findIndex((value) => value >= current);
        if (index < 0) index = sorted.length - 1;
        const nextIndex = Math.max(0, Math.min(sorted.length - 1, index + direction));
        return sorted[nextIndex];
      },
    };
  }

  window.WorkbenchPreviewState = {
    PREVIEW_BASE_WIDTH,
    PREVIEW_BASE_HEIGHT,
    createPreviewState,
    computeFitScale,
    busyMessage,
  };
})();
