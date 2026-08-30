// generation.js — C13-0 拆分：单页生成 / QA / 修复 / 导出 / 修订（由 app.js 原样迁移）

async function generatePacketForSlide(slideId) {
  const slideNo = slideNoById(slideId);
  const response = await api(
    `/api/projects/${encodeURIComponent(activeProject)}/slides/${slideId}/executor-packet`,
    {
      method: "POST",
      body: JSON.stringify({ markdown: true }),
    },
  );
  appendLog(commandSummary(`第 ${slideNo} 页 Generate packet`, response));
  if (response.ok) {
    const jsonPath = response.data?.packet_json_path || "";
    const mdPath = response.data?.packet_markdown_path || "";
    const verify = response.data?.verify_command || "";
    appendLog(`Packet ready: ${jsonPath}${mdPath ? ` | ${mdPath}` : ""}`);
    if (verify) appendLog(`Recommended verify: ${verify}`);
  }
  await loadStatus();
}

async function regenerateCurrentSlide() {
  await autoGenerateCurrentSlide();
}

async function qaCurrentSlide(slideId = selectedSlide) {
  const targetSlide = Number(slideId);
  const targetSlideNo = slideNoById(targetSlide);
  appendLog(`开始单页检查：第 ${targetSlideNo} 页`);
  if (Number(selectedSlide) === targetSlide) setPreviewBusy(`正在完成第 ${targetSlideNo} 页...`);
  setState("正在完成本页", "running");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${targetSlide}/qa`, { method: "POST" });
  appendLog(commandSummary(`第 ${targetSlideNo} 页 QA`, response));
  await recordTaskEvent("qa_slide", { slide_id: targetSlide, result: response.ok ? "ok" : "failed" });
  await loadStatus();
  if (Number(selectedSlide) === targetSlide) await refreshCurrentPreview();
  await loadQaReport();
  if (response.ok) {
    setState("已生成", "ready");
  } else {
    setState("生成失败", "error");
  }
  if (Number(selectedSlide) === targetSlide) setPreviewBusy("", false);
}

async function autoGenerateCurrentSlide(options = {}) {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  if (latestStatus?.generation?.api_key_configured === false) {
    throw new Error("当前服务还没有读到自动生成 API Key。请先配置本地密钥并重启工作台服务。");
  }
  // Legacy contract marker for frontend state tests: const targetSlide = Number(selectedSlide)
  const waitForCompletion = options?.wait_for_completion !== false;
  const targetSlide = Number(options?.slide_id || selectedSlide);
  const existingTask = autoGenerationSlideTasks.get(targetSlide);
  if (existingTask) {
    appendLog(`第 ${slideNoById(targetSlide)} 页正在生成，已加入队列。`);
    if (waitForCompletion) await existingTask;
    return;
  }
  let targetInitialState = slideStateById(targetSlide);
  const generateBlocker = currentPageGenerateBlocker(targetInitialState, targetSlide);
  if (generateBlocker) {
    appendLog(generateBlocker);
    if (Number(selectedSlide) === targetSlide && currentPageActionHint) currentPageActionHint.textContent = generateBlocker;
    throw new Error(generateBlocker);
  }
  const targetPageType = normalizeWorkbenchPageType(currentPageType?.value || targetInitialState?.page_type);
  const targetContentHandling = normalizeContentHandling(
    currentContentHandling?.value || targetInitialState?.content_handling,
  );
  const targetPageStyle = normalizePageStyle(currentPageStyle?.value || targetInitialState?.page_style);
  const targetPrompt = normalizePromptForSubmit(currentPagePrompt?.value || targetInitialState?.prompt || "");
  const iterationNote = normalizePromptForSubmit(currentPageIterationNote?.value || "");
  if (!targetInitialState) {
    const bootstrapResponse = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides`, {
      method: "POST",
      body: JSON.stringify({
        page_type: targetPageType,
        content_handling: targetContentHandling,
        page_style: targetPageStyle,
        title: "",
        prompt: targetPrompt || "",
      }),
    });
    appendLog(commandSummary("自动补建第 1 页", bootstrapResponse));
    if (!bootstrapResponse.ok) throw new Error(bootstrapResponse.message || "创建第 1 页失败。");
    selectedSlide = Number(bootstrapResponse.data?.slide_id || targetSlide || 1);
    await recordTaskEvent("slide_appended", { slide_id: selectedSlide, source: "auto_generate_bootstrap" });
    await loadStatus();
    targetInitialState = slideStateById(targetSlide) || slideStateById(selectedSlide);
    syncCurrentPagePrompt();
    updateButtons(Boolean(activeProject));
  }
  const targetSlideNo = Number(targetInitialState?.slide_no || slideNoById(targetSlide) || 1);
  const maxAttempts = AUTO_OPTIMIZE_MAX_ATTEMPTS;
  humanInterventionSlides.delete(targetSlide);
  // Legacy contract markers for frontend state tests:
  // autoGenerationTargetSlide = targetSlide
  // autoGenerationRunning = true
  let taskPromise;
  let manualGenerationTurnAcquired = false;
  manualGenerationQueuedSlides.add(targetSlide);
  renderSlideListWithReview(latestStatus?.slides || []);
  renderPageStream(latestStatus?.slides || []);
  updateButtons(Boolean(activeProject));
  taskPromise = (async () => {
    await Promise.resolve();
    manualGenerationTurnAcquired = await acquireManualGenerationTurn(targetSlide);
    if (!manualGenerationTurnAcquired) return;
    if (Number(selectedSlide) === targetSlide) setPreviewBusy(`正在生成第 ${targetSlideNo} 页...`);
    setState("正在生成本页", "running");
    startSlowGenerationHints(targetSlide);
    startAutoGenerationPolling();
    updateButtons(Boolean(activeProject));
    try {
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        const current = slideStateById(targetSlide) || targetInitialState;
        const retrying = attempt > 1;
        if (retrying) {
          if (Number(selectedSlide) === targetSlide) setPreviewBusy(`第 ${targetSlideNo} 页正在自动优化（${attempt}/${maxAttempts}）...`);
          appendLog(`第 ${targetSlideNo} 页自动优化第 ${attempt - 1} 次。`);
          await recordTaskEvent("auto_optimize_retry", { slide_id: targetSlide, attempt: attempt - 1 });
        }
        const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${targetSlide}/auto-generate`, {
          method: "POST",
          body: JSON.stringify({
            page_type: normalizeWorkbenchPageType(targetPageType || current?.page_type),
            content_handling: targetContentHandling,
            page_style: targetPageStyle,
            title: current?.title || "",
            prompt: targetPrompt || current?.prompt || "",
            iteration_note: iterationNote,
          }),
        });
        appendLog(commandSummary(`第 ${targetSlideNo} 页${retrying ? "自动优化" : "自动生成"}`, response));
        if (!response.ok) {
          setState("本页生成失败", "error");
          if (response.error?.code === "slide_generation_queue_timeout") {
            const waitSec = Number(response.data?.queue_timeout_sec || 0);
            const queueHint = waitSec > 0 ? `队列等待超时（${waitSec}s）` : "队列等待超时";
            throw new Error(`${queueHint}，请稍后重试本页生成。`);
          }
          throw new Error(response.message || "本页生成失败。");
        }
        await recordTaskEvent(retrying ? "auto_optimize_slide" : "auto_generate_slide", { slide_id: targetSlide, attempt });
        await loadStatus();
        if (Number(selectedSlide) === targetSlide) setPreviewBusy(`第 ${targetSlideNo} 页已生成，正在完成...`);
        await qaCurrentSlide(targetSlide);
        if (Number(selectedSlide) === targetSlide) await refreshCurrentPreview();
        if (!currentSlideNeedsIntervention(targetSlide)) {
          setState("本页已生成", "ready");
          if (Number(selectedSlide) === targetSlide && currentPageIterationNote) currentPageIterationNote.value = "";
          return;
        }
        if (!shouldAutoRepairCurrentSlide(targetSlide)) {
          setState("本页可用，有优化建议", "ready");
          appendLog("当前页只有优化建议，不需要反复修复；可以继续生成 PPT。");
          if (Number(selectedSlide) === targetSlide && currentPageIterationNote) currentPageIterationNote.value = "";
          return;
        }
      }
      setState("本页仍需处理", "error");
      humanInterventionSlides.add(targetSlide);
      appendLog(`第 ${targetSlide} 页生成失败，请调整本页内容后重试。`);
      await recordTaskEvent("auto_optimize_needs_human", { slide_id: targetSlide, attempts: maxAttempts });
      renderNextAction(latestStatus);
    } finally {
      // Legacy contract markers for frontend state tests:
      // autoGenerationRunning = false
      // autoGenerationTargetSlide = null
      if (manualGenerationTurnAcquired) {
        releaseManualGenerationTurn(targetSlide);
        manualGenerationTurnAcquired = false;
      }
      clearSlowGenerationHints(targetSlide);
      markSlideGenerationFinished(targetSlide, taskPromise);
      try {
        await loadStatus();
      } catch (error) {
        appendLog(error.message || String(error));
      }
      renderSlideListWithReview(latestStatus?.slides || []);
      renderPageStream(latestStatus?.slides || []);
      if (!autoGenerationRunning) {
        stopAutoGenerationPolling();
        setPreviewBusy("", false);
      }
      updateButtons(Boolean(activeProject));
    }
  })();
  markSlideGenerationStarted(targetSlide, taskPromise);
  if (!waitForCompletion) {
    taskPromise.catch((error) => {
      appendLog(error.message || String(error));
    });
    return;
  }
  await taskPromise;
}

async function repairCurrentSlide() {
  if (isApiAutoMode() && latestStatus?.recommended_next_action?.key === "repair_budget") {
    const budgetResponse = await api(`/api/projects/${encodeURIComponent(activeProject)}/budget-repair-task`, {
      method: "POST",
    });
    appendLog(commandSummary("预算压缩修复", budgetResponse));
    if (!budgetResponse.ok) throw new Error(budgetResponse.message || "预算压缩修复失败。");
    await recordTaskEvent("repair_task", {
      repair_type: "budget_auto_compact",
      slides: budgetResponse.data?.updated_slides || [],
    });
    await loadStatus();
    return;
  }
  await autoGenerateCurrentSlide();
}

async function repairCurrentSlideAction() {
  if (isApiAutoMode()) {
    await autoGenerateCurrentSlide();
    return;
  }
  await repairCurrentSlide();
}

async function repairDeliveryBlocker() {
  appendLog("交付问题将通过重新生成页面或再次导出处理。");
  await loadStatus();
  await exportCurrentDeck();
}

async function exportCurrentDeck() {
  appendLog("正在执行 quick finalize...");
  setState("导出中", "running");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/finalize`, {
    method: "POST",
    body: JSON.stringify({ fresh: false }),
  });
  appendLog(commandSummary("Quick finalize", response));
  if (isReviewRequiredFinalize(response)) {
    showFinalizeReviewRequired(response);
    await loadStatus();
    return;
  }
  if (!response.ok || response.data?.returncode !== 0) {
    setState("导出失败", "error");
    if (response.data?.doctor_hint) appendLog(`导出失败建议：${response.data.doctor_hint}`);
    return;
  }
  setState("已导出", "done");
  appendLog(`导出文件：${response.data.export_path}`);
  await recordTaskEvent("export_pptx", { returncode: response.data?.returncode ?? 0 });
  await loadStatus();
}

async function exportCurrentSlide() {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  const slide = Number(selectedSlide);
  setState("正在准备下载", "running");
  appendLog(`正在准备第 ${slide} 页下载。`);
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${slide}/export-pptx`, {
    method: "POST",
  });
  appendLog(commandSummary(`第 ${slide} 页单页导出`, response));
  if (!response.ok) {
    setState("下载失败", "error");
    throw new Error(response.message || "这一页下载失败，请重新生成本页。");
  }
  const filename = singleSlideDownloadFilename(slide);
  const url = `/api/projects/${encodeURIComponent(activeProject)}/slides/${slide}/export-pptx?t=${Date.now()}`;
  const bytes = await downloadBlob(url, filename);
  await recordTaskEvent("export_single_slide", { slide_id: slide, download_triggered: true, bytes });
  appendLog(`第 ${slide} 页下载已开始：${filename}（${bytes} bytes）。`);
  setState("已开始下载", "done");
  await loadStatus();
}

async function deleteCurrentSlide() {
  const current = selectedSlideState();
  if (!activeProject || !current) throw new Error("请先选择要删除的页面。");
  if (isSlideLockedForDelete(current)) {
    throw new Error("当前页正在生成或检查，请稍候再删除。");
  }
  const slide = selectedSlide;
  const confirmed = window.confirm(`确定要删除第 ${slide} 页吗？本页文件会移到本地归档区，并将后续页前移。`);
  if (!confirmed) return;
  setState("正在删除页面", "running");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}`, {
    method: "DELETE",
  });
  appendLog(commandSummary(`删除第 ${slide} 页`, response));
  if (!response.ok) {
    setState("删除页面失败", "error");
    throw new Error(response.message || "删除页面失败。");
  }
  selectedSlide = Number(response.data?.selected_slide_id || 1);
  await recordTaskEvent("delete_slide", { slide_id: slide, selected_slide_id: selectedSlide });
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
  await loadQaReport();
  appendLog(`第 ${slide} 页已删除。`);
}

async function handleExportDeckClick() {
  if (hasDownloadablePpt(latestStatus)) {
    downloadCurrentDeck();
    return;
  }
  await exportCurrentDeck();
}

async function runFreshFinalize(mode) {
  appendLog(`正在执行 fresh ${mode}...`);
  setState("导出中", "running");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/finalize`, {
    method: "POST",
    body: JSON.stringify({ fresh: true, mode }),
  });
  appendLog(commandSummary(`Fresh ${mode}`, response));
  if (isReviewRequiredFinalize(response)) {
    showFinalizeReviewRequired(response);
    await loadStatus();
    return;
  }
  if (!response.ok || response.data?.returncode !== 0) {
    setState("导出失败", "error");
    if (response.data?.doctor_hint) appendLog(`导出失败建议：${response.data.doctor_hint}`);
    return;
  }
  setState("已导出", "done");
  if (response.data?.export_path) appendLog(`导出文件：${response.data.export_path}`);
  await loadStatus();
}

async function loadRevisions() {
  if (!activeProject || !revisionList) return;
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}/revisions`);
  if (!response.ok) {
    revisionList.innerHTML = `<div class="empty-note">暂无备份版本。</div>`;
    return;
  }
  const revisions = response.data.revisions || [];
  if (!revisions.length) {
    revisionList.innerHTML = `<div class="empty-note">暂无备份版本。</div>`;
    return;
  }
  revisionList.innerHTML = revisions
    .map(
      (item) => `
    <button class="revision-item" data-revision="${item.name}">
      <span>${item.name}</span>
      <small>${item.modified_at}</small>
    </button>
  `,
    )
    .join("");
  revisionList.querySelectorAll(".revision-item").forEach((button) => {
    button.addEventListener("click", () => restoreRevision(button.dataset.revision));
  });
}

async function loadQaReport() {
  if (!activeProject || !qaReport) return;
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/qa-report`);
  if (!response.ok || !response.data.exists) {
    if (qaEvidencePreview) qaEvidencePreview.classList.add("hidden");
    renderCurrentSlideQaSummary();
    return;
  }
  if (qaEvidencePreview && contactSheetPreview) {
    const hasContactSheet = Boolean(latestStatus?.last_contact_sheet_path);
    qaEvidencePreview.classList.toggle("hidden", !hasContactSheet);
    if (hasContactSheet) {
      contactSheetPreview.src = `/api/projects/${encodeURIComponent(activeProject)}/qa-contact-sheet?t=${Date.now()}`;
    }
  }
  const content = response.data.content || "QA 报告为空。";
  const current = selectedSlideState();
  const qaText = current?.qa_status || "not_run";
  const header = `当前页状态：第 ${Number(current?.slide_no || 0)} 页 | qa_status=${qaText} | ${qaScopeLabel()}`;
  qaReport.textContent = `${header}\n\n${content}`;
}

async function openQaEvidencePanel() {
  setPanelExpanded(qaPanel, toggleQaPanel, true);
  await loadStatus();
  await loadQaReport();
  qaPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
  setState("已打开", "ready");
}

async function restoreRevision(revisionName) {
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}/restore-revision`, {
    method: "POST",
    body: JSON.stringify({ revision_name: revisionName }),
  });
  appendLog(response.message);
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
}

async function restorePreviousSlideRevision() {
  if (!activeProject) throw new Error("请先选择或创建任务。");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}/revisions`);
  if (!response.ok) throw new Error(response.message || "读取上一版失败。");
  const revisions = response.data?.revisions || [];
  if (!revisions.length) throw new Error("当前页还没有可恢复的上一版。");
  await restoreRevision(revisions[0].name);
  setState("已恢复上一版", "ready");
}
