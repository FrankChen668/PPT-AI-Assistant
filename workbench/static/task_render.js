(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function generatedTaskTitle(value) {
    const raw = String(value || "").trim();
    const matched = raw.match(/^codex-(?:single|multi|uat)-ppt(?:-r\d+)?-(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:-|$)/);
    if (!matched) return "";
    // Example: codex-single-ppt-20260531221751 -> PPT 任务 05-31 22:17.
    return `PPT 任务 ${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}`;
  }

  function userFacingTaskTitle(value, fallback = "未命名 PPT 任务") {
    const raw =
      typeof value === "object" && value
        ? String(value.title || value.project_name || "").trim()
        : String(value || "").trim();
    if (!raw) return fallback;
    const generated = generatedTaskTitle(raw);
    if (generated) return generated;
    const quoted = raw.match(/《([^》]{2,80})》/) || raw.match(/[“"「](.{2,80})[”"」]/);
    if (quoted) return quoted[1].trim();
    const simplified = raw
      .replace(/^请(?:帮我)?(?:只)?生成\s*\d*\s*页?\s*PPT[:：\s]*/iu, "")
      .replace(/^PPT[:：\s]*/iu, "")
      .replace(/不要生成其他页面.*/u, "")
      .replace(/不要补充上下文.*/u, "")
      .replace(/不要输出整套 PPT.*/u, "")
      .replace(/[“”"「」《》]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (simplified.length > 40) return `${simplified.slice(0, 40)}...`;
    return simplified || raw;
  }

  function taskTitle(task) {
    return userFacingTaskTitle(task, "未命名 PPT 任务");
  }

  function compactTaskTitle(task) {
    let title = taskTitle(task).replace(/\s+/g, " ").trim();
    const quoted = title.match(/[“"「《](.{1,80})[”"」》]/);
    if (quoted) return quoted[1].trim();
    title = title
      .replace(/^请只生成\d+页PPT[:：]?\s*/u, "")
      .replace(/[“”"「」《》]/g, "")
      .replace(/\s+-\s+/g, " ")
      .trim();
    if (title.length > 34) return `${title.slice(0, 34)}...`;
    return title || "未命名任务";
  }

  function formatTaskUpdatedAt(value) {
    if (!value) return "未知时间";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function recommendedActionLabel(action) {
    const labels = {
      create_task: "\u521b\u5efa\u4efb\u52a1",
      edit_page_prompt: "\u8865\u5145\u9875\u9762\u5185\u5bb9",
      auto_generate: "\u751f\u6210\u9875\u9762",
      auto_check: "\u5f85\u68c0\u67e5",
      qa_slide: "\u5f85\u68c0\u67e5",
      repair_slide: "\u4fee\u590d\u9875\u9762",
      repair_budget: "\u4f18\u5316\u9875\u9762",
      repair_delivery_blocker: "\u4fee\u590d\u4ea4\u4ed8\u95ee\u9898",
      repair_export_failure: "\u5904\u7406\u5bfc\u51fa\u95ee\u9898",
      export_pptx: "\u751f\u6210 PPT",
      fresh_release_safe: "\u751f\u6210 PPT",
      download_pptx: "\u4e0b\u8f7d PPT",
      manual_review: "\u67e5\u770b\u590d\u6838\u7ed3\u679c",
      auto_optimize_slide: "\u4f18\u5316\u9875\u9762",
      export_current_slide: "\u4e0b\u8f7d\u5f53\u524d\u9875",
    };
    return labels[String(action || "")] || "";
  }

  function taskStatusLabel(task, projectStatusLabel) {
    const status = String(task?.status || "");
    const project = String(task?.project_status || "");
    const exportStatus = String(task?.export_status || "");
    const action = String(task?.recommended_action || "");
    const projectLabel = projectStatusLabel ? projectStatusLabel(project) : "";
    if (["exported", "export_ready", "export_review_required", "qa_passed", "svg_ready"].includes(project)) {
      return projectLabel || "已生成";
    }
    if (["exported", "ready", "review_required"].includes(exportStatus)) {
      return projectLabel || "已生成";
    }
    if (["qa_failed", "export_failed"].includes(project) || exportStatus === "failed") {
      return projectLabel || "需处理";
    }
    if (status === "active") return "进行中";
    if (status === "completed") return "已完成";
    if (status === "blocked") return "需处理";
    if (status === "ready") return "可生成";
    if (status === "missing_project") return "项目缺失";
    const actionLabel = recommendedActionLabel(action);
    if (actionLabel) return actionLabel;
    return projectStatusLabel ? projectStatusLabel(project || status || "active") : project || status || "active";
  }

  function renderTaskCard(task, options = {}) {
    const id = String(task?.id || "");
    const active = id && id === options.activeTaskId ? "active" : "";
    const compact = options.compact ? "compact" : "";
    const title = options.compact ? compactTaskTitle(task) : taskTitle(task);
    const updated = `更新：${formatTaskUpdatedAt(task?.updated_at)}`;
    const archiveAction = options.allowArchive
      ? `<div class="task-card-menu-wrap">
          <button class="task-card-remove" type="button" data-task-menu="${escapeHtml(id)}" aria-expanded="false" aria-label="打开任务菜单 ${escapeHtml(title)}">...</button>
          <div class="task-card-menu hidden" data-task-menu-panel="${escapeHtml(id)}">
            <button type="button" data-task-delete-confirm="${escapeHtml(id)}" data-task-title="${escapeHtml(title)}">删除任务</button>
            <button type="button" class="task-card-menu-danger" data-task-purge-confirm="${escapeHtml(id)}" data-task-title="${escapeHtml(title)}">永久删除</button>
          </div>
        </div>`
      : "";
    return `<article class="task-card ${active} ${compact}" data-task-id="${escapeHtml(id)}">
        <button class="task-card-main" type="button" data-task-id="${escapeHtml(id)}">
          <strong>${escapeHtml(title)}</strong>
          <span class="task-card-status">${escapeHtml(taskStatusLabel(task, options.projectStatusLabel))}</span>
          <small>${escapeHtml(updated)}</small>
        </button>
        ${archiveAction}
      </article>`;
  }

  function taskRowDescription(task) {
    const raw = String(task?.user_prompt || "").replace(/\s+/g, " ").trim();
    const text = raw && raw !== taskTitle(task) ? raw : String(task?.project_name || "");
    if (text.length > 60) return `${text.slice(0, 60)}...`;
    return text;
  }

  function renderTaskTableHeader(options = {}) {
    const selectCell = options.selectable
      ? `<div class="task-row-select"><input type="checkbox" data-task-select-all aria-label="全选任务" /></div>`
      : "";
    return `<div class="task-row task-row-header">
        ${selectCell}
        <div>任务名称</div>
        <div>状态</div>
        <div>页数</div>
        <div>更新时间</div>
        <div class="task-row-actions-head">操作</div>
      </div>`;
  }

  function renderTaskRow(task, options = {}) {
    const id = String(task?.id || "");
    const active = id && id === options.activeTaskId ? "active" : "";
    const title = taskTitle(task);
    const desc = taskRowDescription(task);
    const slideCount = Number(task?.slide_count || 0);
    const pages = slideCount > 0 ? `${slideCount}页` : "—";
    const checked = options.selectedIds && options.selectedIds.has(id) ? "checked" : "";
    const selectCell = options.selectable
      ? `<div class="task-row-select"><input type="checkbox" data-task-select="${escapeHtml(id)}" aria-label="选择任务 ${escapeHtml(title)}" ${checked} /></div>`
      : "";
    return `<div class="task-row task-card-row ${active}" data-task-id="${escapeHtml(id)}">
        ${selectCell}
        <div class="task-row-main">
          <div class="task-row-title">${escapeHtml(title)}</div>
          ${desc ? `<div class="task-row-desc">${escapeHtml(desc)}</div>` : ""}
        </div>
        <div><span class="task-card-status">${escapeHtml(taskStatusLabel(task, options.projectStatusLabel))}</span></div>
        <div class="task-row-pages">${escapeHtml(pages)}</div>
        <div class="task-row-time">${escapeHtml(formatTaskUpdatedAt(task?.updated_at))}</div>
        <div class="task-row-actions">
          <button class="task-row-open" type="button" data-task-open="${escapeHtml(id)}">打开</button>
          <button class="task-row-danger" type="button" data-task-purge-confirm="${escapeHtml(id)}" data-task-title="${escapeHtml(title)}">永久删除</button>
        </div>
      </div>`;
  }

  function eventTypeLabel(type) {
    const labels = {
      qa_slide: "检查页面",
      repair_task: "继续处理",
      export_pptx: "生成 PPT",
      download_pptx: "下载 PPT",
      auto_generate_slide: "生成页面",
      auto_generate_batch: "批量生成",
    };
    return labels[type] || type || "事件";
  }

  function taskEventSignature(event) {
    const payload = event?.payload || {};
    return [
      event?.event_type || "",
      payload.project || "",
      payload.slide_id || "",
      payload.source || "",
      payload.result || "",
      payload.returncode ?? "",
      payload.repair_type || "",
    ].join("|");
  }

  function compactTaskEvents(events) {
    const compacted = [];
    (Array.isArray(events) ? events : []).forEach((event) => {
      const signature = taskEventSignature(event);
      const previous = compacted[compacted.length - 1];
      if (previous && previous._signature === signature) {
        previous._count = (previous._count || 1) + 1;
        previous.created_at = event.created_at || previous.created_at;
        previous.id = event.id || previous.id;
        return;
      }
      compacted.push({ ...event, _signature: signature, _count: 1 });
    });
    return compacted;
  }

  function renderTaskEvents(events) {
    return compactTaskEvents(events)
      .slice(-20)
      .reverse()
      .map((event) => {
        const payload = event.payload || {};
        const eventSlideNo = Number(event.slide_no_at_event || payload.slide_no || 0);
        const detail = eventSlideNo > 0 ? `第 ${eventSlideNo} 页` : payload.project || "";
        return `
        <div class="task-event-item">
          <strong>${escapeHtml(eventTypeLabel(event.event_type))}${event._count && event._count > 1 ? ` x${event._count}` : ""}</strong>
          <span>${escapeHtml(detail)}</span>
          <small>${escapeHtml(event.created_at || "")}</small>
        </div>
      `;
      })
      .join("");
  }

  window.WorkbenchTaskRender = {
    compactTaskTitle,
    renderTaskCard,
    renderTaskRow,
    renderTaskTableHeader,
    renderTaskEvents,
    compactTaskEvents,
    userFacingTaskTitle,
  };
})();
