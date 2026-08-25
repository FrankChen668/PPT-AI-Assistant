// next_action.js — C13-0 拆分：下一步建议 / 推荐动作 / 按钮更新（由 app.js 原样迁移）

function hasAnySvg(status) {
  return Boolean(status && Array.isArray(status.slides) && status.slides.some((slide) => slideIsDisplayable(slide)));
}

function hasFailedQa(status) {
  return Boolean(
    status &&
      Array.isArray(status.slides) &&
      status.slides.some((slide) => ["failed", "qa_failed"].includes(String(slide.qa_status || ""))),
  );
}

function allSlidesPassedQa(status) {
  return Boolean(
    status &&
      Array.isArray(status.slides) &&
      status.slides.length &&
      status.slides.every((slide) => String(slide.qa_status || "") === "passed"),
  );
}

function hasGeneratedPpt(status) {
  return Boolean(status?.export?.pptx_path || status?.export?.status === "exported");
}

function hasDownloadablePpt(status) {
  return Boolean(status?.delivery_approved === true);
}

function isReviewRequiredFinalize(response) {
  const data = response?.data || {};
  return Boolean(
    data.finalize_status === "review_required" ||
      (data.export_path && data.returncode !== 0 && (data.delivery_blocked || data.manual_review_required)),
  );
}

function showFinalizeReviewRequired(response) {
  setState("PPT 可下载，建议复核", "done");
  const detail = response.data?.user_facing_error || "PPT 已生成，可下载；正式使用前建议人工复核。";
  appendLog(detail);
  if (response.data?.export_path) appendLog(`已生成文件：${response.data.export_path}`);
}

function budgetOverloadedSlides(status) {
  const slides = status?.export_readiness?.budget_overloaded_slides;
  return Array.isArray(slides) ? slides.map(Number).filter((item) => Number.isFinite(item)) : [];
}

function missingSlidesWithPrompt(status) {
  if (!status || !Array.isArray(status.slides)) return [];
  return status.slides.filter((slide) => {
    const hasSvg = slideIsDisplayable(slide);
    if (hasSvg) return false;
    return Boolean(String(slide?.prompt || "").trim());
  });
}

function deckLevelRepairItems(status) {
  const items = status?.deck_level_repair_blockers;
  return Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
}

function hardDeckLevelRepairItems(status) {
  const deliveryBlocked = status?.delivery_blocked === true;
  return deckLevelRepairItems(status).filter((item) => {
    const issueCode = String(item?.issue_code || "").trim().toLowerCase();
    const severity = String(item?.severity || "").trim().toLowerCase();
    if (deliveryBlocked) return true;
    if (severity === "error" || severity === "danger" || severity === "blocking") return true;
    return issueCode !== "visual-delivery-review-required";
  });
}

function softDeckLevelRepairItems(status) {
  const hardKeys = new Set(
    hardDeckLevelRepairItems(status).map(
      (item) => `${String(item?.issue_code || "")}|${String(item?.message || "")}|${String(item?.slide_id || "")}`,
    ),
  );
  return deckLevelRepairItems(status).filter((item) => {
    const key = `${String(item?.issue_code || "")}|${String(item?.message || "")}|${String(item?.slide_id || "")}`;
    return !hardKeys.has(key);
  });
}

function firstUnreadySlide(status) {
  if (!status || !Array.isArray(status.slides)) return 1;
  const overloaded = budgetOverloadedSlides(status);
  if (overloaded.length) return overloaded[0];
  const missing = status.slides.find((slide) => !slideIsDisplayable(slide));
  const failed = status.slides.find((slide) => ["failed", "qa_failed"].includes(String(slide.qa_status || "")));
  const unchecked = status.slides.find((slide) => String(slide.qa_status || "not_run") !== "passed");
  return Number((failed || missing || unchecked || status.slides[0] || {}).slide_id || 1);
}

function uncheckedGeneratedSlides(status) {
  if (!status || !Array.isArray(status.slides)) return [];
  return status.slides.filter((slide) => {
    const hasSvg = Boolean(slide.has_svg || slide.svg_status === "svg_authored" || slide.svg_status === "svg_ready");
    return hasSvg && String(slide.qa_status || "not_run") !== "passed";
  });
}

function shouldScheduleAutoCheck(status) {
  return (
    Boolean(activeProject) &&
    isApiAutoMode() &&
    !autoGenerationRunning &&
    !autoCheckRunning &&
    latestStatus?.generation?.api_key_configured !== false &&
    uncheckedGeneratedSlides(status).length > 0
  );
}

function scheduleAutoCheckIfNeeded(status = latestStatus) {
  if (!shouldScheduleAutoCheck(status) || autoCheckTimer) return;
  autoCheckTimer = window.setTimeout(async () => {
    autoCheckTimer = null;
    if (!shouldScheduleAutoCheck(latestStatus)) return;
    try {
      await qaUncheckedGeneratedSlides();
    } catch (error) {
      appendLog(`自动检查启动失败：${error.message || String(error)}`);
      autoCheckRunning = false;
      updateButtons(Boolean(activeProject));
    }
  }, 0);
}

const ACTION_COPY = {};
const INTERNAL_ACTION_TITLE_PATTERN = /(?:\u68c0\u67e5|\u590d\u6838|QA|qa)/;

function compactRecommendedActionTitle(key, label) {
  const actionKey = String(key || "");
  if (actionKey === "create_task") return "创建任务";
  if (actionKey === "edit_page_prompt") return "补充本页内容";
  if (actionKey === "auto_generate") return "生成页面";
  if (actionKey === "auto_check" || actionKey === "qa_slide") return "生成中";
  if (actionKey === "repair_slide" || actionKey === "repair_budget" || actionKey === "auto_optimize_slide") return "生成失败";
  if (actionKey === "repair_delivery_blocker") return "下载";
  if (actionKey === "repair_export_failure") return "生成失败";
  if (actionKey === "export_pptx" || actionKey === "fresh_release_safe") return "生成 PPT";
  if (actionKey === "download_pptx" || actionKey === "export_current_slide") return "下载";
  if (actionKey === "manual_review") return "已生成，可下载";
  const cleanLabel = String(label || "刷新").trim();
  return INTERNAL_ACTION_TITLE_PATTERN.test(cleanLabel) ? "刷新" : cleanLabel;
}

function serverRecommendedAction(status) {
  const action = status?.recommended_next_action;
  if (!action || !action.key) return null;
  const copy = ACTION_COPY[action.key] || {};
  const label = String(action.label || "刷新").trim();
  return {
    key: action.key,
    title: compactRecommendedActionTitle(action.key, label),
    detail: action.user_message || action.detail || "",
    helper: copy.helper || "",
    progress: "",
    disabled: Boolean(action.disabled),
    slide_id: action.slide_id,
  };
}

function userNextStep(status) {
  const recommended = serverRecommendedAction(status);
  if (recommended?.key === "auto_check" && isApiAutoMode()) {
    return {
      key: "auto_check_running",
      title: "生成中",
      detail: "",
      helper: "",
      progress: "",
      disabled: true,
    };
  }
  if (recommended) return recommended;
  if (autoCheckRunning) {
    return {
      key: "auto_check_running",
      title: "生成中",
      detail: "",
      helper: "",
      progress: "",
      disabled: true,
    };
  }
  if (!activeProject) {
    return {
      key: "create_task",
      title: "创建任务",
      detail: "",
      helper: "",
      progress: "",
    };
  }
  return {
    key: "refresh_status",
    title: "刷新",
    detail: "",
    helper: "",
    progress: "",
    disabled: false,
  };
}

function renderWorkflowMap(status) {
  const downloadable = hasDownloadablePpt(status);
  const stepState = {
    create: activeProject ? "done" : "active",
    page: hasAnySvg(status) ? "done" : activeProject ? "active" : "",
    download: downloadable ? "active" : "",
  };
  workflowSteps.forEach((step) => {
    const state = stepState[step.dataset.step] || "";
    step.classList.remove("active", "done", "blocked", "review");
    if (state) step.classList.add(state);
  });
}

function renderNextAction(status) {
  const hidePagewiseTopAction = isPagewiseWorkflowStatus(status);
  if (nextActionPanel) nextActionPanel.classList.toggle("hidden", hidePagewiseTopAction);
  if (hidePagewiseTopAction) {
    if (isMissingProjectStatus(status)) renderUserBlocker(status);
    else if (userBlockerPanel) userBlockerPanel.classList.add("hidden");
    return;
  }
  const action = userNextStep(status);
  if (nextActionTitle) nextActionTitle.textContent = action.title;
  if (nextActionButton) {
    setButtonLabel(nextActionButton, action.title);
    nextActionButton.dataset.action = action.key;
    nextActionButton.disabled = Boolean(action.disabled);
  }
  renderUserBlocker(status);
}

function currentPageGenerateBlocker(current = selectedSlideState(), slideId = selectedSlide) {
  const targetSlide = Number(slideId || selectedSlide || 1);
  const slides = Array.isArray(latestStatus?.slides) ? latestStatus.slides : [];
  const promptText = String(currentPagePrompt?.value || slidePromptForUi(current, targetSlide) || "").trim();
  if (!activeProject) return "请先选择或创建任务。";
  if (!isApiAutoMode()) return "当前任务不是自动生成模式。";
  if (!current && slides.length > 0) return `第 ${targetSlide} 页不存在，请先刷新页面列表。`;
  if (!promptText) return `第 ${targetSlide} 页还没有提示词，请先补充本页内容。`;
  if (slideIsQueuedForGeneration(targetSlide)) return "等待中";
  if (hasSlideGenerationInFlight(targetSlide)) return "生成中";
  return "";
}

function updateButtons(enabled) {
  const config = WORKFLOW_CONFIG[currentWorkflowMode()] || WORKFLOW_CONFIG.prompt_deck;
  const repairMode = currentWorkflowMode() === "repair_existing" || Boolean(config.disabledCreate);
  const missingProject = isMissingProjectStatus();
  if (createTask) {
    createTask.disabled = repairMode || createTask.dataset.busy === "true";
  }
  if (refreshStatus) refreshStatus.disabled = !enabled;
  if (refreshPreview) refreshPreview.disabled = !enabled;
  if (regenSlide) regenSlide.disabled = !enabled;
  if (generatePacket) generatePacket.disabled = !enabled;
  if (fitPreview) fitPreview.disabled = !enabled;
  if (previewZoom) previewZoom.disabled = !enabled;
  if (fullscreenPreview) fullscreenPreview.disabled = !enabled;
  if (startSlideshow) startSlideshow.disabled = !enabled || !latestStatus?.slides?.length;
  if (resetPreview) resetPreview.disabled = !enabled;
  const current = selectedSlideState();
  const hasSvg = slideIsDisplayable(current);
  const hasPrompt = Boolean((currentPagePrompt?.value || current?.prompt || "").trim());
  const isFailed = Boolean(current && (current.qa_status === "failed" || current.status === "qa_failed"));
  const currentSlideQueued = Boolean(current && slideIsQueuedForGeneration(current.slide_id));
  const currentSlideInFlight = Boolean(current && hasSlideGenerationInFlight(current.slide_id) && !currentSlideQueued);
  const generateBlocker = currentPageGenerateBlocker(current);
  if (qaSlide) qaSlide.disabled = !enabled || !hasSvg;
  if (autoGeneratePage) {
    const generateButtonLabel = currentSlideQueued ? "等待中" : currentSlideInFlight ? "生成中" : isFailed || hasSvg ? "重新生成本页" : "生成本页";
    setButtonLabel(autoGeneratePage, generateButtonLabel);
    autoGeneratePage.disabled =
      !enabled || !current || !isApiAutoMode() || !hasPrompt || currentSlideQueued || currentSlideInFlight || Boolean(generateBlocker);
    autoGeneratePage.title = generateBlocker || generateButtonLabel;
  }
  if (autoGenerateMissingPages) {
    const pendingCount = missingSlidesWithPrompt(latestStatus).length;
    const hasPendingPages = isApiAutoMode() && pendingCount > 0;
    autoGenerateMissingPages.classList.toggle("hidden", !hasPendingPages);
    autoGenerateMissingPages.disabled = !enabled || !hasPendingPages || autoGenerateMissingPages.dataset.busy === "true";
    setButtonLabel(autoGenerateMissingPages, `生成未完成页（${pendingCount}）`);
  }
  if (repairCurrentPage) {
    repairCurrentPage.classList.toggle("hidden", isApiAutoMode());
    repairCurrentPage.disabled = isApiAutoMode() || !enabled || !isFailed;
  }
  if (restorePreviousRevision) {
    const revisionCount = Number(current?.revision_count || 0);
    restorePreviousRevision.disabled = !enabled || !current || revisionCount <= 0 || currentSlideInFlight;
  }
  if (repairSlide) {
    repairSlide.classList.toggle("hidden", isApiAutoMode());
    repairSlide.disabled = isApiAutoMode() || !enabled;
  }
  if (downloadCurrentPage) {
    downloadCurrentPage.classList.toggle("hidden", !enabled || !hasSvg);
    downloadCurrentPage.disabled = !enabled || !hasSvg;
  }
  if (deleteCurrentPage) deleteCurrentPage.disabled = !enabled || !current || isSlideLockedForDelete(current);
  const pptReady = hasDownloadablePpt(latestStatus);
  const canExport = enabled && latestStatus && (pptReady || (latestStatus.export_readiness && latestStatus.export_readiness.ready));
  if (exportDeck) {
    exportDeck.classList.toggle("hidden", !canExport);
    exportDeck.disabled = !canExport;
    setButtonLabel(exportDeck, pptReady ? "下载 PPT" : "生成 PPT");
    exportDeck.title = pptReady ? "下载 PPT" : "生成 PPT";
  }
  if (freshReleaseSafe) freshReleaseSafe.disabled = !canExport;
  if (freshPremium) freshPremium.disabled = !canExport;
  if (refreshRevisions) refreshRevisions.disabled = !enabled;
  if (refreshQaReport) refreshQaReport.disabled = !enabled;
  if (collapsedCreateTask) collapsedCreateTask.disabled = createTask.disabled;
  if (appendSlideFromList) {
    appendSlideFromList.disabled = !enabled || isSinglePageDeck() || missingProject;
    appendSlideFromList.classList.toggle("hidden", isSinglePageDeck() || missingProject);
  }
  if (insertSlideAfterCurrent) {
    insertSlideAfterCurrent.disabled = !enabled || !current || isSinglePageDeck() || missingProject;
    insertSlideAfterCurrent.classList.toggle("hidden", isSinglePageDeck() || missingProject);
  }
  if (nextActionButton) {
    const action = nextActionButton.dataset.action || "";
    nextActionButton.disabled = nextActionButton.dataset.busy === "true" || (!enabled && action !== "create_task");
  }
  renderCurrentPageActionHint();
  renderPreviewRetryState();
}

function renderCurrentSlideQaSummary() {
  const current = selectedSlideState();
  if (!qaReport || !current) return;
  const qaText = current.qa_status || "not_run";
  const header = `当前页状态：第 ${selectedSlide} 页 | qa_status=${qaText} | ${qaScopeLabel()}`;
  const error = userFacingGenerationError(current.last_error || "");
  if (error) {
    qaReport.textContent = `${header}\n\n失败摘录：\n${error}`;
    return;
  }
  qaReport.textContent = `${header}\n\n尚无失败摘录。`;
}

function clearQaReport() {
  if (qaEvidencePreview) qaEvidencePreview.classList.add("hidden");
  if (qaReport) qaReport.textContent = "";
}
