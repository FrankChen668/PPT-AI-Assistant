// outline_editor.js — C13-A 大纲确认点：生成大纲 → 可编辑面板 → 确认后创建项目
// 职责：
//   1. 调用 POST /api/outline/generate 获取大纲（不创建项目）
//   2. 在 composer 区域渲染可编辑大纲面板（标题 / 核心结论 / 支撑要点）
//   3. HTML5 Drag and Drop 拖拽排序（不引入第三方库）
//   4. 调用 POST /api/outline/confirm 提交确认后大纲并启动生成
// 数据权威：blueprint.json 结构不变；claim_boundary 为后端校验字段，前端不暴露编辑。

const outlineEditorPanel = document.getElementById("outlineEditorPanel");
const outlineDeckThesis = document.getElementById("outlineDeckThesis");
const outlineSlideList = document.getElementById("outlineSlideList");
const outlineAddSlide = document.getElementById("outlineAddSlide");
const outlineCancelEdit = document.getElementById("outlineCancelEdit");
const outlineConfirmButton = document.getElementById("outlineConfirmButton");
const outlineDirectGenerate = document.getElementById("outlineDirectGenerate");
const outlineSkipConfirm = document.getElementById("outlineSkipConfirm");

let outlineEditorData = null; // { deck_thesis, slides }
let outlineDirtyKeys = new Set(); // 变更标记："thesis" | "order" | "s{index}:{field}"
let outlineDragIndex = -1;

// 进入大纲流程的前置条件：多页提示词或文档模式且未勾选"跳过确认"。
function isOutlineEligible() {
  if (!outlineSkipConfirm || outlineSkipConfirm.checked) return false;
  const mode = currentWorkflowMode();
  if (mode !== "prompt_deck" && mode !== "single_page" && mode !== "document_deck") return false;
  const targetPages = targetPageCount?.value || "auto";
  if (targetPages === "auto") return false;
  const pages = Number(targetPages);
  if (!Number.isInteger(pages) || pages <= 1) return false;
  return true;
}

// 与 createCodexTask 保持一致的请求参数收集。
function buildOutlineRequestPayload(prompt) {
  let deckTypeValue = deckType.value;
  let pageCountValue = Number(pageCount.value);
  const targetPages = targetPageCount?.value || "auto";
  if (["prompt_deck", "single_page", "document_deck"].includes(currentWorkflowMode()) && targetPages !== "auto") {
    const parsedPages = Number(targetPages);
    if (Number.isInteger(parsedPages) && parsedPages >= 1) {
      deckTypeValue = parsedPages > 1 ? "multi" : "single";
      pageCountValue = parsedPages;
    }
  }
  return {
    prompt,
    deck_type: deckTypeValue,
    page_count: pageCountValue,
    scene: sceneSelect?.value || "proposal",
    style_profile: styleProfile.value,
    template_mode: templateMode.value,
    selected_template_id: getSelectedTemplateId() || "",
    workflow_mode: currentWorkflowMode(),
    source_inputs: currentWorkflowMode() === "document_deck"
      ? WorkbenchAppStateOrchestration.collectDocumentSourceInputs()
      : undefined,
  };
}

// 主入口：生成大纲并展示编辑面板；不适用时回退到旧流程。
async function generateOutlineAndEdit() {
  const prompt = normalizePromptForSubmit(promptInput.value);
  if (!prompt) throw new Error("请先输入提示词。");
  if (templateMode.value === "strict_template") {
    appendLog("提示：strict_template 需要项目已绑定模板（template_binding.json + templates/layout_ref）。未绑定会被阻断。");
  }
  resetLog("正在生成大纲...");
  setState("生成大纲中", "running");
  updateButtons(false);
  const payload = buildOutlineRequestPayload(prompt);
  const response = await api("/api/outline/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  appendLog(commandSummary("生成大纲", response));
  if (!response.ok) {
    setState("大纲生成失败", "error");
    updateButtons(true);
    if (String(response.message || "").includes("not_eligible")) {
      appendLog("当前输入不适合大纲确认流程，已切换到直接生成。");
      outlineSkipConfirm.checked = true;
      return createCodexTask();
    }
    throw new Error(response.message || "大纲生成失败。");
  }
  openOutlineEditor(response.data);
}

function openOutlineEditor(data) {
  outlineEditorData = data || { deck_thesis: "", slides: [] };
  outlineDirtyKeys.clear();
  document.getElementById("promptInput")?.closest(".prompt-field")?.classList.add("hidden");
  documentSourceField?.classList.add("hidden");
  document.querySelector(".composer-control-bar")?.classList.add("hidden");
  outlineEditorPanel?.classList.remove("hidden");
  renderOutlineEditor();
}

function closeOutlineEditor() {
  outlineEditorPanel?.classList.add("hidden");
  document.getElementById("promptInput")?.closest(".prompt-field")?.classList.remove("hidden");
  documentSourceField?.classList.remove("hidden");
  document.querySelector(".composer-control-bar")?.classList.remove("hidden");
  outlineEditorData = null;
  outlineDirtyKeys.clear();
}

// ---------- 渲染 ----------

function renderOutlineEditor() {
  const data = outlineEditorData || { deck_thesis: "", slides: [] };
  const thesisLabel = outlineDeckThesis?.closest("label");
  outlineDeckThesis.value = data.deck_thesis || "";
  thesisLabel?.classList.toggle("changed", outlineDirtyKeys.has("thesis"));
  outlineSlideList.innerHTML = "";
  data.slides.forEach((slide, index) => {
    outlineSlideList.appendChild(renderOutlineSlideCard(slide, index));
  });
  updateOutlineConfirmState();
}

function renderOutlineSlideCard(slide, index) {
  const card = document.createElement("article");
  card.className = "outline-slide-card";
  card.dataset.slideIndex = String(index);
  card.draggable = true;
  card.setAttribute("aria-label", `第 ${index + 1} 页大纲`);

  const claims = Array.isArray(slide.claims) ? slide.claims : [];
  const content = slide.content && typeof slide.content === "object" ? slide.content : {};
  const extraClaims = claims.slice(1);
  const extraPointRows = extraClaims
    .map(
      (claim, offset) => `
      <div class="outline-point-row" data-point-row="${offset + 1}">
        <span class="outline-point-bullet">•</span>
        <input class="outline-point-input" type="text" data-outline-field="claims:${offset + 1}" value="" placeholder="辅助要点" />
        <button class="ghost-action icon-btn outline-point-remove" type="button" title="删除要点" aria-label="删除要点">×</button>
      </div>`,
    )
    .join("");

  card.innerHTML = `
    <div class="outline-slide-head">
      <span class="outline-drag-handle" title="拖拽排序" aria-label="拖拽排序">≡</span>
      <span class="outline-slide-number">第 ${index + 1} 页</span>
      <input class="outline-title-input" type="text" data-outline-field="title" value="" placeholder="页面标题" />
      <span class="outline-slide-tools">
        <button class="ghost-action icon-btn outline-slide-move-up" type="button" title="上移" aria-label="上移">↑</button>
        <button class="ghost-action icon-btn outline-slide-move-down" type="button" title="下移" aria-label="下移">↓</button>
        <button class="ghost-action icon-btn outline-slide-remove" type="button" title="删除本页" aria-label="删除本页">×</button>
      </span>
    </div>
    <label class="outline-field-label">
      <span>核心结论</span>
      <textarea class="outline-claim-input" rows="2" data-outline-field="claims:0" placeholder="一句话核心结论"></textarea>
    </label>
    <div class="outline-points-block">
      <span class="outline-points-title">支撑要点</span>
      <div class="outline-point-row" data-point-row="body">
        <span class="outline-point-bullet">•</span>
        <input class="outline-point-input" type="text" data-outline-field="body" value="" placeholder="来自用户材料的支撑内容" />
      </div>
      <div class="outline-point-row" data-point-row="support">
        <span class="outline-point-bullet">•</span>
        <input class="outline-point-input" type="text" data-outline-field="support" value="" placeholder="对受众的含义（材料不足可写待补充）" />
      </div>
      ${extraPointRows}
      <button class="ghost-action outline-add-point" type="button">+ 添加要点</button>
    </div>`;

  card.querySelector('[data-outline-field="title"]').value = slide.title || "";
  card.querySelector('[data-outline-field="claims:0"]').value = claims[0] || "";
  card.querySelector('[data-outline-field="body"]').value = content.body || "";
  card.querySelector('[data-outline-field="support"]').value = content.support || "";
  extraClaims.forEach((claim, offset) => {
    card.querySelector(`[data-outline-field="claims:${offset + 1}"]`).value = claim || "";
  });

  bindOutlineCardEvents(card, index);
  markOutlineCardChanged(card, index);
  return card;
}

function bindOutlineCardEvents(card, index) {
  card.querySelectorAll("[data-outline-field]").forEach((field) => {
    field.addEventListener("input", () => {
      applyOutlineFieldEdit(index, field.dataset.outlineField, field.value);
    });
  });
  card.querySelector(".outline-slide-move-up")?.addEventListener("click", () => {
    if (index > 0) moveOutlineSlide(index, index - 1);
  });
  card.querySelector(".outline-slide-move-down")?.addEventListener("click", () => {
    if (index < outlineEditorData.slides.length - 1) moveOutlineSlide(index, index + 1);
  });
  card.querySelector(".outline-slide-remove")?.addEventListener("click", () => {
    removeOutlineSlide(index);
  });
  card.querySelector(".outline-add-point")?.addEventListener("click", () => {
    addOutlinePoint(index);
  });
  card.querySelectorAll(".outline-point-remove").forEach((button) => {
    const row = button.closest("[data-point-row]");
    const pointIndex = Number(row?.dataset.pointRow || 0);
    button.addEventListener("click", () => {
      removeOutlinePoint(index, pointIndex);
    });
  });
  // HTML5 Drag and Drop：卡片本身可拖拽，悬停目标高亮，放下时重排。
  card.addEventListener("dragstart", (event) => {
    outlineDragIndex = index;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(index));
    card.classList.add("outline-dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("outline-dragging");
    outlineSlideList.querySelectorAll(".outline-drop-target").forEach((el) => el.classList.remove("outline-drop-target"));
    outlineDragIndex = -1;
  });
  card.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    if (outlineDragIndex !== index) card.classList.add("outline-drop-target");
  });
  card.addEventListener("dragleave", () => {
    card.classList.remove("outline-drop-target");
  });
  card.addEventListener("drop", (event) => {
    event.preventDefault();
    card.classList.remove("outline-drop-target");
    const fromIndex =
      outlineDragIndex >= 0 ? outlineDragIndex : Number(event.dataTransfer.getData("text/plain"));
    if (Number.isInteger(fromIndex) && fromIndex >= 0 && fromIndex < outlineEditorData.slides.length && fromIndex !== index) {
      moveOutlineSlide(fromIndex, index);
    }
  });
}

// ---------- 编辑操作 ----------

function applyOutlineFieldEdit(index, field, value) {
  const slide = outlineEditorData.slides[index];
  if (!slide) return;
  if (field === "title") {
    slide.title = value;
  } else if (field === "claims:0") {
    const claims = Array.isArray(slide.claims) ? [...slide.claims] : [];
    claims[0] = value;
    slide.claims = claims;
  } else if (field.startsWith("claims:")) {
    const claimIndex = Number(field.slice("claims:".length));
    const claims = Array.isArray(slide.claims) ? [...slide.claims] : [];
    claims[claimIndex] = value;
    slide.claims = claims;
  } else if (field === "body" || field === "support") {
    slide.content = { ...(slide.content || {}), [field]: value };
  }
  outlineDirtyKeys.add(`s${index}:${field}`);
  markOutlineCardChanged(document.querySelector(`.outline-slide-card[data-slide-index="${index}"]`), index);
  updateOutlineConfirmState();
}

function moveOutlineSlide(fromIndex, toIndex) {
  const slides = outlineEditorData.slides;
  const [moved] = slides.splice(fromIndex, 1);
  slides.splice(toIndex, 0, moved);
  outlineDirtyKeys.add("order");
  renderOutlineEditor();
}

function removeOutlineSlide(index) {
  outlineEditorData.slides.splice(index, 1);
  outlineDirtyKeys.add("order");
  renderOutlineEditor();
}

function addOutlinePoint(index) {
  const slide = outlineEditorData.slides[index];
  const claims = Array.isArray(slide.claims) ? [...slide.claims] : [];
  claims.push("");
  slide.claims = claims;
  outlineDirtyKeys.add(`s${index}:claims:${claims.length - 1}`);
  renderOutlineEditor();
}

function removeOutlinePoint(index, pointIndex) {
  const slide = outlineEditorData.slides[index];
  let claims = Array.isArray(slide.claims) ? [...slide.claims] : [];
  if (pointIndex === 1 && slide.content) {
    slide.content = { ...slide.content, body: "" };
  } else if (pointIndex === 2 && slide.content) {
    slide.content = { ...slide.content, support: "" };
  } else {
    claims = claims.filter((_, claimOffset) => claimOffset !== pointIndex);
    if (claims.length === 0) claims.push("");
    slide.claims = claims;
  }
  outlineDirtyKeys.add(`s${index}:points`);
  renderOutlineEditor();
}

// 变更视觉标记：左侧竖线高亮（数据行）。
function markOutlineCardChanged(card, index) {
  if (!card) return;
  const dirty = ["title", "claims:0", "body", "support", "points", "order"]
    .some((key) => outlineDirtyKeys.has(`s${index}:${key}`));
  card.classList.toggle("changed", dirty);
}

function updateOutlineConfirmState() {
  const slides = outlineEditorData?.slides || [];
  const hasEmptyTitle = slides.some((slide) => !String(slide.title || "").trim());
  outlineConfirmButton.disabled = slides.length === 0 || hasEmptyTitle;
}

// ---------- 提交 ----------

function collectOutlineSlides() {
  return (outlineEditorData?.slides || []).map((slide) => ({
    id: slide.id,
    title: String(slide.title || "").trim(),
    body: String(slide.body || "").trim(),
    prompt: String(slide.prompt || slide.body || "").trim(),
    claims: Array.isArray(slide.claims) ? slide.claims : [],
    claim_boundary: slide.claim_boundary || "",
    acceptance_criteria: Array.isArray(slide.acceptance_criteria) ? slide.acceptance_criteria : [],
    narrative_intent: slide.narrative_intent || "",
    visual_intent: slide.visual_intent || "",
    content: slide.content && typeof slide.content === "object" ? slide.content : {},
    source_refs: Array.isArray(slide.source_refs) ? slide.source_refs : [],
  }));
}

async function confirmOutlineAndStart() {
  if (!outlineEditorData) return;
  const slides = collectOutlineSlides();
  if (!slides.length) throw new Error("大纲没有页面，无法开始生成。");
  if (slides.some((slide) => !slide.title)) throw new Error("存在空标题页面，请先填写标题后再确认。");
  const base = buildOutlineRequestPayload(normalizePromptForSubmit(promptInput.value));
  const payload = {
    ...base,
    deck_thesis: String(outlineDeckThesis.value || "").trim(),
    slides,
  };
  resetLog("正在创建任务...");
  setState("创建中", "running");
  updateButtons(false);
  const response = await api("/api/outline/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  appendLog(commandSummary("确认大纲并创建任务", response));
  if (!response.ok) {
    setState("创建失败", "error");
    updateButtons(true);
    throw new Error(response.message || "创建任务失败。");
  }
  closeOutlineEditor();
  await activateCreatedTask(response.data);
}

// 与 createCodexTask 成功后一致的任务激活流程。
async function activateCreatedTask(data) {
  activeProject = data.project;
  activeTaskId = String(data.task_id || "");
  activeProjectTitle = userFacingTaskTitle(data.task_title || activeProject);
  latestStatus = null;
  setWorkbenchView("task_detail");
  saveActiveProject();
  syncBrowserProjectUrl(activeProject);
  selectedSlide = 1;
  projectName.textContent = userFacingTaskTitle(data.task_title || activeProject);
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

// ---------- 事件绑定 ----------

outlineDeckThesis?.addEventListener("input", () => {
  if (!outlineEditorData) return;
  outlineEditorData.deck_thesis = outlineDeckThesis.value;
  outlineDirtyKeys.add("thesis");
  outlineDeckThesis.closest("label")?.classList.add("changed");
});

outlineConfirmButton?.addEventListener("click", () => runAction(outlineConfirmButton, confirmOutlineAndStart));

outlineDirectGenerate?.addEventListener("click", () => {
  if (outlineSkipConfirm) outlineSkipConfirm.checked = true;
  closeOutlineEditor();
  return createCodexTask();
});

outlineCancelEdit?.addEventListener("click", () => runAction(outlineCancelEdit, closeOutlineEditor));

outlineAddSlide?.addEventListener("click", () => {
  outlineEditorData.slides.push({
    id: outlineEditorData.slides.length + 1,
    title: "",
    body: "",
    prompt: "",
    claims: [""],
    content: {},
    claim_boundary: "open",
    acceptance_criteria: [],
    narrative_intent: "",
    visual_intent: "",
    source_refs: [],
  });
  outlineDirtyKeys.add("order");
  renderOutlineEditor();
  const cards = outlineSlideList.querySelectorAll(".outline-slide-card");
  cards[cards.length - 1]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

// 切换工作流视图时关闭大纲面板，避免回到 composer 时残留编辑状态。
changeWorkflowMode?.addEventListener("click", closeOutlineEditor);
