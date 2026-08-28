// preview.js — C13-0 拆分：预览缩放 / 全屏 / 幻灯片放映 / 状态刷新（由 app.js 原样迁移）

function computeFitScale() {
  if (!previewStageShell) return 1;
  return window.WorkbenchPreviewState.computeFitScale(previewStageShell.clientWidth, previewStageShell.clientHeight);
}

function applyPreviewScale() {
  if (!previewStage || !previewStageSizer || !previewStageShell) return;
  const scale = previewState.currentScale(computeFitScale());
  const width = window.WorkbenchPreviewState.PREVIEW_BASE_WIDTH * scale;
  const height = window.WorkbenchPreviewState.PREVIEW_BASE_HEIGHT * scale;
  previewStage.style.transform = `scale(${scale})`;
  previewStageSizer.style.width = `${width}px`;
  previewStageSizer.style.height = `${height}px`;
  previewStageShell.classList.toggle("fit-mode", previewState.mode === "fit");
  previewStageShell.classList.toggle("manual-mode", previewState.mode === "manual");
}

function stepPreviewZoom(direction) {
  const options = previewZoom ? Array.from(previewZoom.options).map((item) => Number(item.value)) : [0.75, 1, 1.25, 1.5, 2];
  const current = previewState.currentScale(computeFitScale());
  setPreviewMode("manual", previewState.nextZoomScale(direction, current, options));
}

function setPreviewMode(mode, scale = previewState.manualScale) {
  const prefs = previewState.setMode(mode, scale);
  if (prefs.mode === "manual" && previewZoom) {
    previewZoom.value = String(prefs.manualScale);
  } else if (previewZoom) {
    const options = Array.from(previewZoom.options).map((item) => Number(item.value));
    previewZoom.value = String(previewState.closestScale(computeFitScale(), options));
  }
  applyPreviewScale();
  savePreviewPrefs();
}

function updateFullscreenButton() {
  if (!fullscreenPreview) return;
  const inFullscreen = document.fullscreenElement === previewZone;
  const label = inFullscreen ? "退出全屏预览" : "全屏预览";
  fullscreenPreview.setAttribute("title", label);
  fullscreenPreview.setAttribute("aria-label", label);
}

function slideshowSlides() {
  return Array.isArray(latestStatus?.slides) ? latestStatus.slides : [];
}

function showSlideshowSlide(slideId = slideshowSlide) {
  const slides = slideshowSlides();
  if (!slideshowOverlay || !slideshowFrame || !slideshowCounter || !slides.length) return;
  const ids = slides.map((slide) => Number(slide.slide_id || 0)).filter((id) => id > 0);
  const minId = Math.min(...ids);
  const maxId = Math.max(...ids);
  slideshowSlide = Math.min(Math.max(Number(slideId) || selectedSlide || minId, minId), maxId);
  const current = slides.find((slide) => Number(slide.slide_id || 0) === slideshowSlide) || null;
  const hasSvg = Boolean(activeProject && slideIsDisplayable(current));
  if (hasSvg) {
    slideshowFrame.src = slidePreviewUrl(slideshowSlide);
  } else {
    slideshowFrame.removeAttribute("src");
  }
  slideshowFrame.classList.toggle("hidden", !hasSvg);
  slideshowEmpty?.classList.toggle("hidden", hasSvg);
  slideshowCounter.textContent = `${slideshowSlide} / ${maxId}`;
  if (slideshowPrev) slideshowPrev.disabled = slideshowSlide <= minId;
  if (slideshowNext) slideshowNext.disabled = slideshowSlide >= maxId;
}

async function openSlideshow() {
  if (!slideshowOverlay || !slideshowSlides().length) return;
  slideshowOverlay.classList.remove("hidden");
  showSlideshowSlide(selectedSlide);
  if (!document.fullscreenElement && slideshowOverlay.requestFullscreen) {
    try {
      await slideshowOverlay.requestFullscreen();
    } catch {
      // Browser may reject fullscreen when focus is not user-initiated; the overlay still works.
    }
  }
}

async function closeSlideshowOverlay() {
  if (!slideshowOverlay) return;
  slideshowOverlay.classList.add("hidden");
  slideshowFrame?.removeAttribute("src");
  if (document.fullscreenElement === slideshowOverlay) {
    await document.exitFullscreen();
  }
}

function stepSlideshow(delta) {
  showSlideshowSlide(slideshowSlide + delta);
}

async function loadStatus(options = {}) {
  if (!activeProject) return;
  const useLite = Boolean(options.lite);
  const statusAction = useLite ? "status-lite" : "status";
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/${statusAction}`);
  if (!response.ok) {
    throw new Error(response.message || "读取状态失败。");
  }
  latestStatus = useLite ? mergeLiteStatus(latestStatus, response.data) : response.data;
  activeProjectTitle = userFacingTaskTitle(latestStatus?.task_title || activeProject);
  if (Array.isArray(latestStatus?.slides)) {
    latestStatus.slides.forEach((slide) => reconcileLocalDraftWithServer(slide));
  }
  reconcileGenerationTasksWithServer(latestStatus.slides || []);
  saveActiveProject();
  projectName.textContent = userFacingTaskTitle(latestStatus?.task_title || activeProject);
  renderExportReadiness(latestStatus.export_readiness);
  renderQaEvidence(latestStatus);
  renderSlideListWithReview(latestStatus.slides || []);
  if (useLite) {
    updatePageStreamState(latestStatus.slides || []);
  } else {
    renderPageStream(latestStatus.slides || []);
  }
  syncCurrentPagePrompt();
  renderWorkflowMap(latestStatus);
  renderNextAction(latestStatus);
  const projectStatus = latestStatus.project_status || "project_created";
  const missingProject = projectStatus === "missing";
  const exportReviewRequired = latestStatus?.export?.status === "review_required" || projectStatus === "export_review_required";
  const manualReviewRequired = latestStatus?.manual_review_required === true || latestStatus?.delivery_status === "downloadable_with_notes";
  const downloadReady = hasDownloadablePpt(latestStatus);
  const hasOldPpt = hasGeneratedPpt(latestStatus);
  const pagewiseStateText = isPagewiseWorkflowStatus(latestStatus) ? pagewiseProjectProgressCopy(latestStatus) : "";
  let stateText = downloadReady
    ? (manualReviewRequired ? "PPT 可下载，建议复核" : exportReviewRequired ? "PPT 已生成，可下载" : "PPT 可下载")
    : exportReviewRequired
      ? "PPT 生成未完成"
      : hasOldPpt
        ? "已有旧 PPT，需重新生成"
        : projectStateText[projectStatus] || projectStatus;
  const currentGenerationStateText = currentPageGenerationStateText();
  if (pagewiseStateText && !downloadReady) stateText = pagewiseStateText;
  if (currentGenerationStateText) stateText = currentGenerationStateText;
  let style = "running";
  if (downloadReady || projectStatus === "qa_passed") style = exportReviewRequired ? "running" : "done";
  if (projectStatus === "export_ready" || projectStatus === "svg_ready") style = "ready";
  if (projectStatus === "qa_failed" || projectStatus === "export_failed" || projectStatus === "export_review_required" || missingProject) style = "error";
  if (projectStatus === "project_created" || projectStatus === "waiting_codex") style = "idle";
  setState(stateText, style);
  const routeLabel = latestStatus.route_label || "-";
  const routeId = latestStatus.route_id || "-";
  const workflowLabel = latestStatus.workflow_label || WORKFLOW_CONFIG[currentWorkflowMode()]?.label || "逐页生成 PPT";
  const allowed = (latestStatus.route_policy?.allowed_actions || []).join(", ") || "-";
  const forbidden = (latestStatus.route_policy?.forbidden_actions || []).join(", ") || "-";
  if (routeMeta) {
    routeMeta.textContent = `${workflowLabel} | 生成路径: ${routeId}（${routeLabel}） | 可用动作: ${allowed} | 禁止动作: ${forbidden}`;
  }
  const templateModeValue = latestStatus.template_mode || "-";
  const templateBound = latestStatus.template_bound ? "已绑定" : "未绑定";
  const templateNote = latestStatus.template_binding_note || "";
  if (templateMeta) {
    templateMeta.textContent = `模板策略: ${templateModeValue} | 模板绑定: ${templateBound} | ${templateNote}`;
  }
  updateGenerationModeUi();
  updateButtons(Boolean(activeProject));
  updateCollapsedSummary();
  renderSlideReviewPanel();
  renderCurrentSlideQaSummary();
}

function syncBrowserProjectUrl(project) {
  const value = String(project || "").trim();
  if (!value || !window.history?.replaceState) return;
  const url = new URL(window.location.href);
  url.searchParams.set("project", value);
  if (url.href !== window.location.href) {
    window.history.replaceState({}, "", url.toString());
  }
}

async function activateProject(project) {
  activeTaskId = "";
  activeProject = project;
  activeProjectTitle = "";
  selectedSlide = 1;
  setWorkbenchView("task_detail");
  projectName.textContent = activeProject;
  saveActiveProject();
  syncBrowserProjectUrl(activeProject);
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
  await loadQaReport();
  appendLog(`已恢复项目：${activeProject}`);
}

async function restoreActiveProject() {
  const params = new URLSearchParams(window.location.search);
  const projectFromUrl = (params.get("project") || "").trim();
  let savedProject = "";
  try {
    savedProject = storage.readText(ACTIVE_PROJECT_KEY, "").trim();
  } catch {
    savedProject = "";
  }
  const listResponse = await api("/api/projects");
  const projects = Array.isArray(listResponse?.data?.projects) ? listResponse.data.projects : [];
  const resumableProjects = Array.isArray(listResponse?.data?.resumable_projects)
    ? listResponse.data.resumable_projects
    : [];
  const resumeMode = String(listResponse?.data?.resume_mode || "none");
  const latestProject = String(listResponse?.data?.latest_project || "").trim();
  const candidates = [projectFromUrl, savedProject].filter(Boolean);
  const nextProject = candidates.find((item) => projects.includes(item));
  if (nextProject) {
    renderResumeChooser([]);
    await activateProject(nextProject);
    return;
  }
  if (resumeMode === "auto" && latestProject && projects.includes(latestProject)) {
    renderResumeChooser([]);
    await activateProject(latestProject);
    return;
  }
  if (resumeMode === "choose") {
    renderResumeChooser(resumableProjects);
    appendLog("发现多个可继续任务，请选择一个恢复。");
  }
}

async function refreshCurrentPreviewLegacy() {
  if (!activeProject) return;
  selectedSlideTitle.textContent = `第 ${selectedSlide} 页`;
  const current = selectedSlideState();
  if (!current || !slideIsDisplayable(current)) {
    previewState.setHasContent(false);
    previewHint.textContent = `第 ${selectedSlide} 页还没有生成。请把交接内容发给助手，完成后回到这里刷新。`;
    previewHint.classList.remove("hidden");
    previewLoading.classList.add("hidden");
    svgPreview.removeAttribute("src");
    updateButtons(Boolean(activeProject));
    renderPreviewRetryState();
    return;
  }
  const url = slidePreviewUrl(selectedSlide);
  previewLoading.classList.remove("hidden");
  const probe = await fetch(url);
  if (!probe.ok) {
    previewState.setHasContent(false);
    previewHint.textContent = `第 ${selectedSlide} 页还没有生成。请把交接内容发给助手，完成后回到这里刷新。`;
    previewHint.classList.remove("hidden");
    previewLoading.classList.add("hidden");
    svgPreview.removeAttribute("src");
    delete svgPreview.dataset.project;
    delete svgPreview.dataset.slide;
    return;
  }
  previewState.setHasContent(true);
  previewHint.classList.add("hidden");
  svgPreview.dataset.project = activeProject;
  svgPreview.dataset.slide = String(selectedSlide);
  svgPreview.src = url;
  updateButtons(Boolean(activeProject));
}

async function refreshCurrentPreview() {
  if (!activeProject) return;
  const previewSlide = Number(selectedSlide);
  selectedSlideTitle.textContent = `第 ${previewSlide} 页`;
  const current = selectedSlideState();
  if (!current || !slideIsDisplayable(current)) {
    previewState.setHasContent(false);
    previewHint.textContent = missingSlidePreviewMessage(current, previewSlide);
    previewHint.classList.remove("hidden");
    clearPreviewLoadFallback();
    if (autoGenerationRunning && shouldShowPreviewBusy(previewSlide)) {
      setPreviewBusy(`正在生成第 ${previewSlide} 页...`);
    } else {
      setPreviewBusy("", false);
    }
    svgPreview.removeAttribute("src");
    delete svgPreview.dataset.project;
    delete svgPreview.dataset.slide;
    updateButtons(Boolean(activeProject));
    return;
  }
  const url = slidePreviewUrl(previewSlide, slidePreviewVersion(current));
  const previewAlreadyLoaded = currentPreviewMatches(previewSlide, url);
  if (shouldShowPreviewBusy(previewSlide) && !previewAlreadyLoaded) {
    setPreviewBusy(`正在加载第 ${previewSlide} 页预览...`);
  } else {
    setPreviewBusy("", false);
  }
  if (Number(selectedSlide) !== previewSlide) return;
  previewState.setHasContent(true);
  previewHint.classList.add("hidden");
  svgPreview.dataset.project = activeProject;
  svgPreview.dataset.slide = String(previewSlide);
  if (!previewAlreadyLoaded) {
    svgPreview.src = url;
    schedulePreviewLoadFallback(previewSlide);
  }
  updateButtons(Boolean(activeProject));
  renderPreviewRetryState();
}
