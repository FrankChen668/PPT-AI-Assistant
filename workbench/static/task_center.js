// task_center.js — C13-0 拆分：任务中心 / 会话 / 新建任务（由 app.js 原样迁移）

function renderTaskListInto(container, tasks, options = {}) {
  if (!container) return;
  const items = Array.isArray(tasks) ? tasks : [];
  if (!items.length) {
    container.innerHTML = `<div class="empty-note">${options.emptyText || "还没有任务。先选择一个模式开始。"}</div>`;
    return;
  }
  container.innerHTML = items
    .map((task) =>
      taskRender.renderTaskCard(task, {
        activeTaskId,
        compact: Boolean(options.compact),
        allowArchive: Boolean(options.allowArchive),
        projectStatusLabel,
      }),
    )
    .join("");
  container.querySelectorAll(".task-card-main").forEach((button) => {
    button.addEventListener("click", () => {
      const taskId = button.dataset.taskId || "";
      if (!taskId) return;
      runAction(button, async () => activateTask(taskId));
    });
  });
  container.querySelectorAll(".task-card-remove").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const taskId = button.dataset.taskMenu || "";
      if (!taskId) return;
      toggleTaskArchiveMenu(taskId);
    });
  });
  container.querySelectorAll("[data-task-delete-confirm]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const taskId = button.dataset.taskDeleteConfirm || "";
      if (!taskId) return;
      runAction(button, async () => confirmDeleteTask(taskId, button.dataset.taskTitle || ""));
    });
  });
  container.querySelectorAll("[data-task-purge-confirm]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const taskId = button.dataset.taskPurgeConfirm || "";
      if (!taskId) return;
      runAction(button, async () => confirmPurgeTask(taskId, button.dataset.taskTitle || ""));
    });
  });
}

function closeTaskArchiveMenus(exceptTaskId = "") {
  document.querySelectorAll(".task-card-menu").forEach((menu) => {
    const taskId = menu.dataset.taskMenuPanel || "";
    if (taskId === exceptTaskId) return;
    menu.classList.add("hidden");
  });
  document.querySelectorAll(".task-card-remove").forEach((button) => {
    const taskId = button.dataset.taskMenu || "";
    if (taskId === exceptTaskId) return;
    button.setAttribute("aria-expanded", "false");
  });
}

function toggleTaskArchiveMenu(taskId) {
  const menu = document.querySelector(`[data-task-menu-panel="${CSS.escape(taskId)}"]`);
  const trigger = document.querySelector(`[data-task-menu="${CSS.escape(taskId)}"]`);
  if (!menu || !trigger) return;
  const willOpen = menu.classList.contains("hidden");
  closeTaskArchiveMenus(willOpen ? taskId : "");
  menu.classList.toggle("hidden", !willOpen);
  trigger.setAttribute("aria-expanded", String(willOpen));
}

function filteredTasks(tasks) {
  const keyword = String(taskCenterSearch?.value || "").trim().toLowerCase();
  const filter = String(taskCenterFilter?.value || "all");
  return (Array.isArray(tasks) ? tasks : []).filter((task) => {
    const status = String(task?.status || "").toLowerCase();
    if (filter !== "all" && status !== filter) return false;
    if (!keyword) return true;
    const title = String(task?.title || task?.project_name || "").toLowerCase();
    const project = String(task?.project_name || "").toLowerCase();
    return title.includes(keyword) || project.includes(keyword);
  });
}

function renderTaskList(tasks) {
  const visible = filteredTasks(tasks);
  const visibleIds = new Set(visible.map((task) => String(task?.id || "")));
  [...taskCenterSelectedIds].forEach((id) => {
    if (!visibleIds.has(id)) taskCenterSelectedIds.delete(id);
  });
  renderTaskTableInto(taskList, visible, {
    emptyText: "还没有任务。点击“新建任务”开始。",
  });
  updateTaskBatchDeleteButton();
}

const taskCenterSelectedIds = new Set();

function updateTaskBatchDeleteButton() {
  if (!taskBatchDelete) return;
  const count = taskCenterSelectedIds.size;
  taskBatchDelete.classList.toggle("hidden", count === 0);
  taskBatchDelete.textContent = `删除所选（${count}）`;
}

function renderTaskTableInto(container, tasks, options = {}) {
  if (!container) return;
  const items = Array.isArray(tasks) ? tasks : [];
  if (!items.length) {
    container.innerHTML = `<div class="empty-note">${options.emptyText || "还没有任务。"}</div>`;
    return;
  }
  container.innerHTML =
    taskRender.renderTaskTableHeader({ selectable: true }) +
    items
      .map((task) =>
        taskRender.renderTaskRow(task, {
          activeTaskId,
          selectable: true,
          selectedIds: taskCenterSelectedIds,
          projectStatusLabel,
        }),
      )
      .join("");
  const syncSelectAll = () => {
    const selectAll = container.querySelector("[data-task-select-all]");
    if (!selectAll) return;
    selectAll.checked = items.length > 0 && items.every((task) => taskCenterSelectedIds.has(String(task?.id || "")));
  };
  syncSelectAll();
  container.querySelector("[data-task-select-all]")?.addEventListener("change", (event) => {
    const checked = Boolean(event.target.checked);
    items.forEach((task) => {
      const id = String(task?.id || "");
      if (!id) return;
      if (checked) taskCenterSelectedIds.add(id);
      else taskCenterSelectedIds.delete(id);
    });
    container.querySelectorAll("[data-task-select]").forEach((input) => {
      input.checked = checked;
    });
    updateTaskBatchDeleteButton();
  });
  container.querySelectorAll("[data-task-select]").forEach((input) => {
    input.addEventListener("change", () => {
      const id = input.dataset.taskSelect || "";
      if (!id) return;
      if (input.checked) taskCenterSelectedIds.add(id);
      else taskCenterSelectedIds.delete(id);
      syncSelectAll();
      updateTaskBatchDeleteButton();
    });
  });
  container.querySelectorAll("[data-task-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const taskId = button.dataset.taskOpen || "";
      if (!taskId) return;
      runAction(button, async () => activateTask(taskId));
    });
  });
  container.querySelectorAll("[data-task-purge-confirm]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const taskId = button.dataset.taskPurgeConfirm || "";
      if (!taskId) return;
      runAction(button, async () => confirmPurgeTask(taskId, button.dataset.taskTitle || ""));
    });
  });
}

async function purgeSelectedTasks() {
  const ids = [...taskCenterSelectedIds];
  if (!ids.length) return;
  const confirmed = window.confirm(
    `确定永久删除所选 ${ids.length} 个任务吗？\n\n任务记录和项目文件会被彻底删除，无法恢复。`,
  );
  if (!confirmed) return;
  const failures = [];
  for (const taskId of ids) {
    const response = await api(`/api/workbench/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
    if (!response.ok) {
      failures.push(response.message || taskId);
      continue;
    }
    taskCenterSelectedIds.delete(taskId);
    if (activeTaskId === taskId) activeTaskId = "";
  }
  await loadTaskList();
  if (failures.length) throw new Error(`有 ${failures.length} 个任务删除失败：${failures[0]}`);
  appendLog(`已永久删除 ${ids.length} 个任务。`);
}

function renderRecentTaskList(tasks) {
  const recent = Array.isArray(tasks) ? tasks.slice(0, 5) : [];
  renderTaskListInto(recentTaskList, recent, {
    emptyText: "还没有任务。先选择一个模式开始。",
    compact: true,
    allowArchive: true,
  });
}

async function deleteTask(taskId) {
  const response = await api(`/api/workbench/tasks/${encodeURIComponent(taskId)}/delete`, { method: "POST" });
  if (!response.ok) throw new Error(response.message || "删除任务失败。");
  if (activeTaskId === taskId) activeTaskId = "";
  appendLog("任务已删除。");
  await loadTaskList();
}

async function confirmDeleteTask(taskId, title = "") {
  closeTaskArchiveMenus();
  const label = title ? `“${title}”` : "这个任务";
  const confirmed = window.confirm(`确定删除${label}吗？\n\n任务会从列表移除，项目文件会移到本地归档区。`);
  if (!confirmed) return;
  await deleteTask(taskId);
}

async function purgeTask(taskId) {
  const response = await api(`/api/workbench/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(response.message || "永久删除任务失败。");
  if (activeTaskId === taskId) activeTaskId = "";
  appendLog("任务已永久删除。");
  await loadTaskList();
}

async function confirmPurgeTask(taskId, title = "") {
  closeTaskArchiveMenus();
  const label = title ? `“${title}”` : "这个任务";
  const confirmed = window.confirm(`确定永久删除${label}吗？\n\n任务记录和项目文件会被彻底删除，无法恢复。`);
  if (!confirmed) return;
  await purgeTask(taskId);
}

async function loadTaskList() {
  const response = await api("/api/workbench/tasks");
  if (response.ok) {
    const tasks = response.data?.tasks || [];
    allTasks = tasks;
    renderTaskList(allTasks);
    renderRecentTaskList(allTasks);
  }
  return response;
}

async function activateTask(taskId) {
  const response = await api(`/api/workbench/tasks/${encodeURIComponent(taskId)}/activate`, { method: "POST" });
  if (!response.ok) throw new Error(response.message || "激活任务失败。");
  const task = response.data?.task || {};
  activeTaskId = String(task.id || taskId);
  activeProject = String(task.project_name || "");
  selectedSlide = 0;
  setWorkbenchView("task_detail");
  if (activeProject) syncBrowserProjectUrl(activeProject);
  if (setupCollapsedSummary) setSetupCollapsed(false);
  if (activeProject) {
    await loadStatus();
    await refreshCurrentPreview();
    await loadRevisions();
    await loadQaReport();
  }
  await loadTaskList();
}

async function showModeSelectView() {
  await api("/api/workbench/session", {
    method: "PATCH",
    body: JSON.stringify({ current_view: "mode_select", current_task_id: "" }),
  });
  activeTaskId = "";
  activeProject = "";
  setWorkbenchView("mode_select");
  updateButtons(false);
  updateCollapsedSummary();
  await loadTaskList();
}

async function startNewTask() {
  await selectWorkflowMode("prompt_deck");
  saveCreationDraft();
}

async function showTaskCenterView() {
  await api("/api/workbench/session", {
    method: "PATCH",
    body: JSON.stringify({ current_view: "task_center", current_task_id: "" }),
  });
  activeTaskId = "";
  activeProject = "";
  setWorkbenchView("task_center");
  updateButtons(false);
  updateCollapsedSummary();
  await loadTaskList();
}

async function selectWorkflowMode(mode) {
  const nextMode = WORKFLOW_CONFIG[mode] ? mode : "prompt_deck";
  await api("/api/workbench/session", {
    method: "PATCH",
    body: JSON.stringify({
      current_view: "new_task",
      current_task_id: "",
      selected_workflow_mode: nextMode,
    }),
  });
  activeTaskId = "";
  activeProject = "";
  setWorkflowMode(nextMode);
  projectName.textContent = "新建任务";
  setState("准备创建", "idle");
  setWorkbenchView("new_task");
  updateButtons(false);
  updateCollapsedSummary();
}

async function showNewTaskView() {
  await selectWorkflowMode(currentWorkflowMode());
}

async function loadWorkbenchSession() {
  const response = await api("/api/workbench/session");
  if (!response.ok) throw new Error(response.message || "读取工作台会话失败。");
  const session = response.data?.session || {};
  const task = response.data?.current_task || null;
  const selectedMode = "prompt_deck";
  await loadTaskList();
  const projectFromUrl = (new URLSearchParams(window.location.search).get("project") || "").trim();
  if (projectFromUrl) {
    const listResponse = await api("/api/projects");
    const projects = Array.isArray(listResponse?.data?.projects) ? listResponse.data.projects : [];
    if (projects.includes(projectFromUrl)) {
      await activateProject(projectFromUrl);
      return;
    }
  }
  if (session.current_view === "new_task") {
    setWorkflowMode(selectedMode, false);
    setWorkbenchView("new_task");
    return;
  }
  if (session.current_view === "task_detail" && task?.id && task?.project_name) {
    activeTaskId = String(task.id);
    activeProject = String(task.project_name);
    setWorkbenchView("task_detail");
    await loadStatus();
    await refreshCurrentPreview();
    await loadRevisions();
    await loadQaReport();
    return;
  }
  activeTaskId = "";
  activeProject = "";
  setWorkflowMode(selectedMode, false);
  setWorkbenchView(session.current_view === "task_center" ? "task_center" : "mode_select");
  updateButtons(false);
  updateCollapsedSummary();
}



async function createCodexTask() {
  if (currentWorkflowMode() === "optimize_existing") {
    appendLog("优化已有 PPT 功能暂未接入。本轮先从最近任务或全部任务打开已有项目。");
    return;
  }
  if (currentWorkflowMode() === "deep_replica") {
    appendLog("深度复刻后续接入。本期不会创建任务。");
    return;
  }
  if (currentWorkflowMode() === "repair_existing") {
    appendLog("继续处理模式不会创建新项目；请先选择当前项目页面，然后检查或处理这一页。");
    return;
  }
  // C13-A：多页 prompt 场景默认先展示可编辑大纲（未勾选"跳过确认"时）。
  if (isOutlineEligible()) {
    await generateOutlineAndEdit();
    return;
  }
  const prompt = normalizePromptForSubmit(promptInput.value);
  if (!prompt) throw new Error("请先输入提示词。");
  if (templateMode.value === "strict_template") {
    appendLog("提示：strict_template 需要项目已绑定模板（template_binding.json + templates/layout_ref）。未绑定会被阻断。");
  }
  resetLog("正在创建助手任务...");
  setState("创建中", "running");
  updateButtons(false);
  // 用途与目标页数只作为生成上下文/计划目标传入；auto 保持各模式既有默认。
  let deckTypeValue = deckType.value;
  let pageCountValue = Number(pageCount.value);
  const targetPages = targetPageCount?.value || "auto";
  const isDocumentDeck = currentWorkflowMode() === "document_deck";
  if (["prompt_deck", "single_page", "document_deck"].includes(currentWorkflowMode()) && targetPages !== "auto") {
    const parsedPages = Number(targetPages);
    if (Number.isInteger(parsedPages) && parsedPages >= 1) {
      deckTypeValue = parsedPages > 1 ? "multi" : "single";
      pageCountValue = parsedPages;
    }
  }
  const payload = {
    prompt,
    deck_type: deckTypeValue,
    page_count: pageCountValue,
    scene: sceneSelect?.value || "proposal",
    style_profile: styleProfile.value,
    template_mode: templateMode.value,
    selected_template_id: getSelectedTemplateId() || "",
    workflow_mode: currentWorkflowMode(),
    source_inputs: isDocumentDeck
      ? WorkbenchAppStateOrchestration.collectDocumentSourceInputs()
      : undefined,
  };
  const response = await api("/api/workbench/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  appendLog(commandSummary("创建助手任务", response));
  if (!response.ok) {
    setState("创建失败", "error");
    throw new Error(response.message || "创建任务失败。");
  }
  activeProject = response.data.project;
  activeTaskId = String(response.data.task_id || "");
  activeProjectTitle = userFacingTaskTitle(response.data.task_title || activeProject);
  latestStatus = null;
  setWorkbenchView("task_detail");
  saveActiveProject();
  syncBrowserProjectUrl(activeProject);
  selectedSlide = 0;
  projectName.textContent = userFacingTaskTitle(response.data.task_title || activeProject);
  updateButtons(true);
  updateCollapsedSummary();
  await loadStatus();
  await refreshCurrentPreview();
  await loadRevisions();
  await loadQaReport();
  await loadTaskList();
  if (latestStatus?.generation?.api_key_configured === false) {
    appendLog("自动生成未启动：当前服务还没有读到自动生成 API Key。请配置本地密钥并重启工作台服务。");
    return;
  }
  await autoGenerateCurrentProject();
}
