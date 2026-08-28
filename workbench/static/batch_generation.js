// batch_generation.js — C13-0 拆分：批量生成 / 并发控制 / 推荐动作分发（由 app.js 原样迁移）

async function runAction(button, task) {
  if (button?.dataset.busy === "true") return;
  setBusy(button, true);
  updateButtons(Boolean(activeProject));
  try {
    await task();
  } catch (error) {
    appendLog(error.message || String(error));
    surfaceActionError(error);
  } finally {
    setBusy(button, false);
    updateButtons(Boolean(activeProject));
  }
}

function surfaceActionError(error, fallback = "操作没有完成，请重试。") {
  const message = userFacingGenerationError(error?.message || error || "");
  setState(message || fallback, "error");
}

function handleResize() {
  if (previewState.mode === "fit" && previewState.hasContent) {
    applyPreviewScale();
  }
}

async function autoGenerateCurrentProject() {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  autoGenerationGlobalBusy = true;
  refreshAutoGenerationRunningFlag();
  resetLog("正在自动生成页面...");
  setPreviewBusy("正在调用配置的模型生成页面...");
  startAutoGenerationPolling();
  setState("自动生成页面", "running");
  updateButtons(false);
  try {
    const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/auto-generate`, { method: "POST" });
    appendLog(commandSummary("自动生成页面", response));
    if (!response.ok) {
      setState("自动生成失败", "error");
      throw new Error(response.message || "自动生成页面失败。");
    }
    await recordTaskEvent("auto_generate", response.data || {});
    await loadStatus();
    await refreshCurrentPreview();
    const generatedSlides = Array.isArray(response.data?.generated_slides) ? response.data.generated_slides : [];
    if (generatedSlides.length) {
      setPreviewBusy("正在刷新...");
    } else {
      setPreviewBusy("没有生成新的页面，请检查当前页状态。");
    }
    for (const slideId of generatedSlides) {
      const qaSlideId = Number(slideId);
      if (!Number.isFinite(qaSlideId)) continue;
      setPreviewBusy(`第 ${qaSlideId} 页已生成，正在自动检查...`);
      const qaResponse = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${qaSlideId}/qa`, { method: "POST" });
      appendLog(commandSummary(`第 ${qaSlideId} 页自动检查`, qaResponse));
      await recordTaskEvent("qa_slide", { slide_id: qaSlideId, result: qaResponse.ok ? "ok" : "failed", source: "auto_generate" });
      await loadStatus();
    }
    await loadQaReport();
    if (generatedSlides.length) {
      setState("已生成", "ready");
    } else {
      setState("等待页面生成", "idle");
    }
  } finally {
    autoGenerationGlobalBusy = false;
    refreshAutoGenerationRunningFlag();
    if (!autoGenerationRunning) {
      stopAutoGenerationPolling();
      setPreviewBusy("", false);
    }
    updateButtons(Boolean(activeProject));
  }
}

function batchGenerationPauseReason(failedIds, consecutiveFailures, totalCount) {
  const failedCount = Array.isArray(failedIds) ? failedIds.length : 0;
  const total = Number(totalCount || 0);
  if (consecutiveFailures >= BATCH_GENERATION_CONSECUTIVE_FAILURE_LIMIT) {
    return `连续 ${consecutiveFailures} 页生成失败，已暂停批量生成。`;
  }
  if (failedCount >= BATCH_GENERATION_TOTAL_FAILURE_LIMIT) {
    return `已有 ${failedCount} 页生成失败，已暂停批量生成。`;
  }
  if (total > 0 && failedCount >= 3 && failedCount / total >= BATCH_GENERATION_FAILURE_RATIO_LIMIT) {
    return `失败页占比超过 10%，已暂停批量生成。`;
  }
  return "";
}

async function runWithConcurrency(items, limit, worker, options = {}) {
  const queue = Array.isArray(items) ? items.slice() : [];
  const workerCount = Math.max(1, Math.min(Number(limit || 1), queue.length || 1));
  const shouldContinue = typeof options.shouldContinue === "function" ? options.shouldContinue : () => true;
  const runners = Array.from({ length: workerCount }, async () => {
    while (queue.length && shouldContinue()) {
      const item = queue.shift();
      if (typeof item === "undefined") break;
      await worker(item);
    }
  });
  await Promise.all(runners);
}

async function autoGenerateMissingPagesBatch() {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  if (!isApiAutoMode()) throw new Error("仅自动生成模式支持批量生成未完成页。");
  if (latestStatus?.generation?.api_key_configured === false) {
    throw new Error("当前服务还没读取到自动生成 API Key，请在服务器 .env 或 Windows 环境变量中配置并重启。");
  }

  await loadStatus();
  const candidates = missingSlidesWithPrompt(latestStatus);
  if (!candidates.length) {
    appendLog("没有可批量生成的未完成页（可能都已生成，或缺少页面提示词）。");
    return;
  }
  const candidateIds = candidates
    .map((item) => Number(item.slide_id || 0))
    .filter((id, index, ids) => Number.isFinite(id) && id > 0 && ids.indexOf(id) === index);
  autoGenerationGlobalBusy = true;
  autoGenerationTargetSlide = null;
  batchGenerationQueuedSlides = new Set(candidateIds);
  refreshAutoGenerationRunningFlag();
  renderSlideListWithReview(latestStatus?.slides || []);
  setPreviewBusy(`正在生成未完成页（共 ${candidateIds.length} 页，最多同时 ${BATCH_GENERATION_MAX_CONCURRENCY} 页）...`);
  setState("正在生成未完成页", "running");
  startAutoGenerationPolling();
  updateButtons(false);

  const failedIds = [];
  let consecutiveFailures = 0;
  let batchPausedReason = "";
  try {
    await runWithConcurrency(candidateIds, BATCH_GENERATION_MAX_CONCURRENCY, async (slideId) => {
      batchGenerationQueuedSlides.delete(slideId);
      batchGenerationActiveSlides.add(slideId);
      renderSlideListWithReview(latestStatus?.slides || []);
      const slide = slideStateById(slideId) || {};
      startSlowGenerationHints(slideId);
      let response;
      try {
        response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${slideId}/auto-generate`, {
          method: "POST",
          body: JSON.stringify({
            page_type: normalizeWorkbenchPageType(slide.page_type),
            content_handling: normalizeContentHandling(slide.content_handling),
            page_style: normalizePageStyle(slide.page_style),
            title: String(slide.title || ""),
            prompt: String(slide.prompt || ""),
          }),
        });
      } finally {
        batchGenerationActiveSlides.delete(slideId);
        clearSlowGenerationHints(slideId);
        renderSlideListWithReview(latestStatus?.slides || []);
      }
      appendLog(commandSummary(`第 ${slideId} 页批量生成`, response));
      await loadStatus();
      if (Number(selectedSlide) === slideId) await refreshCurrentPreview();
      if (!response.ok) {
        failedIds.push(slideId);
        consecutiveFailures += 1;
        batchPausedReason = batchPausedReason || batchGenerationPauseReason(failedIds, consecutiveFailures, candidateIds.length);
      } else {
        consecutiveFailures = 0;
      }
    }, {
      shouldContinue: () => !batchPausedReason,
    });
    await recordTaskEvent("auto_generate_batch", {
      total: candidateIds.length,
      failed: failedIds.length,
      failed_slides: failedIds,
      concurrency: BATCH_GENERATION_MAX_CONCURRENCY,
      paused_reason: batchPausedReason,
    });
    await loadStatus();
    if (!batchPausedReason && uncheckedGeneratedSlides(latestStatus).length) {
      await qaUncheckedGeneratedSlides();
    } else {
      await loadQaReport();
    }
    if (batchPausedReason) {
      appendLog(batchPausedReason);
      setState("批量生成已暂停", "error");
    } else if (failedIds.length) {
      setState("批量生成部分失败", "error");
    } else {
      setState("批量生成完成", "ready");
    }
  } finally {
    autoGenerationGlobalBusy = false;
    autoGenerationTargetSlide = null;
    batchGenerationQueuedSlides = new Set();
    batchGenerationActiveSlides.clear();
    refreshAutoGenerationRunningFlag();
    renderSlideListWithReview(latestStatus?.slides || []);
    if (!autoGenerationRunning) {
      stopAutoGenerationPolling();
      setPreviewBusy("", false);
    }
    updateButtons(Boolean(activeProject));
  }
}

async function qaUncheckedGeneratedSlides() {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  const slides = uncheckedGeneratedSlides(latestStatus);
  if (!slides.length) {
    await loadStatus();
    return;
  }
  autoCheckRunning = true;
  setPreviewBusy("正在自动检查已生成页面...");
  setState("自动检查页面", "running");
  renderNextAction(latestStatus);
  updateButtons(false);
  try {
    for (const slide of slides) {
      const qaSlideId = Number(slide.slide_id || 0);
      if (!Number.isFinite(qaSlideId) || qaSlideId <= 0) continue;
      setPreviewBusy(`第 ${qaSlideId} 页正在自动检查...`);
      const qaResponse = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${qaSlideId}/qa`, {
        method: "POST",
      });
      appendLog(commandSummary(`第 ${qaSlideId} 页自动检查`, qaResponse));
      await recordTaskEvent("qa_slide", { slide_id: qaSlideId, result: qaResponse.ok ? "ok" : "failed", source: "auto_check" });
      await loadStatus();
      if (Number(selectedSlide) === qaSlideId) await refreshCurrentPreview();
    }
    await loadQaReport();
    setState("页面已检查", "ready");
  } finally {
    autoCheckRunning = false;
    setPreviewBusy("", false);
    updateButtons(Boolean(activeProject));
    renderNextAction(latestStatus);
  }
}

async function executeRecommendedAction() {
  const action = nextActionButton?.dataset.action || "refresh_status";
  if (action === "create_task") {
    await createCodexTask();
    return;
  }
  if (action === "auto_generate") {
    const pending = missingSlidesWithPrompt(latestStatus);
    if (pending.length > 1 && isApiAutoMode()) {
      await autoGenerateMissingPagesBatch();
      return;
    }
    await autoGenerateCurrentProject();
    return;
  }
  if (action === "auto_check") {
    await qaUncheckedGeneratedSlides();
    return;
  }
  if (action === "edit_page_prompt") {
    const slide = Number(latestStatus?.recommended_next_action?.slide_id || selectedSlide || 1);
    await focusSlideContext(slide, { focusPrompt: true });
    appendLog(`请先填写第 ${selectedSlide} 页提示词，再生成本页。`);
    updateButtons(Boolean(activeProject));
    return;
  }
  if (action === "qa_slide") {
    await qaCurrentSlide();
    return;
  }
  if (action === "repair_delivery_blocker") {
    await repairDeliveryBlocker();
    return;
  }
  if (action === "repair_export_failure") {
    await repairDeliveryBlocker();
    return;
  }
  if (action === "auto_optimize_slide") {
    const slide = Number(latestStatus?.recommended_next_action?.slide_id || firstUnreadySlide(latestStatus));
    await focusSlideContext(slide, { scroll: true });
    await autoGenerateCurrentSlide();
    return;
  }
  if (action === "repair_slide") {
    const slide = Number(latestStatus?.recommended_next_action?.slide_id || firstUnreadySlide(latestStatus));
    await focusSlideContext(slide, { scroll: true });
    if (isApiAutoMode()) {
      await autoGenerateCurrentSlide();
      return;
    }
    await repairCurrentSlide();
    return;
  }
  if (action === "repair_budget") {
    const slide = Number(latestStatus?.recommended_next_action?.slide_id || firstUnreadySlide(latestStatus));
    await focusSlideContext(slide, { scroll: true });
    await repairCurrentSlide();
    return;
  }
  if (action === "export_pptx") {
    await exportCurrentDeck();
    return;
  }
  if (action === "export_current_slide") {
    const slide = Number(latestStatus?.recommended_next_action?.slide_id || selectedSlide || 1);
    await focusSlideContext(slide, { scroll: true });
    await exportCurrentSlide();
    return;
  }
  if (action === "download_pptx") {
    downloadCurrentDeck();
    return;
  }
  if (action === "fresh_release_safe") {
    await runFreshFinalize("release-safe");
    return;
  }
  if (action === "manual_review") {
    await openQaEvidencePanel();
    appendLog("已打开。");
    return;
  }
  await loadStatus();
  await refreshCurrentPreview();
}
