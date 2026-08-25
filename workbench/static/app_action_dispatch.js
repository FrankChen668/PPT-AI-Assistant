async function deleteTask(taskId) {
  const response = await api(`/api/workbench/tasks/${encodeURIComponent(taskId)}/delete`, { method: "POST" });
  if (!response.ok) throw new Error(response.message || "删除任务失败。");
  if (activeTaskId === taskId) activeTaskId = "";
  appendLog("任务已删除。");
  await loadTaskList();
}

async function confirmDeleteTask(taskId, title = "") {
  closeTaskArchiveMenus();
  const label = title ? `“${title}”` : "该任务";
  const confirmed = window.confirm(`确定删除 ${label} 吗？\n\n任务会从列表移除，项目文件会移到本地归档区。`);
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
  const label = title ? `“${title}”` : "该任务";
  const confirmed = window.confirm(`确定永久删除 ${label} 吗？\n\n任务记录和项目文件会被彻底删除，无法恢复。`);
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
  if (!response.ok) throw new Error(response.message || "打开任务失败。");
  const task = response.data?.task || {};
  activeTaskId = String(task.id || taskId);
  activeProject = String(task.project_name || "");
  selectedSlide = 1;
  setWorkbenchView("task_detail");
  if (activeProject && typeof syncBrowserProjectUrl === "function") syncBrowserProjectUrl(activeProject);
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
  projectName.textContent = "尚未创建任务";
  setState("等待开始", "idle");
  setWorkbenchView("new_task");
  updateButtons(false);
  updateCollapsedSummary();
}

async function showNewTaskView() {
  await selectWorkflowMode(currentWorkflowMode());
}

async function loadWorkbenchSession() {
  const response = await api("/api/workbench/session");
  if (!response.ok) throw new Error(response.message || "读取工作台状态失败。");
  const session = response.data?.session || {};
  const task = response.data?.current_task || null;
  const selectedMode = WORKFLOW_CONFIG[session.selected_workflow_mode] ? session.selected_workflow_mode : "prompt_deck";
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

window.WorkbenchAppActionDispatch = {
  deleteTask,
  confirmDeleteTask,
  purgeTask,
  confirmPurgeTask,
  loadTaskList,
  activateTask,
  showModeSelectView,
  startNewTask,
  showTaskCenterView,
  selectWorkflowMode,
  showNewTaskView,
  loadWorkbenchSession,
};
