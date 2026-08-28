// task_detail.js — C13-0 拆分：任务详情 / 幻灯片状态 / 页面草稿（由 app.js 原样迁移）

function slideIsDisplayable(slide) {
  return Boolean(slide?.has_svg);
}

const activeServerGenerationPhases = new Set(["queued", "starting", "running", "retrying"]);

function slideHasActiveServerGenerationPhase(slide) {
  return activeServerGenerationPhases.has(String(slide?.generation_phase || "").trim().toLowerCase());
}

function slideIsGeneratingForUi(slide) {
  const slideId = Number(slide?.slide_id || 0);
  if (slideIsQueuedForGeneration(slideId)) return false;
  return (
    slideIsActiveGeneration(slideId) ||
    hasSlideGenerationInFlight(slideId) ||
    slideHasActiveServerGenerationPhase(slide) ||
    (slide?.status === "generating" && isCurrentTabGeneratingSlide(slideId)) ||
    slide?.status === "qa_running" ||
    slide?.qa_status === "running"
  );
}

function userFacingSlideState(slide) {
  const slideId = Number(slide?.slide_id || 0);
  if (slideIsQueuedForGeneration(slideId)) {
    return { label: "等待中", key: "waiting", downloadable: false, icon: "icon-refresh" };
  }
  const displayable = slideIsDisplayable(slide);
  const isGenerating = slideIsGeneratingForUi(slide);
  const generationError = slideGenerationError(slide);
  if (isGenerating) {
    return { label: "生成中", key: "generating", downloadable: false, icon: "icon-refresh" };
  }
  if (generationError || slide?.status === "failed") {
    return { label: "生成失败", key: "failed", downloadable: false, icon: "icon-wrench" };
  }
  if (displayable) return { label: "已生成", key: "generated", downloadable: true, icon: "icon-file-down" };
  return { label: "未生成", key: "not_generated", downloadable: false, icon: "icon-panel" };
}

function slideQaStateLabel(slide) {
  if (slideNeedsHumanIntervention(slide.slide_id)) return "需处理";
  const hasSvg = slideIsDisplayable(slide);
  if (slideIsQueuedForGeneration(slide.slide_id)) return "等待中";
  if (slideIsGeneratingForUi(slide)) return "正在生成";
  if (slideStateText[slide.qa_status_field]) return slideStateText[slide.qa_status_field];
  if (slide.qa_status === "passed") return "已生成";
  if (slide.qa_status === "failed") return "生成失败";
  if (hasSvg) return "已生成";
  return "未生成";
}

function selectedSlideReviewState() {
  const slide = selectedSlideState();
  if (!slide) return {};
  return {
    score: slide.review_score,
    usable_for_next_edit: slide.review_usable_for_next_edit,
    pptx_editable: slide.review_pptx_editable,
    issue_tags: Array.isArray(slide.review_issue_tags) ? slide.review_issue_tags : [],
    notes: String(slide.review_notes || ""),
    updated_at: String(slide.review_updated_at || ""),
  };
}

function setReviewScoreSelection(score) {
  selectedReviewScore = Number.isInteger(Number(score)) ? Number(score) : null;
  if (!slideReviewScoreGroup) return;
  slideReviewScoreGroup.querySelectorAll(".review-score-btn").forEach((button) => {
    const buttonScore = Number(button.dataset.score || 0);
    const active = Number.isFinite(buttonScore) && buttonScore === selectedReviewScore;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", active ? "true" : "false");
  });
}

function setRadioPair(yesInput, noInput, value) {
  const boolValue = typeof value === "boolean" ? value : null;
  if (!yesInput || !noInput) return;
  yesInput.checked = boolValue === true;
  noInput.checked = boolValue === false;
}

function readRadioPair(yesInput, noInput) {
  if (yesInput?.checked) return true;
  if (noInput?.checked) return false;
  return null;
}

function setReviewTags(tags) {
  const wanted = new Set((Array.isArray(tags) ? tags : []).map((item) => String(item)));
  reviewTagInputs.forEach((input) => {
    input.checked = wanted.has(String(input.value || ""));
  });
}

function readReviewTags() {
  return reviewTagInputs
    .filter((input) => input.checked)
    .map((input) => String(input.value || "").trim())
    .filter(Boolean);
}

function renderSlideReviewPanel() {
  if (!slideReviewPanel) return;
  const hasProject = Boolean(activeProject);
  const current = selectedSlideState();
  const hasSlide = Boolean(current && Number(current.slide_id) > 0);
  slideReviewPanel.classList.toggle("disabled", !hasProject || !hasSlide);
  if (!hasProject || !hasSlide) {
    setReviewScoreSelection(null);
    setRadioPair(reviewUsableYes, reviewUsableNo, null);
    setRadioPair(reviewEditableYes, reviewEditableNo, null);
    setReviewTags([]);
    if (reviewNotes) reviewNotes.value = "";
    if (slideReviewHint) slideReviewHint.textContent = "Select a slide to submit human review.";
    if (slideReviewMeta) slideReviewMeta.textContent = "No manual review submitted yet.";
    if (saveSlideReview) saveSlideReview.disabled = true;
    return;
  }
  const review = selectedSlideReviewState();
  const hasAnyReview =
    review.score != null ||
    review.usable_for_next_edit != null ||
    review.pptx_editable != null ||
    (Array.isArray(review.issue_tags) && review.issue_tags.length > 0) ||
    String(review.notes || "").trim().length > 0;
  setReviewScoreSelection(review.score);
  setRadioPair(reviewUsableYes, reviewUsableNo, review.usable_for_next_edit);
  setRadioPair(reviewEditableYes, reviewEditableNo, review.pptx_editable);
  setReviewTags(review.issue_tags);
  if (reviewNotes) reviewNotes.value = review.notes || "";
  if (slideReviewHint) {
    slideReviewHint.textContent = hasAnyReview
      ? `Slide ${selectedSlide} has manual review; update when needed.`
      : `Slide ${selectedSlide} has no manual review yet.`;
  }
  if (slideReviewMeta) {
    slideReviewMeta.textContent = review.updated_at ? `Last submitted: ${review.updated_at}` : "No manual review submitted yet.";
  }
  if (saveSlideReview) saveSlideReview.disabled = false;
}

async function submitSlideReview() {
  const current = selectedSlideState();
  if (!activeProject || !current) throw new Error("Please select a project and slide first.");
  const payload = {
    score: selectedReviewScore,
    usable_for_next_edit: readRadioPair(reviewUsableYes, reviewUsableNo),
    pptx_editable: readRadioPair(reviewEditableYes, reviewEditableNo),
    issue_tags: readReviewTags(),
    notes: String(reviewNotes?.value || ""),
  };
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  appendLog(commandSummary(`Slide ${selectedSlide} manual review`, response));
  if (!response.ok) {
    throw new Error(response.message || "Failed to save manual review.");
  }
  await recordTaskEvent("manual_review_submitted", { slide_id: selectedSlide, score: selectedReviewScore });
  await loadStatus();
  renderSlideReviewPanel();
}

function updateSlideCountLabel(slides) {
  const rows = Array.isArray(slides) ? slides : [];
  if (!slideCountLabel) return;
  slideCountLabel.textContent = `共 ${rows.length} 页`;
}

function renderSlideList(slides) {
  updateSlideCountLabel(slides);
  slideListRenderSignature = "";
  if (!slides.length) {
    slideList.innerHTML = '<div class="empty-note">还没有页面。</div>';
    return;
  }
  slideList.innerHTML = slides
    .map((slide) => {
      const active = Number(slide.slide_id) === Number(selectedSlide) ? "active" : "";
      const pageState = userFacingSlideState(slide);
      const klass = pageState.key;
      return `<div class="slide-row ${active}" data-slide-row="${slide.slide_id}">
        <button class="slide-main ${active}" data-slide="${slide.slide_id}" title="第 ${slide.slide_id} 页 · ${pageState.label}">
          <span class="slide-no" data-page="${slide.slide_id}">第 ${slide.slide_id} 页</span>
          <span class="slide-dot ${klass}" aria-hidden="true"></span><span class="sr-only">${pageState.label}</span>
        </button>
      </div>`;
    })
    .join("");
  slideList.querySelectorAll(".slide-main").forEach((button) => {
    button.addEventListener("click", () => {
      void selectSlide(Number(button.dataset.slide));
    });
  });
  slideList.querySelectorAll(".packet-btn").forEach((button) => {
    button.addEventListener("click", () =>
      runAction(button, async () => {
        await generatePacketForSlide(Number(button.dataset.slide));
      }),
    );
  });
}

function slideListSignature(rows) {
  return rows
    .map((slide) => {
      const pageState = userFacingSlideState(slide);
      const reviewScore = Number(slide.review_score || 0);
      const hasReview = reviewScore >= 1 && reviewScore <= 5;
      return [
        activeProject,
        Number(slide.slide_id || 0),
        Number(slide.slide_id) === Number(selectedSlide) ? "active" : "",
        pageState.key,
        pageState.label,
        pageState.icon,
        hasReview ? reviewScore : "",
      ].join(":");
    })
    .join("|");
}

function renderSlideListWithReview(slides) {
  const rows = Array.isArray(slides) ? slides : [];
  updateSlideCountLabel(rows);
  if (!rows.length) {
    slideListRenderSignature = "empty";
    slideList.innerHTML = '<div class="empty-note">No slides yet.</div>';
    renderSlideReviewPanel();
    return;
  }
  const signature = slideListSignature(rows);
  if (signature === slideListRenderSignature) {
    renderSlideReviewPanel();
    return;
  }
  slideListRenderSignature = signature;
  slideList.innerHTML = rows
    .map((slide) => {
      const active = Number(slide.slide_id) === Number(selectedSlide) ? "active" : "";
      const pageState = userFacingSlideState(slide);
      const klass = pageState.key;
      const reviewScore = Number(slide.review_score || 0);
      const hasReview = reviewScore >= 1 && reviewScore <= 5;
      const reviewBadge = hasReview
        ? `<span class="slide-review-badge score-${reviewScore}" title="Manual review ${reviewScore}/5">R${reviewScore}</span>`
        : "";
      return `<div class="slide-row ${active}" data-slide-row="${slide.slide_id}">
        <button class="slide-main ${active}" data-slide="${slide.slide_id}" title="第 ${slide.slide_id} 页 · ${pageState.label}">
          <span class="slide-no" data-page="${slide.slide_id}">第 ${slide.slide_id} 页</span>${reviewBadge}
          <span class="slide-dot ${klass}" aria-hidden="true"></span><span class="sr-only">${pageState.label}</span>
        </button>
      </div>`;
    })
    .join("");
  slideList.querySelectorAll(".slide-main").forEach((button) => {
    button.addEventListener("click", () => {
      void selectSlide(Number(button.dataset.slide));
    });
  });
  slideList.querySelectorAll(".packet-btn").forEach((button) => {
    button.addEventListener("click", () =>
      runAction(button, async () => {
        await generatePacketForSlide(Number(button.dataset.slide));
      }),
    );
  });
  renderSlideReviewPanel();
}

function slideStateById(slideId) {
  if (!latestStatus || !Array.isArray(latestStatus.slides)) return null;
  return latestStatus.slides.find((slide) => Number(slide.slide_id) === Number(slideId)) || null;
}

function selectedSlideState() {
  return slideStateById(selectedSlide);
}

function readLocalPageDraft(slideId) {
  const key = Number(slideId);
  if (!Number.isFinite(key) || key < 1) return null;
  return localPageDrafts.get(key) || null;
}

function writeLocalPageDraft(slideId, draft) {
  const key = Number(slideId);
  if (!Number.isFinite(key) || key < 1 || !draft || typeof draft !== "object") return;
  localPageDrafts.set(key, {
    page_type: normalizeWorkbenchPageType(draft.page_type),
    content_handling: normalizeContentHandling(draft.content_handling),
    page_style: normalizePageStyle(draft.page_style),
    prompt: String(draft.prompt || ""),
    dirty: Boolean(draft.dirty),
    updated_at: Date.now(),
  });
}

function captureCurrentPageDraft(dirty = true) {
  const slideId = Number(selectedSlide);
  if (!Number.isFinite(slideId) || slideId < 1) return;
  writeLocalPageDraft(slideId, {
    page_type: normalizeWorkbenchPageType(currentPageType?.value),
    content_handling: normalizeContentHandling(currentContentHandling?.value),
    page_style: normalizePageStyle(currentPageStyle?.value),
    prompt: currentPagePrompt?.value || "",
    dirty,
  });
}

function reconcileLocalDraftWithServer(slide) {
  const slideId = Number(slide?.slide_id || 0);
  if (!Number.isFinite(slideId) || slideId < 1) return;
  const localDraft = readLocalPageDraft(slideId);
  if (!localDraft || !localDraft.dirty) return;
  const serverType = String(slide?.page_type || "content");
  const serverContentHandling = normalizeContentHandling(slide?.content_handling);
  const serverPageStyle = normalizePageStyle(slide?.page_style);
  const serverPrompt = String(slide?.prompt || "");
  if (
    serverType === localDraft.page_type &&
    serverContentHandling === localDraft.content_handling &&
    serverPageStyle === localDraft.page_style &&
    serverPrompt === localDraft.prompt
  ) {
    writeLocalPageDraft(slideId, { ...localDraft, dirty: false });
  }
}

function slidePromptForUi(slide, slideId = null) {
  const id = Number(slideId || slide?.slide_id || 0);
  const localDraft = readLocalPageDraft(id);
  if (localDraft && localDraft.dirty) return String(localDraft.prompt || "");
  return String(slide?.prompt || "");
}

async function selectSlide(slideId) {
  const slide = Number(slideId);
  if (!Number.isFinite(slide) || slide < 1) return;
  selectedSlide = slide;
  renderSlideListWithReview(latestStatus?.slides || []);
  renderPageStream(latestStatus?.slides || []);
  syncCurrentPagePrompt();
  updateButtons(Boolean(activeProject));
  await refreshCurrentPreview();
  await loadRevisions();
  clearQaReport();
  renderSlideReviewPanel();
}

function focusCurrentPagePromptEditor() {
  setInspectorOpen(true, false);
  setInspectorTab("content");
  if (window.matchMedia("(max-width: 1180px)").matches) {
    detailInspector?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  currentPagePrompt?.focus();
}

async function focusSlideContext(slideId, { scroll = true, focusPrompt = false } = {}) {
  const slide = Number(slideId);
  if (!Number.isFinite(slide) || slide < 1) return;
  await selectSlide(slide);
  if (scroll) pagePromptPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (focusPrompt) focusCurrentPagePromptEditor();
}

function slideGenerationError(slide) {
  const error = String(slide?.last_error || "").trim();
  if (!error) return "";
  if (
    slideHasActiveServerGenerationPhase(slide) ||
    (slide?.status === "generating" && isCurrentTabGeneratingSlide(slide?.slide_id || selectedSlide))
  ) {
    return "";
  }
  if (slide?.status === "waiting_prompt") return "";
  const hasSvg = Boolean(slide?.has_svg);
  const generationFailed =
    slide?.generation_phase === "failed" || slide?.generation_phase === "failed_preserved_previous" || slide?.status === "failed";
  if (hasSvg && !generationFailed) return "";
  return userFacingGenerationError(error);
}

function isCurrentTabGeneratingSlide(slideId) {
  if (!autoGenerationRunning) return false;
  if (autoGenerationGlobalBusy) return true;
  return hasSlideGenerationInFlight(slideId);
}

function isStaleGeneratingSlide(slide) {
  return slideIsGeneratingForUi(slide) && !isCurrentTabGeneratingSlide(slide?.slide_id || selectedSlide);
}

function isSlideLockedForDelete(slide) {
  if (!slide) return false;
  return hasSlideGenerationInFlight(slide.slide_id || selectedSlide);
}

function slidePreviewVersion(slide) {
  return String(slide?.generation_completed_at || slide?.lock_updated_at || slide?.updated_at || "").trim();
}

function pageStreamPreviewUrl(slideId, previewVersion = "") {
  return slidePreviewUrl(slideId, previewVersion);
}

function slidePreviewUrl(slideId, previewVersion = "") {
  const base = `/api/projects/${encodeURIComponent(activeProject)}/slides/${slideId}/preview`;
  const version = String(previewVersion || "").trim();
  return version ? `${base}?v=${encodeURIComponent(version)}` : base;
}

const generationPhaseLabels = {
  scaffold: "准备页面结构",
  structure: "准备页面结构",
  draft: "生成页面内容",
  compose: "生成页面内容",
  content: "生成页面内容",
  refine: "优化页面效果",
  polish: "优化页面效果",
  qa: "检查页面",
  check: "检查页面",
  review: "检查页面",
};

function userFacingGenerationPhase(value) {
  const key = String(value || "").trim().toLowerCase();
  return generationPhaseLabels[key] || "";
}

function currentPreviewMatches(slideId, url) {
  if (!svgPreview) return false;
  if (svgPreview.dataset.project !== activeProject) return false;
  if (svgPreview.dataset.slide !== String(slideId)) return false;
  const currentSrc = svgPreview.getAttribute("src") || "";
  if (!currentSrc) return false;
  if (currentSrc === url) return true;
  try {
    return new URL(currentSrc, window.location.href).href === new URL(url, window.location.href).href;
  } catch {
    return false;
  }
}

function slideGenerationPendingMessage(slide, slideId) {
  if (slideIsQueuedForGeneration(slideId)) return "等待中";
  if (slideHasActiveServerGenerationPhase(slide)) return "生成中";
  if (slide?.status === "generating" && isCurrentTabGeneratingSlide(slideId)) return "生成中";
  return "";
}

function slideGenerationPendingMessageDetailed(slide, slideId) {
  if (slideIsQueuedForGeneration(slideId)) return "等待生成";
  if (slide?.status !== "generating") return "";
  const blockTotal = Number(slide?.block_total || 0);
  const rawCompleted = Number(slide?.block_completed || 0);
  const blockCompleted = Number.isFinite(rawCompleted) ? rawCompleted : 0;
  const phase = String(slide?.generation_phase || "").trim();
  const label = String(slide?.current_block_label || "").trim();
  if (Number.isFinite(blockTotal) && blockTotal > 0) {
    const bounded = Math.max(0, Math.min(blockTotal, blockCompleted));
    const phaseLabel = userFacingGenerationPhase(phase) || userFacingGenerationPhase(label) || "正在生成页面";
    return `生成中：${phaseLabel}（${bounded}/${blockTotal}）`;
  }
  return slideGenerationPendingMessage(slide, slideId);
}

function missingSlidePreviewMessage(slide, slideId) {
  const promptText = slidePromptForUi(slide, slideId).trim();
  const waitingForPrompt = (slide?.status === "waiting_prompt" && !promptText) || (slide && ("prompt" in slide) && !promptText);
  const pendingMessage = slideGenerationPendingMessageDetailed(slide, slideId);
  const generationError = slideGenerationError(slide);
  if (slideIsGeneratingForUi(slide)) return pendingMessage || "生成中";
  if (waitingForPrompt) return `第 ${slideId} 页还没有提示词。请先填写本页提示词，再生成页面。`;
  if (pendingMessage) return pendingMessage;
  if (generationError) {
    const cleanGenerationError = compactSentenceEnd(generationError);
    return `第 ${slideId} 页自动生成失败：${cleanGenerationError}。请点“生成本页”重试。`;
  }
  if (autoGenerationRunning || isApiAutoMode()) return `第 ${slideId} 页还没有生成。请点“生成本页”开始自动生成。`;
  return `第 ${slideId} 页还没有生成。请把交接内容发给助手，完成后回到这里刷新。`;
}

function currentPageActionMessage(current) {
  const pageState = userFacingSlideState(current);
  if (!current) return "未生成";
  if (pageState.key === "generated") return "本页已生成";
  if (pageState.key === "waiting") return "等待中";
  if (pageState.key === "generating") return "生成中";
  if (pageState.key === "failed") return "生成失败，可重新生成";
  return "未生成";
}

function renderCurrentPageActionHint() {
  if (!currentPageActionHint) return;
  const current = selectedSlideState();
  const generateBlocker = activeProject ? currentPageGenerateBlocker(current) : "";
  currentPageActionHint.textContent = generateBlocker || currentPageActionMessage(current);
  const pageState = userFacingSlideState(current);
  const isWaitingBlocker = generateBlocker === "等待中";
  currentPageActionHint.classList.toggle("failed", pageState.key === "failed" || (Boolean(generateBlocker) && !isWaitingBlocker));
  currentPageActionHint.classList.toggle("passed", pageState.key === "generated");
  currentPageActionHint.classList.toggle("waiting", pageState.key === "not_generated" || pageState.key === "waiting" || isWaitingBlocker);
}

function syncCurrentPagePrompt() {
  if (!pagePromptPanel || !pagePromptTitle || !currentPageType || !currentPagePrompt) return;
  const current = selectedSlideState();
  const hasCurrent = Boolean(current);
  pagePromptTitle.textContent = hasCurrent ? `第 ${selectedSlide} 页` : "还没有页面";
  currentPageType.disabled = !activeProject;
  if (currentContentHandling) currentContentHandling.disabled = !activeProject;
  if (currentPageStyle) currentPageStyle.disabled = !activeProject;
  currentPagePrompt.disabled = !activeProject;
  if (currentPageIterationNote) currentPageIterationNote.disabled = !activeProject;
  if (!hasCurrent) {
    const bootstrapDraft = readLocalPageDraft(selectedSlide);
    setCurrentPageTypeValue(bootstrapDraft?.page_type);
    setCurrentContentHandlingValue(bootstrapDraft?.content_handling);
    setCurrentPageStyleValue(bootstrapDraft?.page_style);
    currentPagePrompt.value = bootstrapDraft?.prompt || "";
    if (currentPageIterationNote) currentPageIterationNote.value = "";
    renderCurrentPageActionHint();
    renderPromptSummaryCard();
    refreshPageOptionsBadge();
    return;
  }
  const localDraft = readLocalPageDraft(selectedSlide);
  if (localDraft && localDraft.dirty) {
    setCurrentPageTypeValue(localDraft.page_type);
    setCurrentContentHandlingValue(localDraft.content_handling);
    setCurrentPageStyleValue(localDraft.page_style);
    currentPagePrompt.value = localDraft.prompt || "";
  } else {
    setCurrentPageTypeValue(current.page_type);
    setCurrentContentHandlingValue(current.content_handling);
    setCurrentPageStyleValue(current.page_style);
    currentPagePrompt.value = current.prompt || "";
  }
  renderCurrentPageActionHint();
  renderPromptSummaryCard();
  refreshPageOptionsBadge();
}

function pageStatusLabel(slide) {
  return userFacingSlideState(slide).label;
}

function isSinglePageDeck(status = latestStatus) {
  const deckType = String(status?.deck_type || "").trim();
  const workflowMode = String(status?.workflow_mode || "").trim();
  return deckType === "single" && workflowMode === "single_page";
}

function isMissingProjectStatus(status = latestStatus) {
  return status?.project_status === "missing";
}

function isPagewiseWorkflowStatus(status = latestStatus) {
  const mode = String(status?.workflow_mode || currentWorkflowMode() || "").trim();
  return mode === "prompt_deck" || mode === "single_page" || mode === "document_deck";
}

