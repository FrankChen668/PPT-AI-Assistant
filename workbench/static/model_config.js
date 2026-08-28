// model_config.js — C13-0 拆分：模型配置 / 连接管理 / 角色路由 / 草稿（由 app.js 原样迁移）

function openModelConfigView() {
  if (!modelConfigView) return;
  if (activeWorkbenchView !== "model_config") modelConfigReturnView = activeWorkbenchView;
  setWorkbenchView("model_config");
  if (!selectedConnectionId && latestConnections.length) {
    selectConnection(latestConnections[0].id);
  }
}

function closeModelConfigView() {
  if (activeWorkbenchView !== "model_config") return;
  setWorkbenchView(modelConfigReturnView === "model_config" ? "mode_select" : modelConfigReturnView);
}

function setModelConfigTab(tabName) {
  const showRouting = tabName === "routing";
  modelSubtabButtons.forEach((button) => {
    const active = button.dataset.modelTab === (showRouting ? "routing" : "connections");
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  connectionsSection?.classList.toggle("active", !showRouting);
  routingSection?.classList.toggle("active", showRouting);
}

function providerDisplayName(provider) {
  const key = String(provider || "").trim().toLowerCase();
  const labels = {
    google: "Google",
    siliconflow: "SiliconFlow",
    xiaomi: "Xiaomi",
    deepseek: "DeepSeek",
  };
  return labels[key] || key || "未配置";
}

function applyGenerationSettings(settings) {
  if (!settings || typeof settings !== "object") return;
  currentGenerationSettings = { ...settings };
  if (generationProgressiveSetting) {
    generationProgressiveSetting.checked = Boolean(
      settings.progressive_visualization_enabled === true,
    );
  }
}

async function loadGenerationSettings() {
  const response = await api("/api/workbench/generation-settings");
  if (!response.ok) {
    throw new Error(response.message || "读取模型配置失败。");
  }
  applyGenerationSettings(response.data?.settings || {});
}

async function saveProgressiveVisualizationSetting() {
  // PATCH 缺 model 字段时后端会把模型重置为通道默认值，必须回传当前完整配置。
  const payload = {
    provider: currentGenerationSettings.provider || "",
    model: currentGenerationSettings.model || "",
    base_url: currentGenerationSettings.base_url || "",
    progressive_visualization_enabled: generationProgressiveSetting ? Boolean(generationProgressiveSetting.checked) : false,
  };
  const response = await api("/api/workbench/generation-settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    appendLog(response.message || "保存全局选项失败。");
    throw new Error(response.message || "保存全局选项失败。");
  }
  applyGenerationSettings(response.data?.settings || {});
  appendLog("渐进可视化设置已保存。");
}

let latestConnections = [];
let selectedConnectionId = "";

function setConnectionFormStatus(text, isError = false) {
  if (!connectionFormStatus) return;
  connectionFormStatus.textContent = text || "";
  connectionFormStatus.classList.toggle("error", Boolean(isError));
}

function renderConnectionList(connections) {
  if (!connectionListEl) return;
  if (!connections.length) {
    connectionListEl.innerHTML = '<div class="empty-note">暂无连接</div>';
    return;
  }
  connectionListEl.innerHTML = connections
    .map((item) => {
      const active = item.id === selectedConnectionId;
      const keyState = item.api_key_configured ? "密钥已配置" : "密钥未配置";
      const stateSuffix = item.enabled ? "" : " · 已停用";
      return `<button type="button" class="connection-item${active ? " active" : ""}${item.enabled ? "" : " connection-item-disabled"}" data-connection-select="${escapeHtml(item.id)}">
        <span class="connection-item-main">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(providerDisplayName(item.provider) || item.provider)} · ${keyState}${stateSuffix}</span>
        </span>
        <span class="mini-status${item.enabled && item.api_key_configured ? " ok" : ""}" aria-hidden="true"></span>
      </button>`;
    })
    .join("");
}

async function loadConnections() {
  if (!connectionListEl) return;
  const response = await api("/api/workbench/connections");
  if (!response.ok) throw new Error(response.message || "读取连接列表失败。");
  latestConnections = response.data?.connections || [];
  if (selectedConnectionId && !latestConnections.some((item) => item.id === selectedConnectionId)) {
    selectedConnectionId = "";
  }
  renderConnectionList(latestConnections);
  renderRoleRoutingOptions();
}

function selectConnection(connectionId) {
  const found = latestConnections.find((item) => item.id === connectionId) || null;
  selectedConnectionId = found ? found.id : "";
  renderConnectionList(latestConnections);
  openConnectionForm(found);
}

function connectionKeyHintText(connection) {
  // C07：密钥展示只依赖服务端派生的 api_key_hint 尾号字段，前端不接触明文。
  if (!connection || !connection.api_key_configured) return "未配置密钥";
  const hint = String(connection.api_key_hint || "").trim();
  return hint ? `••••••••${hint}` : "已配置（尾号不展示）";
}

function updateProtocolNote(provider) {
  if (!protocolNoteEl) return;
  const isGoogle = String(provider || "") === "google";
  protocolNoteEl.classList.toggle("hidden", !isGoogle);
  protocolNoteEl.textContent = isGoogle
    ? "Google 连接走官方协议：Base URL 留空即使用官方端点，模型列表经官方接口读取。"
    : "";
}

function setConnectionTestStatus(title, detail, isOk = false) {
  if (testStatusTitleEl) {
    testStatusTitleEl.textContent = title || "未测试";
    testStatusTitleEl.classList.toggle("ok", Boolean(isOk));
  }
  if (testStatusDetailEl) testStatusDetailEl.textContent = detail || "";
}

function openConnectionForm(connection = null) {
  if (!connectionFormEl) return;
  const editing = Boolean(connection);
  connectionEditingIdInput.value = editing ? connection.id : "";
  connectionNameInput.value = editing ? connection.name : "";
  connectionProviderSelect.value = editing ? connection.provider : "deepseek";
  // 编辑态不允许改 provider（服务端白名单不含 provider，避免静默丢弃）。
  connectionProviderSelect.disabled = editing;
  connectionBaseUrlInput.value = editing ? connection.base_url : "";
  connectionApiKeyInput.value = "";
  // 编辑态默认只展示尾号，点「更换密钥」后才显示输入框；新建态直接显示输入框。
  connectionApiKeyInput.classList.toggle("hidden", editing);
  if (keyMaskedEl) keyMaskedEl.textContent = editing ? connectionKeyHintText(connection) : "新连接：请输入密钥";
  if (replaceKeyButton) replaceKeyButton.classList.toggle("hidden", !editing);
  if (connectionTitleEl) connectionTitleEl.textContent = editing ? connection.name : "新建连接";
  if (connectionDescriptionEl) {
    connectionDescriptionEl.textContent = editing
      ? `${providerDisplayName(connection.provider) || connection.provider} · ${connection.enabled ? "已启用" : "已停用"}`
      : "填写连接信息后保存。";
  }
  if (deleteConnectionButton) deleteConnectionButton.classList.toggle("hidden", !editing);
  if (toggleConnectionEnabledButton) {
    toggleConnectionEnabledButton.classList.toggle("hidden", !editing);
    toggleConnectionEnabledButton.textContent = editing && !connection.enabled ? "启用" : "停用";
  }
  if (duplicateConnectionButton) duplicateConnectionButton.classList.toggle("hidden", !editing);
  updateProtocolNote(editing ? connection.provider : connectionProviderSelect.value);
  setConnectionTestStatus("未测试", editing ? "点击「测试并读取模型」验证连接。" : "保存后可测试连接。");
  setConnectionFormStatus(editing ? `正在编辑：${connection.name}` : "");
  connectionFormEl.classList.remove("hidden");
}

function closeConnectionForm() {
  if (!connectionFormEl) return;
  selectedConnectionId = "";
  renderConnectionList(latestConnections);
  openConnectionForm(null);
}

async function saveConnection() {
  const editingId = connectionEditingIdInput.value.trim();
  const payload = {
    name: connectionNameInput.value.trim(),
    base_url: connectionBaseUrlInput.value.trim(),
  };
  if (!editingId) payload.provider = connectionProviderSelect.value;
  const apiKey = connectionApiKeyInput.value.trim();
  if (apiKey) payload.api_key = apiKey;
  setConnectionFormStatus("正在保存连接...");
  const response = await api(
    editingId ? `/api/workbench/connections/${encodeURIComponent(editingId)}` : "/api/workbench/connections",
    { method: editingId ? "PATCH" : "POST", body: JSON.stringify(payload) },
  );
  if (!response.ok) {
    setConnectionFormStatus(response.message || "保存连接失败。", true);
    throw new Error(response.message || "保存连接失败。");
  }
  appendLog("API 连接已保存。");
  const savedId = String(response.data?.connection?.id || editingId || "");
  await loadConnections();
  if (savedId) selectConnection(savedId);
  setConnectionFormStatus("连接已保存。");
}

async function testConnectionAndLoadModels(connectionId) {
  const targetId = connectionId || selectedConnectionId;
  if (!targetId) return;
  setConnectionTestStatus("测试中…", "正在连接服务端…");
  const response = await api(`/api/workbench/connections/${encodeURIComponent(targetId)}/test`, { method: "POST" });
  if (!response.ok) {
    setConnectionTestStatus("测试失败", response.message || "连接测试失败。");
    throw new Error(response.message || "连接测试失败。");
  }
  const result = response.data?.result || {};
  if (!result.ok) {
    setConnectionTestStatus("测试失败", result.message || "未知原因");
    appendLog(`连接测试失败：${result.message || "未知原因"}`);
    return;
  }
  const modelsResponse = await api(`/api/workbench/connections/${encodeURIComponent(targetId)}/models`);
  const models = modelsResponse.ok ? modelsResponse.data?.models || [] : [];
  setConnectionTestStatus("连接正常", models.length ? `读取到 ${models.length} 个模型。` : "连接测试通过。", true);
  appendLog("连接测试通过。");
}

async function duplicateSelectedConnection() {
  const source = latestConnections.find((item) => item.id === selectedConnectionId);
  if (!source) return;
  // C07：复制连接只带公开字段，密钥不随副本传输，需在副本上重新录入。
  const payload = {
    name: `${source.name}（副本）`,
    provider: source.provider,
    base_url: source.base_url,
    models: Array.isArray(source.models) ? source.models : [],
  };
  const response = await api("/api/workbench/connections", { method: "POST", body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(response.message || "复制连接失败。");
  appendLog("连接已复制，密钥需在副本上重新录入。");
  const createdId = String(response.data?.connection?.id || "");
  await loadConnections();
  if (createdId) selectConnection(createdId);
}

async function toggleSelectedConnectionEnabled() {
  const source = latestConnections.find((item) => item.id === selectedConnectionId);
  if (!source) return;
  await toggleConnectionEnabled(source.id, !source.enabled);
  selectConnection(source.id);
}

async function deleteSelectedConnection() {
  const source = latestConnections.find((item) => item.id === selectedConnectionId);
  if (!source) return;
  const confirmed = window.confirm(`确定删除连接“${source.name}”吗？\n\n连接记录会被彻底删除，无法恢复。`);
  if (!confirmed) return;
  const response = await api(`/api/workbench/connections/${encodeURIComponent(source.id)}`, { method: "DELETE" });
  if (!response.ok) {
    // 被角色路由引用时服务端返回 409，把具体原因直接展示在表单状态里。
    setConnectionFormStatus(response.message || "删除连接失败。", true);
    throw new Error(response.message || "删除连接失败。");
  }
  appendLog(`连接“${source.name}”已删除。`);
  selectedConnectionId = "";
  await loadConnections();
  openConnectionForm(null);
}

async function toggleConnectionEnabled(connectionId, enabled) {
  const response = await api(`/api/workbench/connections/${encodeURIComponent(connectionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw new Error(response.message || "更新连接状态失败。");
  appendLog(enabled ? "连接已启用。" : "连接已停用。");
  await loadConnections();
}

function roleRoutingConnectionSelects() {
  return Array.from(document.querySelectorAll("[data-role-connection]"));
}

function roleRoutingModelInputs() {
  return Array.from(document.querySelectorAll("[data-role-model]"));
}

function setRoleRoutingStatus(message, isError = false) {
  if (!roleRoutingStatusEl) return;
  roleRoutingStatusEl.textContent = message || "";
  roleRoutingStatusEl.classList.toggle("error", Boolean(isError));
}

function renderRoleRoutingOptions() {
  roleRoutingConnectionSelects().forEach((select) => {
    const current = select.value;
    const placeholder = select.querySelector('option[value=""]')?.textContent || "使用默认";
    select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>${latestConnections
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`)
      .join("")}`;
    select.value = current;
    if (select.value !== current) select.value = "";
  });
}

async function loadRoleRouting() {
  if (!saveRoleRoutingButton) return;
  renderRoleRoutingOptions();
  const response = await api("/api/workbench/role-routing");
  if (!response.ok) throw new Error(response.message || "读取角色路由失败。");
  const roles = response.data?.roles || {};
  roleRoutingConnectionSelects().forEach((select) => {
    const entry = roles[select.dataset.roleConnection] || {};
    select.value = entry.connection_id || "";
  });
  roleRoutingModelInputs().forEach((input) => {
    const entry = roles[input.dataset.roleModel] || {};
    input.value = entry.model_id || "";
  });
}

async function saveRoleRouting() {
  const roles = {};
  roleRoutingConnectionSelects().forEach((select) => {
    roles[select.dataset.roleConnection] = { connection_id: select.value || "", model_id: "" };
  });
  roleRoutingModelInputs().forEach((input) => {
    const entry = roles[input.dataset.roleModel] || { connection_id: "" };
    entry.model_id = input.value.trim();
    roles[input.dataset.roleModel] = entry;
  });
  setRoleRoutingStatus("正在保存角色路由...");
  const response = await api("/api/workbench/role-routing", { method: "PATCH", body: JSON.stringify({ roles }) });
  if (!response.ok) {
    setRoleRoutingStatus(response.message || "保存角色路由失败。", true);
    throw new Error(response.message || "保存角色路由失败。");
  }
  setRoleRoutingStatus("角色路由已保存。");
  appendLog("角色模型路由已保存。");
}

function saveActiveProject() {
  if (!activeProject) return;
  storage.writeText(ACTIVE_PROJECT_KEY, activeProject);
}

function saveCreationDraft() {
  writeJsonStorage(DRAFT_PREF_KEY, {
    workflowMode: "prompt_deck",
    deckType: "single",
    pageCount: "1",
    scene: sceneSelect?.value || "proposal",
    targetPageCount: targetPageCount?.value || "auto",
    styleProfile: styleProfile?.value || "consulting_blue",
    templateMode: templateMode?.value || "free",
    selectedTemplateId: getSelectedTemplateId(),
    prompt: promptInput?.value || "",
  });
}

function loadCreationDraft() {
  const saved = readJsonStorage(DRAFT_PREF_KEY, {});
  const mode = "prompt_deck";
  const config = WORKFLOW_CONFIG[mode] || WORKFLOW_CONFIG.prompt_deck;
  setWorkflowMode(mode, false);
  if (deckType) deckType.value = config.deckType || "single";
  if (pageCount) pageCount.value = config.pageCount || "1";
  if (sceneSelect && saved.scene) sceneSelect.value = saved.scene;
  if (targetPageCount && saved.targetPageCount) targetPageCount.value = saved.targetPageCount;
  if (styleProfile && saved.styleProfile) styleProfile.value = saved.styleProfile;
  if (templateMode && saved.templateMode) templateMode.value = saved.templateMode;
  if (saved.selectedTemplateId) setSelectedTemplateId(String(saved.selectedTemplateId));
  if (promptInput && typeof saved.prompt === "string" && saved.prompt.trim()) {
    promptInput.value = saved.prompt;
  } else if (promptInput && !promptInput.value.trim()) {
    promptInput.value = WORKFLOW_CONFIG[mode]?.prompt || "";
  }
  deckType.disabled = true;
  pageCount.disabled = true;
  renderSelectedWorkflowMode(mode);
  updateGenerationModeUi();
}

