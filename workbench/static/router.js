// router.js — C13-0 拆分：视图路由 / 工作流模式（由 app.js 原样迁移）

function showCreateWorkspace() {
  setWorkbenchView("new_task");
  if (createWorkspace) createWorkspace.classList.remove("hidden");
}

let activeWorkbenchView = "mode_select";
let modelConfigReturnView = "mode_select";

function setWorkbenchView(view) {
  const nextView = ["mode_select", "task_center", "new_task", "task_detail", "model_config"].includes(view) ? view : "mode_select";
  const createVisible = nextView === "mode_select" || nextView === "new_task";
  if (appShell) {
    if (nextView !== "task_detail" && appShell.classList.contains("setup-collapsed")) {
      setSetupCollapsed(false, false);
    }
    appShell.classList.toggle("mode-select-view", nextView === "mode_select");
    appShell.classList.toggle("task-center-view", nextView === "task_center");
    appShell.classList.toggle("new-task-view", nextView === "new_task");
    appShell.classList.toggle("task-detail-view", nextView === "task_detail");
    appShell.classList.toggle("model-config-view", nextView === "model_config");
  }
  if (modelConfigView) modelConfigView.classList.toggle("hidden", nextView !== "model_config");
  if (modeSelectPanel) modeSelectPanel.classList.toggle("hidden", !createVisible);
  if (taskCenterPanel) taskCenterPanel.classList.toggle("hidden", nextView !== "task_center");
  if (createWorkspace) createWorkspace.classList.toggle("hidden", !createVisible);
  if (setupContent) {
    setupContent.classList.toggle("hidden", !createVisible);
    setupContent.setAttribute("aria-hidden", String(!createVisible));
  }
  if (taskDetailShell) taskDetailShell.classList.toggle("hidden", nextView !== "task_detail");
  if (nextView !== "task_detail") setInspectorOpen(false, false);
  else {
    setInspectorOpen(true, false);
    applyDetailBreakpoint();
  }
  if (toggleSetupPanel) toggleSetupPanel.classList.toggle("hidden", nextView !== "task_detail");
  if (newTaskButton) {
    const active = nextView === "mode_select" || nextView === "new_task";
    newTaskButton.classList.toggle("active", active);
    newTaskButton.setAttribute("aria-current", active ? "page" : "false");
  }
  if (showTaskCenter) {
    const active = nextView === "task_center";
    showTaskCenter.classList.toggle("active", active);
    showTaskCenter.setAttribute("aria-current", active ? "page" : "false");
  }
  if (openPreferencePopoverRail) {
    const active = nextView === "model_config";
    openPreferencePopoverRail.classList.toggle("active", active);
    openPreferencePopoverRail.setAttribute("aria-current", active ? "page" : "false");
  }
  if (nextView === "mode_select" || nextView === "new_task") createWorkspace?.scrollTo({ top: 0, left: 0 });
  if (nextView === "task_center") taskCenterPanel?.scrollTo({ top: 0, left: 0 });
  activeWorkbenchView = nextView;
  updateGenerationModeUi();
}


function currentWorkflowMode() {
  return workflowMode?.value || "prompt_deck";
}

function renderSelectedWorkflowMode(mode = currentWorkflowMode()) {
  const config = WORKFLOW_CONFIG[mode] || WORKFLOW_CONFIG.prompt_deck;
  if (composerModeTitle) composerModeTitle.textContent = config.label;
  if (composerModeDetail) composerModeDetail.textContent = config.detail || "";
}

function setWorkflowMode(mode, updatePrompt = true) {
  const nextMode = WORKFLOW_CONFIG[mode] ? mode : "prompt_deck";
  const config = WORKFLOW_CONFIG[nextMode];
  if (workflowMode) workflowMode.value = nextMode;
  modeOptions.forEach((option) => {
    const active = option.dataset.workflowMode === nextMode;
    option.classList.toggle("active", active);
    option.setAttribute("aria-selected", String(active));
    option.setAttribute("aria-pressed", String(active));
  });
  deckType.value = config.deckType || "single";
  pageCount.value = config.pageCount || "1";
  deckType.disabled = true;
  pageCount.disabled = true;
  if (documentSourceField) {
    documentSourceField.classList.toggle("hidden", nextMode !== "document_deck");
  }
  createTask.textContent = config.createLabel || "开始逐页生成";
  if (updatePrompt) promptInput.value = config.prompt;
  createTask.disabled = Boolean(config.disabledCreate);
  renderSelectedWorkflowMode(nextMode);
  updateGenerationModeUi();
  updateButtons(Boolean(activeProject));
  renderNextAction(latestStatus);
  renderWorkflowMap(latestStatus);
}
