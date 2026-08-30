// app.js — C13-0 拆分后入口：事件绑定 / C09 交互 / 初始化（原文件尾部区域）

modeOptions.forEach((option) => {
  option.addEventListener("click", () => {
    const mode = option.dataset.workflowMode || "prompt_deck";
    runAction(option, async () => {
      await selectWorkflowMode(mode);
      saveCreationDraft();
    });
  });
});

if (showTaskCenter) {
  showTaskCenter.addEventListener("click", () => runAction(showTaskCenter, showTaskCenterView));
}
if (newTaskButton) {
  newTaskButton.addEventListener("click", () => runAction(newTaskButton, startNewTask));
}
if (changeWorkflowMode) {
  changeWorkflowMode.addEventListener("click", () => runAction(changeWorkflowMode, showModeSelectView));
}

deckType.addEventListener("change", () => {
  if (deckType.value === "single") {
    pageCount.value = "1";
    pageCount.disabled = true;
  } else {
    pageCount.disabled = false;
      if (pageCount.value === "1") pageCount.value = "3";
  }
  renderWorkflowMap(latestStatus);
  renderNextAction(latestStatus);
  saveCreationDraft();
});

pageCount.addEventListener("change", saveCreationDraft);
sceneSelect?.addEventListener("change", saveCreationDraft);
targetPageCount?.addEventListener("change", saveCreationDraft);
styleProfile.addEventListener("change", saveCreationDraft);
templateMode.addEventListener("change", saveCreationDraft);
generationProgressiveSetting?.addEventListener("change", () => {
  saveProgressiveVisualizationSetting().catch((error) => {
    appendLog(error.message || String(error));
  });
});
if (documentFileInput) {
  documentFileInput.addEventListener("change", (event) => {
    void WorkbenchAppStateOrchestration.addDocumentFiles(event.target.files).catch((error) => {
      appendLog(error.message || String(error));
    });
  });
}
if (clearDocumentUploads) {
  clearDocumentUploads.addEventListener("click", () => {
    WorkbenchAppStateOrchestration.clearStagedDocumentSources();
  });
}
if (documentDropZone) {
  documentDropZone.addEventListener("click", () => documentFileInput?.click());
  documentDropZone.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    documentFileInput?.click();
  });
  documentDropZone.addEventListener("dragover", (event) => event.preventDefault());
  documentDropZone.addEventListener("dragleave", (event) => event.preventDefault());
  documentDropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    void WorkbenchAppStateOrchestration.addDocumentFiles(event.dataTransfer.files).catch((error) => {
      appendLog(error.message || String(error));
    });
  });
}
promptInput.addEventListener("input", saveCreationDraft);
taskCenterSearch?.addEventListener("input", () => renderTaskList(allTasks));
taskCenterFilter?.addEventListener("change", () => renderTaskList(allTasks));
taskBatchDelete?.addEventListener("click", () => runAction(taskBatchDelete, purgeSelectedTasks));

fitPreview.addEventListener("click", () => {
  setPreviewMode("fit");
});

previewZoom.addEventListener("change", () => {
  const scale = Number(previewZoom.value || "1");
  setPreviewMode("manual", scale);
});

resetPreview.addEventListener("click", () => {
  setPreviewMode("fit");
});

previewStageShell?.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    stepPreviewZoom(event.deltaY < 0 ? 1 : -1);
  },
  { passive: false },
);

fullscreenPreview.addEventListener("click", async () => {
  if (document.fullscreenElement === previewZone) {
    await document.exitFullscreen();
  } else if (previewZone.requestFullscreen) {
    await previewZone.requestFullscreen();
  }
  updateFullscreenButton();
  if (previewState.mode === "fit") applyPreviewScale();
});

startSlideshow?.addEventListener("click", () => runAction(startSlideshow, openSlideshow));
slideshowPrev?.addEventListener("click", () => stepSlideshow(-1));
slideshowNext?.addEventListener("click", () => stepSlideshow(1));
closeSlideshow?.addEventListener("click", () => runAction(closeSlideshow, closeSlideshowOverlay));
document.addEventListener("keydown", (event) => {
  if (!slideshowOverlay || slideshowOverlay.classList.contains("hidden")) return;
  if (event.key === "Escape") {
    closeSlideshowOverlay();
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    stepSlideshow(-1);
  } else if (event.key === "ArrowRight" || event.key === " " || event.key === "Enter") {
    event.preventDefault();
    stepSlideshow(1);
  }
});

window.addEventListener("resize", handleResize);

document.addEventListener("fullscreenchange", () => {
  updateFullscreenButton();
  if (slideshowOverlay && document.fullscreenElement !== slideshowOverlay && !slideshowOverlay.classList.contains("hidden")) {
    slideshowOverlay.classList.add("hidden");
    slideshowFrame?.removeAttribute("src");
  }
  if (previewState.mode === "fit") applyPreviewScale();
});

svgPreview.addEventListener("load", () => {
  if (!svgPreview.getAttribute("src") || !svgPreview.dataset.project || !svgPreview.dataset.slide) return;
  const current = selectedSlideState();
  if (!slideIsDisplayable(current)) return;
  const loadedSlide = previewLoadFallbackSlide || selectedSlide;
  if (!verifyLoadedPreviewFrame()) return;
  clearPreviewLoadFallback();
  hideLoadedPreviewBusy(loadedSlide, true);
  applyPreviewScale();
});

toggleSetupPanel.addEventListener("click", () => {
  const next = !appShell.classList.contains("setup-collapsed");
  setSetupCollapsed(next);
});

if (toggleAdvancedPanel) {
  toggleAdvancedPanel.addEventListener("click", () => {
    const expanded = !advancedPanel.classList.contains("expanded");
    setPanelExpanded(advancedPanel, toggleAdvancedPanel, expanded);
  });
}

toggleLogPanel?.addEventListener("click", () => {
  const expanded = !logPanel.classList.contains("expanded");
  setPanelExpanded(logPanel, toggleLogPanel, expanded);
});

toggleQaPanel?.addEventListener("click", () => {
  const expanded = !qaPanel.classList.contains("expanded");
  setPanelExpanded(qaPanel, toggleQaPanel, expanded);
});

toggleRevisionPanel?.addEventListener("click", () => {
  const expanded = !revisionPanel.classList.contains("expanded");
  setPanelExpanded(revisionPanel, toggleRevisionPanel, expanded);
});

createTask.addEventListener("click", () => runAction(createTask, createCodexTask));
slideReviewScoreGroup?.querySelectorAll(".review-score-btn").forEach((button) => {
  button.addEventListener("click", () => {
    setReviewScoreSelection(Number(button.dataset.score || 0));
  });
});
saveSlideReview?.addEventListener("click", () => runAction(saveSlideReview, submitSlideReview));
if (showNewTaskComposer) {
  showNewTaskComposer.addEventListener("click", () => runAction(showNewTaskComposer, startNewTask));
}
if (nextActionButton) {
  nextActionButton.addEventListener("click", () => runAction(nextActionButton, executeRecommendedAction));
}
if (autoGeneratePage) {
  autoGeneratePage.addEventListener("click", () =>
    runAction(autoGeneratePage, () => autoGenerateCurrentSlide({ wait_for_completion: false })),
  );
}
if (autoGenerateMissingPages) {
  autoGenerateMissingPages.addEventListener("click", () =>
    runAction(autoGenerateMissingPages, autoGenerateMissingPagesBatch),
  );
}
if (previewRetryButton) {
  // Legacy contract marker for frontend state tests: runAction(previewRetryButton, autoGenerateCurrentSlide)
  previewRetryButton.addEventListener("click", () => runAction(previewRetryButton, autoGenerateCurrentSlide));
}
if (repairCurrentPage) {
  repairCurrentPage.addEventListener("click", () => runAction(repairCurrentPage, repairCurrentSlideAction));
}
if (restorePreviousRevision) {
  restorePreviousRevision.addEventListener("click", () => runAction(restorePreviousRevision, restorePreviousSlideRevision));
}
collapseInspector?.addEventListener("click", () => setInspectorOpen(false, false));
expandInspector?.addEventListener("click", () => setInspectorOpen(true, false));
inspectorTabs.forEach((button) => {
  button.addEventListener("click", () => setInspectorTab(button.dataset.inspectorTab));
});
if (downloadCurrentPage) {
  downloadCurrentPage.addEventListener("click", () => runAction(downloadCurrentPage, exportCurrentSlide));
}
if (deleteCurrentPage) {
  deleteCurrentPage.addEventListener("click", () => runAction(deleteCurrentPage, deleteCurrentSlide));
}
if (currentPagePrompt) {
  currentPagePrompt.addEventListener("input", () => {
    captureCurrentPageDraft(true);
    updateButtons(Boolean(activeProject));
    renderCurrentPageActionHint();
    renderPromptSummaryCard();
  });
}
if (currentPageType) {
  currentPageType.addEventListener("change", () => {
    captureCurrentPageDraft(true);
    updateButtons(Boolean(activeProject));
    renderCurrentPageActionHint();
  });
}
if (currentContentHandling) {
  currentContentHandling.addEventListener("change", () => {
    captureCurrentPageDraft(true);
    updateButtons(Boolean(activeProject));
    renderCurrentPageActionHint();
    refreshPageOptionsBadge();
  });
}
if (currentPageStyle) {
  currentPageStyle.addEventListener("change", () => {
    captureCurrentPageDraft(true);
    updateButtons(Boolean(activeProject));
    renderCurrentPageActionHint();
    refreshPageOptionsBadge();
  });
}
if (userBlockerAction) {
  userBlockerAction.addEventListener("click", () =>
    runAction(userBlockerAction, async () => {
      const action = userBlockerAction.dataset.action || "";
      if (action === "repair_slide") {
        const slide = Number(userBlockerAction.dataset.slide || selectedSlide || 1);
        await focusSlideContext(slide, { scroll: true });
        if (isApiAutoMode()) {
          await autoGenerateCurrentSlide();
          return;
        }
        await repairCurrentSlide();
        return;
      }
      if (action === "repair_budget") {
        const slide = Number(userBlockerAction.dataset.slide || selectedSlide || 1);
        await focusSlideContext(slide, { scroll: true });
        await repairCurrentSlide();
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
      if (action === "open_preferences") {
        openModelConfigView();
        return;
      }
      if (action === "manual_review") {
        await openQaEvidencePanel();
        return;
      }
      if (action) await executeRecommendedAction();
    }),
  );
}
if (hideResumeChooser) {
  hideResumeChooser.addEventListener("click", () => renderResumeChooser([]));
}
refreshStatus.addEventListener("click", () =>
  runAction(refreshStatus, async () => {
    await loadStatus();
    await refreshCurrentPreview();
    await loadRevisions();
    await loadQaReport();
  }),
);
refreshPreview.addEventListener("click", () => runAction(refreshPreview, refreshCurrentPreview));
regenSlide?.addEventListener("click", () => runAction(regenSlide, regenerateCurrentSlide));
if (generatePacket) {
  generatePacket.addEventListener("click", () =>
    runAction(generatePacket, async () => {
      await generatePacketForSlide(selectedSlide);
    }),
  );
}
repairSlide?.addEventListener("click", () => runAction(repairSlide, repairCurrentSlideAction));
qaSlide?.addEventListener("click", () => runAction(qaSlide, qaCurrentSlide));
exportDeck?.addEventListener("click", () => runAction(exportDeck, handleExportDeckClick));
if (freshReleaseSafe) {
  freshReleaseSafe.addEventListener("click", () => runAction(freshReleaseSafe, () => runFreshFinalize("release-safe")));
}
if (freshPremium) {
  freshPremium.addEventListener("click", () => runAction(freshPremium, () => runFreshFinalize("premium")));
}
if (refreshRevisions) {
  refreshRevisions.addEventListener("click", () => runAction(refreshRevisions, loadRevisions));
}
if (refreshQaReport) {
  refreshQaReport.addEventListener("click", () => runAction(refreshQaReport, loadQaReport));
}
if (appendSlideFromList) {
  appendSlideFromList.addEventListener("click", () => runAction(appendSlideFromList, appendSlide));
}
if (insertSlideAfterCurrent) {
  insertSlideAfterCurrent.addEventListener("click", () => runAction(insertSlideAfterCurrent, insertSlideAfterSelected));
}
openPreferencePopover?.addEventListener("click", () => openModelConfigView());
openPreferencePopoverRail?.addEventListener("click", () => openModelConfigView());
closePreferencePopover?.addEventListener("click", () => closeModelConfigView());
browseTemplates?.addEventListener("click", () => runAction(browseTemplates, openTemplateGallery));
modelSubtabButtons.forEach((button) => {
  button.addEventListener("click", () => setModelConfigTab(button.dataset.modelTab));
});
addConnectionButton?.addEventListener("click", () => {
  selectedConnectionId = "";
  renderConnectionList(latestConnections);
  openConnectionForm(null);
});
cancelConnectionFormButton?.addEventListener("click", closeConnectionForm);
saveConnectionButton?.addEventListener("click", () => runAction(saveConnectionButton, saveConnection));
replaceKeyButton?.addEventListener("click", () => {
  // 更换密钥：只展开输入框，旧密钥仍留在服务端，直到保存新值覆盖。
  connectionApiKeyInput?.classList.remove("hidden");
  connectionApiKeyInput?.focus();
});
deleteConnectionButton?.addEventListener("click", () => runAction(deleteConnectionButton, deleteSelectedConnection));
toggleConnectionEnabledButton?.addEventListener("click", () => runAction(toggleConnectionEnabledButton, toggleSelectedConnectionEnabled));
duplicateConnectionButton?.addEventListener("click", () => runAction(duplicateConnectionButton, duplicateSelectedConnection));
refreshModelsButton?.addEventListener("click", () => runAction(refreshModelsButton, () => testConnectionAndLoadModels(selectedConnectionId)));
saveRoleRoutingButton?.addEventListener("click", () => runAction(saveRoleRoutingButton, saveRoleRouting));
connectionListEl?.addEventListener("click", (event) => {
  const selectButton = event.target.closest("[data-connection-select]");
  if (selectButton) selectConnection(selectButton.dataset.connectionSelect);
});
if (collapsedCreateTask) {
  collapsedCreateTask.addEventListener("click", () => runAction(collapsedCreateTask, startNewTask));
}

// ===== C09 任务详情页 v2.1 交互（设计事实源：docs/product/pagewise-generation/prototypes/task-detail-v2.1.html） =====
const detailSlideRail = document.getElementById("detailSlideRail");
const collapseSlideRail = document.getElementById("collapseSlideRail");
const morePageActions = document.getElementById("morePageActions");
const morePageActionsMenu = document.getElementById("morePageActionsMenu");
const pageOptionsToggle = document.getElementById("pageOptionsToggle");
const pageOptionsPopover = document.getElementById("pageOptionsPopover");
const pageOptionsBadge = document.getElementById("pageOptionsBadge");
const promptSummaryCard = document.getElementById("promptSummaryCard");
const promptSummaryPreview = document.getElementById("promptSummaryPreview");
const promptSummaryCount = document.getElementById("promptSummaryCount");
const promptEditor = document.getElementById("promptEditor");
const promptEditorTitle = document.getElementById("promptEditorTitle");
const promptEditorCount = document.getElementById("promptEditorCount");
const promptEditorCancel = document.getElementById("promptEditorCancel");
const promptEditorDone = document.getElementById("promptEditorDone");
const previewShowVersions = document.getElementById("previewShowVersions");
let promptEditorSnapshot = "";

function renderPromptSummaryCard() {
  if (!promptSummaryPreview || !promptSummaryCount || !currentPagePrompt) return;
  const text = String(currentPagePrompt.value || "");
  promptSummaryPreview.textContent = text || (activeProject ? "还没有提示词，点击填写本页内容。" : "选择页面后显示本页提示词。");
  promptSummaryPreview.classList.toggle("empty", !text);
  promptSummaryCount.textContent = text ? `共 ${text.length} 字` : "";
  if (promptEditorCount) promptEditorCount.textContent = `${text.length} 字`;
}

function refreshPageOptionsBadge() {
  if (!pageOptionsBadge) return;
  const changed =
    (currentContentHandling && currentContentHandling.value !== "polish") ||
    (currentPageStyle && currentPageStyle.value !== "business_simple");
  pageOptionsBadge.classList.toggle("hidden", !changed);
}

function openPromptEditor() {
  if (!promptEditor || !currentPagePrompt) return;
  promptEditorSnapshot = String(currentPagePrompt.value || "");
  if (promptEditorTitle) {
    promptEditorTitle.textContent = selectedSlide ? `本页提示词 · 第 ${slideNoById(selectedSlide)} 页` : "本页提示词";
  }
  if (promptEditorCount) promptEditorCount.textContent = `${promptEditorSnapshot.length} 字`;
  promptEditor.classList.remove("hidden");
  currentPagePrompt.focus();
  currentPagePrompt.setSelectionRange(0, 0);
  currentPagePrompt.scrollTop = 0;
}

function closePromptEditor(restoreSnapshot) {
  if (!promptEditor || !currentPagePrompt) return;
  if (restoreSnapshot && currentPagePrompt.value !== promptEditorSnapshot) {
    currentPagePrompt.value = promptEditorSnapshot;
    // 回滚后重新走 input 链路，让本地草稿与摘要卡保持一致。
    currentPagePrompt.dispatchEvent(new Event("input", { bubbles: true }));
  }
  promptEditor.classList.add("hidden");
  renderPromptSummaryCard();
}

promptSummaryCard?.addEventListener("click", openPromptEditor);
promptEditorDone?.addEventListener("click", () => closePromptEditor(false));
promptEditorCancel?.addEventListener("click", () => closePromptEditor(true));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && promptEditor && !promptEditor.classList.contains("hidden")) {
    closePromptEditor(true);
  }
});

collapseSlideRail?.addEventListener("click", () => {
  const collapsed = detailSlideRail?.classList.toggle("rail-min");
  collapseSlideRail.setAttribute("aria-expanded", String(!collapsed));
  collapseSlideRail.title = collapsed ? "展开页面列表" : "收起页面列表";
});

function closeDetailPopovers(except) {
  if (except !== "more") {
    morePageActionsMenu?.classList.add("hidden");
    morePageActions?.setAttribute("aria-expanded", "false");
  }
  if (except !== "options") {
    pageOptionsPopover?.classList.add("hidden");
    pageOptionsToggle?.setAttribute("aria-expanded", "false");
  }
}

morePageActions?.addEventListener("click", (event) => {
  event.stopPropagation();
  closeDetailPopovers("more");
  const open = morePageActionsMenu?.classList.toggle("hidden") === false;
  morePageActions.setAttribute("aria-expanded", String(open));
});
pageOptionsToggle?.addEventListener("click", (event) => {
  event.stopPropagation();
  closeDetailPopovers("options");
  const open = pageOptionsPopover?.classList.toggle("hidden") === false;
  pageOptionsToggle.setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (event) => {
  if (morePageActionsMenu && !morePageActionsMenu.classList.contains("hidden") && !morePageActionsMenu.contains(event.target) && event.target !== morePageActions) {
    closeDetailPopovers();
  }
  if (pageOptionsPopover && !pageOptionsPopover.classList.contains("hidden") && !pageOptionsPopover.contains(event.target) && event.target !== pageOptionsToggle) {
    closeDetailPopovers();
  }
});
deleteCurrentPage?.addEventListener("click", () => closeDetailPopovers());

if (currentPageIterationNote) {
  const resizeIterationNote = () => {
    currentPageIterationNote.style.height = "auto";
    currentPageIterationNote.style.height = `${Math.min(currentPageIterationNote.scrollHeight, 120)}px`;
  };
  currentPageIterationNote.addEventListener("input", resizeIterationNote);
  currentPageIterationNote.addEventListener("keydown", (event) => {
    // 仅 Ctrl+Enter 提交，避免输入法确认误触重新生成。
    if (event.key === "Enter" && event.ctrlKey && autoGeneratePage && !autoGeneratePage.disabled) {
      event.preventDefault();
      autoGeneratePage.click();
    }
  });
}

previewShowVersions?.addEventListener("click", () => {
  setInspectorOpen(true, false);
  setInspectorTab("versions");
});

// 窄窗口自动收起右栏，避免三栏挤压画布（与 v2.1 原型断点一致）。
function applyDetailBreakpoint() {
  if (!appShell?.classList.contains("task-detail-view")) return;
  if (window.innerWidth < 1200 && !taskDetailShell?.classList.contains("inspector-collapsed")) {
    setInspectorOpen(false, false);
  }
}
window.addEventListener("resize", applyDetailBreakpoint);

loadPreviewPrefs();
loadUiPrefs();
loadCreationDraft();
loadGenerationSettings().catch((error) => {
  appendLog(error.message || String(error));
});
loadConnections()
  .then(() => loadRoleRouting())
  .catch((error) => {
    appendLog(error.message || String(error));
  });
updateButtons(false);
updateCollapsedSummary();
updateFullscreenButton();
applyPreviewScale();
renderSlideReviewPanel();
loadWorkbenchSession().catch((error) => {
  appendLog(error.message || String(error));
});
