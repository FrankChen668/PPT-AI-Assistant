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
  container.querySelectorAll("[data-task-archive-confirm]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const taskId = button.dataset.taskArchiveConfirm || "";
      if (!taskId) return;
      runAction(button, async () => confirmArchiveTask(taskId, button.dataset.taskTitle || ""));
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
  renderTaskListInto(taskList, visible, {
    emptyText: "还没有任务。可以新建任务开始。",
  });
}

function renderRecentTaskList(tasks) {
  const recent = Array.isArray(tasks) ? tasks.slice(0, 5) : [];
  renderTaskListInto(recentTaskList, recent, {
    emptyText: "还没有最近任务。先选择一个模式开始。",
    compact: true,
    allowArchive: true,
  });
}

window.WorkbenchAppViewWiring = {
  renderTaskListInto,
  closeTaskArchiveMenus,
  toggleTaskArchiveMenu,
  filteredTasks,
  renderTaskList,
  renderRecentTaskList,
};
