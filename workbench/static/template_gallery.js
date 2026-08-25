// template_gallery.js — C13-B 模板画廊：浏览 / 分类 / 详情 / 选择 21 套模板
// 唯一数据源：GET /api/templates（服务端读取 my-ppt-skill/ppt-ai-core/templates/layouts/layouts_index.json）

const CATEGORY_LABELS = {
  brand: "品牌风格",
  general: "通用风格",
  scenario: "场景专用",
  government: "政企模板",
  special: "特殊风格",
};

const CATEGORY_COLORS = {
  brand: "#3b5bdb",
  general: "#0ca678",
  scenario: "#f08c00",
  government: "#c92a2a",
  special: "#7048e8",
};

const QUICK_LOOKUP_LABELS = {
  strategy: "战略",
  board: "董事会",
  general_business: "商务",
  technology: "科技",
  government: "政企",
  academic: "学术",
  medical: "医疗",
  psychology: "心理",
  finance: "金融",
  certification: "认证",
  energy: "能源",
  creative: "创意",
};

const browseTemplates = document.getElementById("browseTemplates");
const templateGalleryModal = document.getElementById("templateGalleryModal");
const templateGalleryClose = document.getElementById("templateGalleryClose");
const templateGalleryCategoriesEl = document.getElementById("templateGalleryCategories");
const templateGalleryQuickLookupEl = document.getElementById("templateGalleryQuickLookup");
const templateGalleryGrid = document.getElementById("templateGalleryGrid");
const templateGalleryDetail = document.getElementById("templateGalleryDetail");
const selectedTemplateBadge = document.getElementById("selectedTemplateBadge");
const selectedTemplateBadgeName = document.getElementById("selectedTemplateBadgeName");

let selectedTemplateId = "";
let galleryTemplates = [];
let galleryCategories = [];
let galleryQuickLookup = {};
let activeGalleryCategory = "all";
let galleryDetailTemplateId = "";
let galleryLoading = false;

function getSelectedTemplateId() {
  return selectedTemplateId;
}

function galleryTemplateById(templateId) {
  return galleryTemplates.find((item) => item.id === templateId) || null;
}

function templateThumbColor(template) {
  return CATEGORY_COLORS[template.category] || "#495057";
}

function templateInitial(template) {
  const first = String(template.label || template.id || "?").trim().charAt(0);
  return /[a-zA-Z0-9]/.test(first) ? first.toUpperCase() : first || "?";
}

function templateSceneLabels(templateId) {
  return Object.entries(galleryQuickLookup)
    .filter(([, ids]) => Array.isArray(ids) && ids.includes(templateId))
    .map(([key]) => QUICK_LOOKUP_LABELS[key] || key);
}

function setSelectedTemplateId(templateId) {
  selectedTemplateId = String(templateId || "");
  if (selectedTemplateBadge && selectedTemplateBadgeName) {
    const template = selectedTemplateId ? galleryTemplateById(selectedTemplateId) : null;
    selectedTemplateBadgeName.textContent = template ? template.label : selectedTemplateId;
    selectedTemplateBadge.classList.toggle("hidden", !selectedTemplateId);
  }
  renderGalleryGrid();
}

function refreshSelectedTemplateBadge() {
  setSelectedTemplateId(selectedTemplateId);
}

function visibleTemplateIds() {
  if (activeGalleryCategory === "all") return galleryTemplates.map((item) => item.id);
  if (activeGalleryCategory.startsWith("quick:")) {
    const key = activeGalleryCategory.slice("quick:".length);
    return Array.isArray(galleryQuickLookup[key]) ? galleryQuickLookup[key] : [];
  }
  const category = galleryCategories.find((item) => item.id === activeGalleryCategory);
  return category ? category.template_ids : [];
}

function renderGalleryCategories() {
  if (!templateGalleryCategoriesEl) return;
  const categoryButtons = [
    `<button type="button" class="gallery-category${activeGalleryCategory === "all" ? " active" : ""}" data-category="all">全部 (${galleryTemplates.length})</button>`,
    ...galleryCategories.map((category) => {
      const label = CATEGORY_LABELS[category.id] || category.label || category.id;
      return `<button type="button" class="gallery-category${activeGalleryCategory === category.id ? " active" : ""}" data-category="${escapeHtml(category.id)}">${escapeHtml(label)} (${category.template_ids.length})</button>`;
    }),
  ].join("");
  templateGalleryCategoriesEl.innerHTML = categoryButtons;
  if (templateGalleryQuickLookupEl) {
    const sceneButtons = Object.entries(galleryQuickLookup)
      .map(([key, ids]) => {
        const label = QUICK_LOOKUP_LABELS[key] || key;
        const active = activeGalleryCategory === `quick:${key}`;
        return `<button type="button" class="gallery-scene${active ? " active" : ""}" data-scene="${escapeHtml(key)}">${escapeHtml(label)} (${ids.length})</button>`;
      })
      .join("");
    templateGalleryQuickLookupEl.innerHTML = sceneButtons;
  }
}

function renderGalleryGrid() {
  if (!templateGalleryGrid) return;
  const visible = visibleTemplateIds().map(galleryTemplateById).filter(Boolean);
  if (!visible.length) {
    templateGalleryGrid.innerHTML = '<div class="empty-note">该分类下暂无模板。</div>';
    return;
  }
  templateGalleryGrid.innerHTML = visible
    .map((template) => {
      const selected = template.id === selectedTemplateId;
      const color = templateThumbColor(template);
      return `<button type="button" class="template-card${selected ? " selected" : ""}" data-template-id="${escapeHtml(template.id)}">
        <span class="template-thumb" style="--thumb-color: ${color}">
          <span class="template-thumb-letter">${escapeHtml(templateInitial(template))}</span>
          <span class="template-thumb-bar bar-one"></span>
          <span class="template-thumb-bar bar-two"></span>
          <span class="template-thumb-bar bar-three"></span>
        </span>
        <span class="template-card-name">${escapeHtml(template.label)}</span>
        <span class="template-card-summary">${escapeHtml(template.summary)}</span>
        <span class="template-card-check">已选</span>
      </button>`;
    })
    .join("");
}

function showTemplateDetail(templateId) {
  const template = galleryTemplateById(templateId);
  if (!template || !templateGalleryDetail || !templateGalleryGrid) return;
  galleryDetailTemplateId = template.id;
  const scenes = templateSceneLabels(template.id);
  const scenesHtml = scenes.length
    ? `<p class="template-detail-scenes">适用场景：${scenes.map(escapeHtml).join("、")}</p>`
    : "";
  templateGalleryDetail.innerHTML = `
    <div class="template-detail-thumb" style="--thumb-color: ${templateThumbColor(template)}">
      <span class="template-thumb-letter">${escapeHtml(templateInitial(template))}</span>
      <span class="template-thumb-bar bar-one"></span>
      <span class="template-thumb-bar bar-two"></span>
      <span class="template-thumb-bar bar-three"></span>
    </div>
    <div class="template-detail-info">
      <h3>${escapeHtml(template.label)}</h3>
      <p class="template-detail-tone">${escapeHtml(template.tone)}</p>
      <p class="template-detail-summary">${escapeHtml(template.summary)}</p>
      ${scenesHtml}
    </div>
    <div class="template-detail-actions">
      <button type="button" class="ghost-action" data-gallery-action="back">返回</button>
      <button type="button" class="primary-action" data-gallery-action="pick">选中此模板</button>
    </div>`;
  templateGalleryGrid.classList.add("hidden");
  templateGalleryDetail.classList.remove("hidden");
}

function hideTemplateDetail() {
  galleryDetailTemplateId = "";
  templateGalleryGrid?.classList.remove("hidden");
  templateGalleryDetail?.classList.add("hidden");
}

function selectTemplateFromGallery(templateId) {
  const template = galleryTemplateById(templateId);
  if (!template) return;
  setSelectedTemplateId(template.id);
  if (typeof saveCreationDraft === "function") saveCreationDraft();
  appendLog(`已选择模板：${template.label}`);
  closeTemplateGallery();
}

async function openTemplateGallery() {
  if (!templateGalleryModal) return;
  if (!galleryTemplates.length && !galleryLoading) {
    galleryLoading = true;
    try {
      const response = await api("/api/templates");
      if (!response.ok) throw new Error(response.message || "读取模板列表失败。");
      const data = response.data || {};
      galleryCategories = Array.isArray(data.categories) ? data.categories : [];
      galleryTemplates = Array.isArray(data.templates) ? data.templates : [];
      galleryQuickLookup =
        data.quick_lookup && typeof data.quick_lookup === "object" ? data.quick_lookup : {};
      activeGalleryCategory = "all";
      renderGalleryCategories();
      renderGalleryGrid();
      refreshSelectedTemplateBadge();
    } catch (error) {
      appendLog(error.message || String(error));
      if (templateGalleryGrid) {
        templateGalleryGrid.innerHTML = `<div class="empty-note">模板列表读取失败：${escapeHtml(error.message || "未知错误")}</div>`;
      }
    } finally {
      galleryLoading = false;
    }
  }
  hideTemplateDetail();
  templateGalleryModal.classList.remove("hidden");
}

function closeTemplateGallery() {
  if (!templateGalleryModal) return;
  templateGalleryModal.classList.add("hidden");
  hideTemplateDetail();
}

templateGalleryClose?.addEventListener("click", closeTemplateGallery);
templateGalleryModal?.addEventListener("click", (event) => {
  if (event.target.closest("[data-gallery-close]")) closeTemplateGallery();
});
templateGalleryCategoriesEl?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-category]");
  if (!button) return;
  activeGalleryCategory = button.dataset.category;
  hideTemplateDetail();
  renderGalleryCategories();
  renderGalleryGrid();
});
templateGalleryQuickLookupEl?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-scene]");
  if (!button) return;
  activeGalleryCategory = `quick:${button.dataset.scene}`;
  hideTemplateDetail();
  renderGalleryCategories();
  renderGalleryGrid();
});
templateGalleryGrid?.addEventListener("click", (event) => {
  const card = event.target.closest("[data-template-id]");
  if (!card) return;
  showTemplateDetail(card.dataset.templateId);
});
templateGalleryDetail?.addEventListener("click", (event) => {
  const action = event.target.closest("[data-gallery-action]")?.dataset.galleryAction;
  if (action === "back") {
    hideTemplateDetail();
    return;
  }
  if (action === "pick" && galleryDetailTemplateId) {
    selectTemplateFromGallery(galleryDetailTemplateId);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && templateGalleryModal && !templateGalleryModal.classList.contains("hidden")) {
    closeTemplateGallery();
  }
});
