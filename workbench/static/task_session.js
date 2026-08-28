// task_session.js — C13-0 拆分：任务会话 / 生成状态 / 预览 busy（由 app.js 原样迁移）

function pushToast(text, level = "info") {
  const message = String(text ?? "").trim();
  if (!message || !toastHost) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${level}`;
  toast.setAttribute("role", level === "error" ? "alert" : "status");
  toast.textContent = message;
  toastHost.appendChild(toast);
  const linger = level === "error" ? 6000 : 3600;
  window.setTimeout(() => {
    toast.classList.add("toast-leaving");
    window.setTimeout(() => toast.remove(), 240);
  }, linger);
}

function appendLog(text) {
  const level = String(text ?? "").includes("失败") ? "error" : "info";
  pushToast(text, level);
}

function resetLog(text) {
  pushToast(text, "info");
}

function isApiAutoMode() {
  return true;
}

function currentSlideNeedsIntervention(slideId = selectedSlide) {
  const current = slideStateById(slideId);
  return Boolean(current && (current.qa_status === "failed" || current.status === "qa_failed"));
}

function shouldAutoRepairCurrentSlide(slideId = selectedSlide) {
  const quality = latestStatus?.user_quality || {};
  if (currentSlideNeedsIntervention(slideId) && quality.should_auto_repair === false) return false;
  return currentSlideNeedsIntervention(slideId);
}

function slideNeedsHumanIntervention(slideId) {
  return humanInterventionSlides.has(Number(slideId || 0));
}

function updateGenerationModeUi() {
  const auto = isApiAutoMode();
  appShell?.classList.toggle("auto-generation-mode", auto);
  taskDetailShell?.classList.toggle("auto-generation-mode", auto);
  if (autoGeneratePage) autoGeneratePage.classList.toggle("hidden", !auto);
  if (repairCurrentPage) repairCurrentPage.classList.toggle("hidden", auto);
  if (repairSlide) repairSlide.classList.toggle("hidden", auto);
}

function renderPreviewBusy(message) {
  const copy = document.createElement("span");
  copy.className = "preview-loading-copy";
  copy.textContent = window.WorkbenchPreviewState.busyMessage(message);

  const steps = document.createElement("span");
  steps.className = "preview-loading-steps";
  steps.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    steps.appendChild(dot);
  }

  const scan = document.createElement("span");
  scan.className = "preview-loading-scan";
  scan.setAttribute("aria-hidden", "true");

  previewLoading.replaceChildren(scan, copy, steps);
}

function setPreviewBusy(message, busy = true) {
  if (!previewLoading) return;
  if (busy) previewHint?.classList.add("hidden");
  if (busy) {
    renderPreviewBusy(message);
  } else {
    previewLoading.replaceChildren();
    previewLoading.textContent = "";
  }
  previewLoading.classList.toggle("hidden", !busy);
  previewLoading.classList.toggle("active", Boolean(busy));
}

function clearPreviewLoadFallback() {
  if (!previewLoadFallbackTimer) return;
  window.clearTimeout(previewLoadFallbackTimer);
  previewLoadFallbackTimer = null;
  previewLoadFallbackSlide = 0;
}

function hideLoadedPreviewBusy(slideId, force = false) {
  if (Number(selectedSlide) !== Number(slideId)) return;
  if (force || (!autoGenerationRunning && !autoCheckRunning)) setPreviewBusy("", false);
}

function schedulePreviewLoadFallback(slideId) {
  clearPreviewLoadFallback();
  previewLoadFallbackSlide = Number(slideId);
  previewLoadFallbackTimer = window.setTimeout(() => {
    const fallbackSlide = previewLoadFallbackSlide;
    previewLoadFallbackTimer = null;
    previewLoadFallbackSlide = 0;
    hideLoadedPreviewBusy(fallbackSlide, true);
  }, 1600);
}

function showPreviewLoadFailure(message = "预览加载失败，请刷新预览或重新生成本页。") {
  previewState.setHasContent(false);
  previewHint.textContent = message;
  previewHint.classList.remove("hidden");
  setPreviewBusy("", false);
  clearPreviewLoadFallback();
  renderPreviewRetryState();
}

function verifyLoadedPreviewFrame() {
  const expectedProject = svgPreview.dataset.project || "";
  const expectedSlide = svgPreview.dataset.slide || "";
  let doc = null;
  try {
    doc = svgPreview.contentDocument;
  } catch {
    showPreviewLoadFailure("预览加载失败：无法读取预览内容。");
    return false;
  }
  const body = doc?.body;
  const actualProject = body?.dataset?.project || "";
  const actualSlide = body?.dataset?.slide || "";
  const status = body?.dataset?.previewStatus || "";
  const hasSvg = Boolean(doc?.querySelector("svg"));
  if (status !== "ready" || !hasSvg) {
    showPreviewLoadFailure("预览加载失败：页面没有正常显示。");
    return false;
  }
  if (expectedProject && actualProject !== expectedProject) {
    showPreviewLoadFailure("预览加载失败：当前预览不是这个任务。");
    return false;
  }
  if (expectedSlide && actualSlide !== expectedSlide) {
    showPreviewLoadFailure("预览加载失败：当前预览不是这一页。");
    return false;
  }
  return true;
}

function renderPreviewRetryState() {
  if (!previewRetryBox || !previewRetryMessage || !previewRetryButton) return;
  const current = selectedSlideState();
  const generationFailed = Boolean(current && slideGenerationError(current) && current.status !== "generating");
  const canRetry = Boolean(activeProject && current && isApiAutoMode());
  const show = Boolean(generationFailed && canRetry);
  previewRetryBox.classList.toggle("hidden", !show);
  previewRetryButton.disabled = !show;
  if (!show) return;
  const cleanGenerationError = compactSentenceEnd(slideGenerationError(current));
  previewRetryMessage.textContent = `生成失败：${cleanGenerationError}。请重新生成本页。`;
}

function refreshAutoGenerationRunningFlag() {
  autoGenerationRunning = autoGenerationGlobalBusy || autoGenerationSlideTasks.size > 0;
  if (!autoGenerationRunning) autoGenerationTargetSlide = null;
}

function hasSlideGenerationInFlight(slideId) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return false;
  return autoGenerationSlideTasks.has(id);
}

function slideIsQueuedForGeneration(slideId) {
  return batchGenerationQueuedSlides.has(Number(slideId)) || manualGenerationQueuedSlides.has(Number(slideId));
}

function slideIsActiveGeneration(slideId) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return false;
  return batchGenerationActiveSlides.has(id) || manualGenerationActiveSlides.has(id);
}

async function acquireManualGenerationTurn(slideId) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return false;
  if (manualGenerationActiveCount < MANUAL_GENERATION_MAX_CONCURRENCY) {
    manualGenerationActiveSlides.add(id);
    manualGenerationActiveCount = manualGenerationActiveSlides.size;
    manualGenerationQueuedSlides.delete(id);
    renderSlideListWithReview(latestStatus?.slides || []);
    renderPageStream(latestStatus?.slides || []);
    updateButtons(Boolean(activeProject));
    return true;
  }
  manualGenerationQueuedSlides.add(id);
  renderSlideListWithReview(latestStatus?.slides || []);
  renderPageStream(latestStatus?.slides || []);
  updateButtons(Boolean(activeProject));
  return new Promise((resolve) => {
    manualGenerationQueue.push({ slideId: id, resolve });
  });
}

function releaseManualGenerationTurn(slideId = 0) {
  const releasedId = Number(slideId);
  if (Number.isFinite(releasedId) && releasedId >= 1) {
    manualGenerationActiveSlides.delete(releasedId);
    manualGenerationQueuedSlides.delete(releasedId);
    for (let index = manualGenerationQueue.length - 1; index >= 0; index -= 1) {
      if (Number(manualGenerationQueue[index]?.slideId || 0) === releasedId) manualGenerationQueue.splice(index, 1);
    }
  } else if (manualGenerationActiveSlides.size) {
    const firstActiveSlide = manualGenerationActiveSlides.values().next().value;
    manualGenerationActiveSlides.delete(firstActiveSlide);
  }
  manualGenerationActiveCount = manualGenerationActiveSlides.size;
  while (manualGenerationQueue.length && manualGenerationActiveCount < MANUAL_GENERATION_MAX_CONCURRENCY) {
    const next = manualGenerationQueue.shift();
    const nextSlideId = Number(next?.slideId || 0);
    const resolve = next?.resolve;
    if (!Number.isFinite(nextSlideId) || nextSlideId < 1 || !autoGenerationSlideTasks.has(nextSlideId)) {
      manualGenerationQueuedSlides.delete(nextSlideId);
      if (resolve) resolve(false);
      continue;
    }
    manualGenerationQueuedSlides.delete(nextSlideId);
    manualGenerationActiveSlides.add(nextSlideId);
    manualGenerationActiveCount = manualGenerationActiveSlides.size;
    if (resolve) resolve(true);
  }
  renderSlideListWithReview(latestStatus?.slides || []);
  renderPageStream(latestStatus?.slides || []);
  updateButtons(Boolean(activeProject));
}

function clearSlowGenerationHints(slideId) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return;
  const timers = slowGenerationHintTimers.get(id) || [];
  timers.forEach((timer) => window.clearTimeout(timer));
  slowGenerationHintTimers.delete(id);
}

function startSlowGenerationHints(slideId) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return;
  clearSlowGenerationHints(id);
  const showHint = (message) => {
    const stillGenerating = hasSlideGenerationInFlight(id) || (autoGenerationGlobalBusy && autoGenerationRunning);
    if (!stillGenerating) return;
    if (Number(selectedSlide) === id) setPreviewBusy(message);
    setState(message, "running");
  };
  slowGenerationHintTimers.set(id, [
    window.setTimeout(() => showHint("模型响应较慢，仍在生成中。"), SLOW_GENERATION_HINT_MS),
    window.setTimeout(() => showHint("生成时间较长，可以继续等待，也可以稍后重试本页。"), VERY_SLOW_GENERATION_HINT_MS),
  ]);
}

function markSlideGenerationStarted(slideId, taskPromise) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return;
  autoGenerationSlideTasks.set(id, taskPromise);
  autoGenerationTargetSlide = id;
  refreshAutoGenerationRunningFlag();
  renderSlideListWithReview(latestStatus?.slides || []);
  renderPageStream(latestStatus?.slides || []);
  updateButtons(Boolean(activeProject));
}

function markSlideGenerationFinished(slideId, taskPromise) {
  const id = Number(slideId);
  if (!Number.isFinite(id) || id < 1) return;
  const current = autoGenerationSlideTasks.get(id);
  if (current && current === taskPromise) autoGenerationSlideTasks.delete(id);
  refreshAutoGenerationRunningFlag();
}

function slideHasGeneratedOutput(slide) {
  if (!slide || typeof slide !== "object") return false;
  if (slide.has_svg) return true;
  const status = String(slide.status || "");
  const svgStatus = String(slide.svg_status || "");
  const qaStatus = String(slide.qa_status || "");
  return (
    svgStatus === "svg_authored" ||
    svgStatus === "svg_ready" ||
    status === "svg_ready" ||
    status === "qa_passed" ||
    status === "qa_failed" ||
    status === "placeholder_svg" ||
    qaStatus === "passed" ||
    qaStatus === "failed"
  );
}

function serverSlideStillGenerating(slide) {
  if (!slide || typeof slide !== "object") return true;
  if (slideHasGeneratedOutput(slide)) return false;
  const status = String(slide.status || "");
  if (status === "failed") return false;
  return true;
}

function reconcileGenerationTasksWithServer(slides = []) {
  if (!Array.isArray(slides) || !autoGenerationSlideTasks.size) return;
  let changed = false;
  slides.forEach((slide) => {
    const slideId = Number(slide?.slide_id || 0);
    if (!Number.isFinite(slideId) || slideId < 1 || !autoGenerationSlideTasks.has(slideId)) return;
    if (manualGenerationQueuedSlides.has(slideId) && !slideHasGeneratedOutput(slide)) return;
    if (serverSlideStillGenerating(slide)) return;
    autoGenerationSlideTasks.delete(slideId);
    manualGenerationQueuedSlides.delete(slideId);
    clearSlowGenerationHints(slideId);
    releaseManualGenerationTurn(slideId);
    changed = true;
  });
  if (changed) refreshAutoGenerationRunningFlag();
}

function shouldShowPreviewBusy(slideId = selectedSlide) {
  if (!autoGenerationRunning && !autoCheckRunning) return false;
  if (autoGenerationGlobalBusy) return true;
  if (autoCheckRunning) return true;
  return hasSlideGenerationInFlight(slideId);
}

function stopAutoGenerationPolling() {
  if (autoGenerationPollTimer) {
    clearInterval(autoGenerationPollTimer);
    autoGenerationPollTimer = null;
  }
}

function startAutoGenerationPolling() {
  stopAutoGenerationPolling();
  autoGenerationPollTimer = setInterval(async () => {
    if (!activeProject || !autoGenerationRunning) return;
    try {
      await loadStatus({ lite: true });
      renderSlideListWithReview(latestStatus?.slides || []);
      const current = selectedSlideState();
      const pendingMessage = slideGenerationPendingMessageDetailed(current, selectedSlide);
      if (pendingMessage && shouldShowPreviewBusy(selectedSlide)) {
        setPreviewBusy(pendingMessage);
      }
      if (slideIsDisplayable(current) && shouldShowPreviewBusy(selectedSlide)) {
        await refreshCurrentPreview();
      }
    } catch (error) {
      appendLog(`自动生成进度刷新失败：${error.message || String(error)}`);
    }
  }, 1800);
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.dataset.busy = busy ? "true" : "false";
}

function setState(text, state) {
  projectState.textContent = text;
  projectState.className = `state-pill ${state}`;
}

function commandSummary(label, response) {
  const data = response.data || {};
  if (typeof data.returncode === "number") {
    const result = data.finalize_status === "review_required" ? "生成完成，需复核" : data.returncode === 0 ? "通过" : "失败";
    const output = [data.stdout, data.stderr].filter(Boolean).join("\n").trim();
    return `${label}：${result}${output ? `\n${output}` : ""}`;
  }
  const message = userFacingGenerationError(response.message || "");
  return `${label}：${response.ok ? "完成" : "失败"}${message ? ` - ${message}` : ""}`;
}

function setPanelExpanded(panel, toggle, expanded, persist = true) {
  if (!panel || !toggle) return;
  if (expanded && panel.classList.contains("utility-panel")) {
    utilityPanels.forEach((item) => {
      if (item !== panel) {
        item.classList.remove("expanded");
        item.classList.add("collapsed");
      }
    });
    utilityToggles.forEach((item) => {
      if (item !== toggle) {
        item.classList.remove("active");
        item.setAttribute("aria-expanded", "false");
      }
    });
  }
  panel.classList.toggle("expanded", expanded);
  panel.classList.toggle("collapsed", !expanded);
  toggle.classList.toggle("active", expanded);
  toggle.setAttribute("aria-expanded", String(expanded));
  if (persist) saveUiPrefs();
}

function setSetupCollapsed(collapsed, persist = true) {
  appShell.classList.toggle("setup-collapsed", collapsed);
  if (setupContent) {
    setupContent.classList.toggle("hidden", collapsed);
    setupContent.setAttribute("aria-hidden", String(collapsed));
  }
  if (setupCollapsedSummary) {
    setupCollapsedSummary.classList.toggle("hidden", !collapsed);
    setupCollapsedSummary.setAttribute("aria-hidden", String(!collapsed));
  }
  if (toggleSetupPanel) {
    toggleSetupPanel.textContent = collapsed ? "展开设置" : "收起设置";
    toggleSetupPanel.setAttribute("aria-expanded", String(!collapsed));
  }
  if (persist) saveUiPrefs();
}

function updateCollapsedSummary() {
  if (!collapsedProjectName) return;
  collapsedProjectName.textContent = userFacingTaskTitle(
    activeProjectTitle || latestStatus?.task_title || activeProject,
    "未创建项目",
  );
}

