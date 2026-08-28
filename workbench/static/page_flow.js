// page_flow.js — C13-0 拆分：页面流渲染 / 追加插入 / 导出就绪 / 用户阻塞（由 app.js 原样迁移）

function renderPageStream(slides) {
  if (!pageStream) return;
  const items = Array.isArray(slides) ? slides : [];
  const allowAppend = !isSinglePageDeck(latestStatus) && !isMissingProjectStatus(latestStatus);
  if (!items.length) {
    pageStream.innerHTML = `
      <div class="page-stream-card empty-note">创建任务后会显示页面流。</div>
      ${allowAppend ? '<button class="page-stream-add" type="button">+ 新增页面</button>' : ""}
    `;
  } else {
    pageStream.innerHTML = items
      .map((slide) => {
        const slideId = Number(slide.slide_id || 0);
        const active = slideId === Number(selectedSlide) ? "active" : "";
        const pageType = pageTypeLabels[slide.page_type] || "内容页";
        const status = pageStatusLabel(slide);
        const generationError = slideGenerationError(slide);
        const previewVersion = slidePreviewVersion(slide);
        const previewUrl = pageStreamPreviewUrl(slideId, previewVersion);
        const displayable = slideIsDisplayable(slide);
        const preview = displayable
          ? `<iframe title="第 ${slideId} 页预览" src="${previewUrl}" loading="lazy" scrolling="no"></iframe>`
          : `<div class="page-stream-waiting ${generationError ? "failed" : ""}">${escapeHtml(generationError ? `生成失败：${generationError}` : slideGenerationPendingMessageDetailed(slide, slideId) || "等待 PPT 生成...")}</div>`;
        return `<article class="page-stream-card ${active}" data-slide="${slideId}">
          <button class="page-stream-select" type="button" data-slide="${slideId}" aria-label="选择第 ${slideId} 页">
            <span>第 ${slideId} 页</span>
            <strong>${escapeHtml(pageType)}</strong>
            <em>${escapeHtml(status)}</em>
          </button>
          <div class="page-stream-preview">${preview}</div>
        </article>`;
      })
      .join("");
    if (allowAppend) {
      pageStream.innerHTML += '<button class="page-stream-add" type="button">+ 新增页面</button>';
    }
  }
  pageStream.querySelectorAll(".page-stream-card[data-slide]").forEach((item) => {
    item.addEventListener("click", () => {
      void selectSlide(Number(item.dataset.slide || item.closest("[data-slide]")?.dataset.slide || 1));
    });
  });
  pageStream.querySelectorAll(".page-stream-add").forEach((button) => {
    button.addEventListener("click", () => runAction(button, appendSlide));
  });
}

function mergeLiteStatus(currentStatus, liteStatus) {
  if (!currentStatus) return liteStatus || {};
  const merged = { ...currentStatus, ...(liteStatus || {}) };
  const previousSlides = new Map((currentStatus.slides || []).map((slide) => [Number(slide.slide_id || 0), slide]));
  merged.slides = (liteStatus?.slides || []).map((slide) => {
    const previous = previousSlides.get(Number(slide.slide_id || 0)) || {};
    return { ...previous, ...slide };
  });
  return merged;
}

function updatePageStreamState(slides) {
  if (!pageStream) return;
  (Array.isArray(slides) ? slides : []).forEach((slide) => {
    const slideId = Number(slide.slide_id || 0);
    const card = pageStream.querySelector(`.page-stream-card[data-slide="${slideId}"]`);
    if (!card) return;
    card.classList.toggle("active", slideId === Number(selectedSlide));
    const stateLabel = card.querySelector(".page-stream-select em");
    if (stateLabel) stateLabel.textContent = pageStatusLabel(slide);
    const previewBox = card.querySelector(".page-stream-preview");
    if (!previewBox) return;
    const existingFrame = previewBox.querySelector("iframe");
    const generationError = slideGenerationError(slide);
    if (slideIsDisplayable(slide)) {
      const previewUrl = pageStreamPreviewUrl(slideId, slidePreviewVersion(slide));
      if (existingFrame) {
        if (existingFrame.getAttribute("src") !== previewUrl) existingFrame.setAttribute("src", previewUrl);
      } else {
        previewBox.innerHTML = `<iframe title="第 ${slideId} 页预览" src="${previewUrl}" loading="lazy" scrolling="no"></iframe>`;
      }
      return;
    }
    const message = generationError
      ? `生成失败：${generationError}`
      : slideGenerationPendingMessageDetailed(slide, slideId) || "等待 PPT 生成...";
    previewBox.innerHTML = `<div class="page-stream-waiting ${generationError ? "failed" : ""}">${escapeHtml(message)}</div>`;
  });
}

async function appendSlide() {
  if (!activeProject) throw new Error("请先打开一个任务。");
  if (isMissingProjectStatus()) throw new Error("项目文件缺失，无法新增页面。");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides`, {
    method: "POST",
    body: JSON.stringify({
      page_type: currentPageType?.value || "content",
      content_handling: normalizeContentHandling(currentContentHandling?.value),
      page_style: normalizePageStyle(currentPageStyle?.value),
      title: "",
      prompt: "",
    }),
  });
  appendLog(commandSummary("新增页面", response));
  if (!response.ok) throw new Error(response.message || "新增页面失败。");
  selectedSlide = Number(response.data?.slide_id || selectedSlide);
  await recordTaskEvent("slide_appended", { slide_id: selectedSlide });
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
  await loadQaReport();
  focusCurrentPagePromptEditor();
}

async function insertSlideAfterSelected() {
  if (!activeProject) throw new Error("请先打开一个任务。");
  if (isMissingProjectStatus()) throw new Error("项目文件缺失，无法插入页面。");
  if (isSinglePageDeck(latestStatus)) throw new Error("单页任务只能保留 1 页。需要多页 PPT 时，请新建多页任务。");
  const current = selectedSlideState();
  if (!current) throw new Error("请先选择要插入位置的页面。");
  const response = await api(`/api/projects/${encodeURIComponent(activeProject)}/slides/${selectedSlide}/insert-after`, {
    method: "POST",
    body: JSON.stringify({
      page_type: normalizeWorkbenchPageType(currentPageType?.value || current.page_type),
      content_handling: normalizeContentHandling(currentContentHandling?.value || current.content_handling),
      page_style: normalizePageStyle(currentPageStyle?.value || current.page_style),
      title: "",
      prompt: "",
    }),
  });
  appendLog(commandSummary(`在第 ${selectedSlide} 页后插入页面`, response));
  if (!response.ok) throw new Error(response.message || "插入页面失败。");
  selectedSlide = Number(response.data?.slide_id || selectedSlide + 1);
  await recordTaskEvent("insert_slide", { slide_id: selectedSlide, source: "current_page_after" });
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
  await loadQaReport();
  focusCurrentPagePromptEditor();
}

function renderExportReadiness(readiness) {
  return;
}

function exportFailureUserMessage(status) {
  const context = status?.export?.last_error_context || {};
  const contextMessage = String(context.user_facing_error || "").trim();
  return contextMessage || userFacingGenerationError(status?.export?.last_error || "");
}

function renderUserBlocker(status) {
  if (!userBlockerPanel || !userBlockerTitle || !userBlockerDetail || !userBlockerAction) return;
  const readiness = status?.export_readiness;
  const recommendedAction = status?.recommended_next_action || {};
  const reasonCode = String(recommendedAction.reason_code || "");
  const recommendedKey = String(recommendedAction.key || "");
  const recommendedLabel = String(recommendedAction.label || "").trim();
  const recommendedMessage = String(recommendedAction.user_message || recommendedAction.detail || "").trim();
  const recommendedSlideRaw = Number(recommendedAction.slide_id || 0);
  const recommendedSlide = Number.isFinite(recommendedSlideRaw) && recommendedSlideRaw > 0 ? recommendedSlideRaw : 0;
  const overloaded = readiness?.budget_overloaded_slides || [];
  const missingSlides = Array.isArray(readiness?.missing_slides)
    ? readiness.missing_slides.map(Number).filter((item) => Number.isFinite(item) && item > 0)
    : [];
  const failedSlides = Array.isArray(status?.slides)
    ? status.slides.filter((slide) => ["failed", "qa_failed"].includes(String(slide?.qa_status || "")))
    : [];
  const failedIds = failedSlides.map((slide) => Number(slide.slide_id || 0)).filter((item) => Number.isFinite(item) && item > 0);
  const exportFailed = status?.export?.status === "failed";
  const exportReviewRequired = status?.export?.status === "review_required" || status?.project_status === "export_review_required";
  let title = "";
  let detail = "";
  let action = "";
  let actionText = "";
  let actionSlide = "";

  if (status?.project_status === "missing") {
    title = "项目文件缺失";
    detail = "当前项目目录不存在，无法新增页面或继续生成。请返回任务中心重新创建任务。";
  } else if (reasonCode === "api_key_missing") {
    const targetSlide = recommendedSlide || missingSlides[0] || 0;
    const targetText = targetSlide > 0 ? `第 ${targetSlide} 页` : "当前页面";
    title = "模型配置需要处理";
    detail = recommendedMessage || `${targetText} 暂时无法生成：服务端 API Key 尚未配置，请在服务器 .env 或 Windows 环境变量中配置并重启。`;
    action = "open_preferences";
    actionText = "打开模型配置";
    actionSlide = targetSlide > 0 ? String(targetSlide) : "";
  } else if (reasonCode === "missing_slide_svg" || reasonCode === "missing_slide_prompt") {
    const targetSlide = recommendedSlide || missingSlides[0] || 0;
    title = missingSlidesTitle(missingSlides, targetSlide);
    detail =
      reasonCode === "missing_slide_prompt"
        ? recommendedMessage || "请先补充页面内容。"
        : missingSlidesBlockerDetail(missingSlides, targetSlide);
    action = recommendedKey || (reasonCode === "missing_slide_prompt" ? "edit_page_prompt" : "auto_generate");
    actionText =
      recommendedLabel ||
      (targetSlide > 0
        ? reasonCode === "missing_slide_prompt"
          ? `补充第 ${targetSlide} 页内容`
          : `生成第 ${targetSlide} 页`
        : "继续处理");
    actionSlide = targetSlide > 0 ? String(targetSlide) : "";
  } else if (reasonCode === "qa_failed_slide") {
    const targetSlide = recommendedSlide || failedIds[0] || 0;
    title = targetSlide > 0 ? `第 ${targetSlide} 页生成失败` : "生成失败";
    detail = targetSlide > 0 ? `第 ${targetSlide} 页生成失败。` : "生成失败。";
    action = recommendedKey || "repair_slide";
    actionText = recommendedLabel || (targetSlide > 0 ? `处理第 ${targetSlide} 页` : "继续处理");
    actionSlide = targetSlide > 0 ? String(targetSlide) : "";
  } else if (reasonCode === "budget_overload") {
    const targetSlide = recommendedSlide || overloaded[0] || 0;
    title = "页面内容还需精简";
    detail =
      recommendedMessage ||
      (targetSlide > 0 ? `第 ${targetSlide} 页内容偏多，请先优化后再继续。` : "页面内容偏多，请先优化后再继续。");
    action = recommendedKey || "repair_budget";
    actionText = recommendedLabel || (targetSlide > 0 ? `优化第 ${targetSlide} 页` : "优化当前页");
    actionSlide = targetSlide > 0 ? String(targetSlide) : "";
  } else if (reasonCode === "export_failed") {
    title = "生成失败";
    detail = exportFailureUserMessage(status) || "生成失败。";
    action = "repair_export_failure";
    actionText = recommendedLabel || "处理导出问题";
  } else if (reasonCode === "delivery_blocked") {
    title = "已生成，可下载";
    detail = recommendedMessage || "PPT 已生成，可下载；有检查提示时可按需重新生成。";
    action = recommendedKey || "download_pptx";
    actionText = recommendedLabel || "下载";
  } else if (missingSlides.length) {
    title = missingSlidesTitle(missingSlides);
    detail = missingSlidesBlockerDetail(missingSlides);
  } else if (failedIds.length) {
    const first = failedSlides[0];
    const firstId = Number(first?.slide_id || failedIds[0]);
    const reason = userFacingGenerationError(first?.last_error || "");
    title = `第 ${firstId} 页生成失败`;
    detail = reason ? `${slideListText(failedIds)} 生成失败。${reason}` : `${slideListText(failedIds)} 生成失败。`;
    action = "repair_slide";
    actionText = `处理第 ${firstId} 页`;
    actionSlide = String(firstId);
  } else if (overloaded.length) {
    title = "页面内容还需精简";
    detail = `${slideListText(overloaded)} 内容偏多，请先优化后再继续。`;
    action = "repair_budget";
    actionText = `优化第 ${overloaded[0]} 页`;
    actionSlide = String(overloaded[0]);
  } else if (exportFailed) {
    title = "生成失败";
    detail = exportFailureUserMessage(status) || "生成失败。";
    action = "repair_export_failure";
    actionText = "生成导出排障任务";
  } else if (exportReviewRequired) {
    title = "已生成";
    detail = userFacingGenerationError(status?.export?.last_error || "") || "已生成，可下载。";
    action = "repair_delivery_blocker";
    actionText = "继续处理";
  } else if (activeProject && readiness && !readiness.ready) {
    const reasons = Array.isArray(readiness?.reasons)
      ? readiness.reasons.map((item) => userFacingReadinessReason(item)).filter(Boolean)
      : [];
    if (reasons.length) {
      title = "暂时不能生成 PPT";
      detail = reasons.join("；");
    }
  }

  userBlockerPanel.classList.toggle("hidden", !title);
  userBlockerTitle.textContent = title || "暂时不能生成 PPT";
  userBlockerDetail.textContent = detail || "请先完成未生成页面。";
  userBlockerAction.classList.toggle("hidden", !action);
  userBlockerAction.textContent = actionText;
  userBlockerAction.dataset.action = action;
  userBlockerAction.dataset.slide = actionSlide;
}

function pagewiseProjectProgressCopy(status) {
  const slides = Array.isArray(status?.slides) ? status.slides : [];
  if (!slides.length) return projectStateText[status?.project_status] || status?.project_status || "状态未知";
  const generated = slides.filter((slide) => slideIsDisplayable(slide)).length;
  const missing = slides.find((slide) => !slideIsDisplayable(slide));
  if (missing) return `\u5df2\u751f\u6210 ${generated}/${slides.length}\uff0c\u4e0b\u4e00\u9875\u7b2c ${missing.slide_id} \u9875`;
  return `\u5df2\u751f\u6210 ${generated}/${slides.length}\uff0c\u53ef\u4ee5\u751f\u6210 PPT`;
}

function currentPageGenerationStateText() {
  const current = selectedSlideState();
  if (!current || !slideIsGeneratingForUi(current)) return "";
  return `第 ${Number(current.slide_id || selectedSlide)} 页生成中`;
}

function projectStatusLabel(value) {
  return projectStateText[value] || value || "状态未知";
}

function renderResumeChooser(projects) {
  if (!resumeChooser || !resumeProjectList) return;
  const items = Array.isArray(projects) ? projects : [];
  if (!items.length) {
    resumeChooser.classList.add("hidden");
    resumeProjectList.innerHTML = "";
    return;
  }
  resumeChooser.classList.remove("hidden");
  resumeProjectList.innerHTML = items
    .map((item) => {
      const project = String(item.project || "");
      const slideSummary = `${Number(item.has_svg_count || 0)}/${Number(item.slide_count || 0)} 页已生成`;
      const qaSummary = `${Number(item.qa_passed_count || 0)} 页已检查`;
      const updated = item.updated_at ? `更新：${item.updated_at}` : "更新：未知";
      const status = projectStatusLabel(item.project_status);
      return `<button class="resume-project-card" data-project="${project}">
        <strong>${project}</strong>
        <span>${status} · ${slideSummary} · ${qaSummary}</span>
        <small>${updated}</small>
      </button>`;
    })
    .join("");
  resumeProjectList.querySelectorAll(".resume-project-card").forEach((button) => {
    button.addEventListener("click", () => {
      const project = button.dataset.project || "";
      if (!project) return;
      runAction(button, async () => {
        await activateProject(project);
        resumeChooser.classList.add("hidden");
      });
    });
  });
}

function triState(value) {
  if (value === true || value === false) return value;
  return "unknown";
}

function renderQaEvidence(status) {
  return;
}

function qaScopeLabel(status = latestStatus) {
  const scope = String(status?.qa_scope || "unknown");
  if (scope === "deck") return "整套 QA";
  if (scope === "slide") {
    const slideId = Number(status?.checked_slide || 0);
    return slideId > 0 ? `单页 QA（第 ${slideId} 页）` : "单页 QA";
  }
  return "QA 范围未知";
}

