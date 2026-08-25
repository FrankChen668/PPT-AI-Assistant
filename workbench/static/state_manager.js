// state_manager.js — C13-0 拆分：DOM 引用 / 全局状态 / 通用工具（由 app.js 原样迁移）
const deckType = document.getElementById("deckType");
const pageCount = document.getElementById("pageCount");
const sceneSelect = document.getElementById("sceneSelect");
const targetPageCount = document.getElementById("targetPageCount");
const styleProfile = document.getElementById("styleProfile");
const templateMode = document.getElementById("templateMode");
const workflowMode = document.getElementById("workflowMode");
const modeSelectPanel = document.getElementById("modeSelectPanel");
const modeOptions = Array.from(document.querySelectorAll(".mode-option"));
const recentTaskList = document.getElementById("recentTaskList");
const newTaskButton = document.getElementById("newTaskButton");
const showTaskCenter = document.getElementById("showTaskCenter");
const changeWorkflowMode = document.getElementById("changeWorkflowMode");
const composerModeTitle = document.getElementById("composerModeTitle");
const composerModeDetail = document.getElementById("composerModeDetail");
const promptInput = document.getElementById("promptInput");
const documentSourceField = document.getElementById("documentSourceField");
const createTask = document.getElementById("createTask");
const projectName = document.getElementById("projectName");
const routeMeta = document.getElementById("routeMeta");
const templateMeta = document.getElementById("templateMeta");
const projectState = document.getElementById("projectState");
const nextActionTitle = document.getElementById("nextActionTitle");
const nextActionButton = document.getElementById("nextActionButton");
const nextActionPanel = document.getElementById("nextActionPanel");
const userBlockerPanel = document.getElementById("userBlockerPanel");
const userBlockerTitle = document.getElementById("userBlockerTitle");
const userBlockerDetail = document.getElementById("userBlockerDetail");
const userBlockerAction = document.getElementById("userBlockerAction");
const resumeChooser = document.getElementById("resumeChooser");
const resumeProjectList = document.getElementById("resumeProjectList");
const hideResumeChooser = document.getElementById("hideResumeChooser");
const taskCenterPanel = document.getElementById("taskCenterPanel");
const taskList = document.getElementById("taskList");
const taskCenterSearch = document.getElementById("taskCenterSearch");
const taskCenterFilter = document.getElementById("taskCenterFilter");
const taskBatchDelete = document.getElementById("taskBatchDelete");
const showNewTaskComposer = document.getElementById("showNewTaskComposer");
const taskDetailShell = document.getElementById("taskDetailShell");
const detailInspector = document.getElementById("detailInspector");
const collapseInspector = document.getElementById("collapseInspector");
const expandInspector = document.getElementById("expandInspector");
const inspectorContentPanel = document.getElementById("inspectorContentPanel");
const inspectorVersionsPanel = document.getElementById("inspectorVersionsPanel");
const inspectorTabs = Array.from(document.querySelectorAll("[data-inspector-tab]"));
const workflowSteps = Array.from(document.querySelectorAll(".workflow-step"));
const refreshStatus = document.getElementById("refreshStatus");
const slideList = document.getElementById("slideList");
const slideCountLabel = document.getElementById("slideCountLabel");
const pagePromptPanel = document.getElementById("pagePromptPanel");
const pagePromptTitle = document.getElementById("pagePromptTitle");
const currentPageActionHint = document.getElementById("currentPageActionHint");
const currentPageType = document.getElementById("currentPageType");
const currentContentHandling = document.getElementById("currentContentHandling");
const currentPageStyle = document.getElementById("currentPageStyle");
const currentPagePrompt = document.getElementById("currentPagePrompt");
const currentPageIterationNote = document.getElementById("currentPageIterationNote");
const autoGeneratePage = document.getElementById("autoGeneratePage");
const restorePreviousRevision = document.getElementById("restorePreviousRevision");
const repairCurrentPage = document.getElementById("repairCurrentPage");
const downloadCurrentPage = document.getElementById("downloadCurrentPage");
const deleteCurrentPage = document.getElementById("deleteCurrentPage");
const appendSlideFromList = document.getElementById("appendSlideFromList");
const insertSlideAfterCurrent = document.getElementById("insertSlideAfterCurrent");
const pageStream = document.getElementById("pageStream");
const selectedSlideTitle = document.getElementById("selectedSlideTitle");
const refreshPreview = document.getElementById("refreshPreview");
const regenSlide = document.getElementById("regenSlide");
const generatePacket = document.getElementById("generatePacket");
const repairSlide = document.getElementById("repairSlide");
const qaSlide = document.getElementById("qaSlide");
const exportDeck = document.getElementById("exportDeck");
const autoGenerateMissingPages = document.getElementById("autoGenerateMissingPages");
const freshReleaseSafe = document.getElementById("freshReleaseSafe");
const freshPremium = document.getElementById("freshPremium");
const exportReadiness = document.getElementById("exportReadiness");
const exportReadinessText = document.getElementById("exportReadinessText");
const qaEvidenceBadges = document.getElementById("qaEvidenceBadges");
const qaEvidenceMeta = document.getElementById("qaEvidenceMeta");
const refreshRevisions = document.getElementById("refreshRevisions");
const revisionList = document.getElementById("revisionList");
const refreshQaReport = document.getElementById("refreshQaReport");
const qaReport = document.getElementById("qaReport");
const qaEvidencePreview = document.getElementById("qaEvidencePreview");
const contactSheetPreview = document.getElementById("contactSheetPreview");
const previewHint = document.getElementById("previewHint");
const previewLoading = document.getElementById("previewLoading");
const previewRetryBox = document.getElementById("previewRetryBox");
const previewRetryMessage = document.getElementById("previewRetryMessage");
const previewRetryButton = document.getElementById("previewRetryButton");
const previewStageShell = document.getElementById("previewStageShell");
const previewStageSizer = document.getElementById("previewStageSizer");
const previewStage = document.getElementById("previewStage");
const previewZone = document.querySelector(".preview-zone");
const svgPreview = document.getElementById("svgPreview");
const fitPreview = document.getElementById("fitPreview");
const previewZoom = document.getElementById("previewZoom");
const fullscreenPreview = document.getElementById("fullscreenPreview");
const startSlideshow = document.getElementById("startSlideshow");
const slideshowOverlay = document.getElementById("slideshowOverlay");
const slideshowFrame = document.getElementById("slideshowFrame");
const slideshowEmpty = document.getElementById("slideshowEmpty");
const slideshowPrev = document.getElementById("slideshowPrev");
const slideshowNext = document.getElementById("slideshowNext");
const closeSlideshow = document.getElementById("closeSlideshow");
const slideshowCounter = document.getElementById("slideshowCounter");
const resetPreview = document.getElementById("resetPreview");
const toggleSetupPanel = document.getElementById("toggleSetupPanel");
const setupContent = document.getElementById("setupContent");
const createWorkspace = document.getElementById("createWorkspace");
const modelConfigView = document.getElementById("modelConfigView");
const openPreferencePopover = document.getElementById("openPreferencePopover");
const openPreferencePopoverRail = document.getElementById("openPreferencePopoverRail");
const closePreferencePopover = document.getElementById("closePreferencePopover");
const generationProgressiveSetting = document.getElementById("generationProgressiveSetting");
const connectionListEl = document.getElementById("connectionList");
const connectionFormEl = document.getElementById("connectionForm");
const connectionEditingIdInput = document.getElementById("connectionEditingId");
const connectionNameInput = document.getElementById("connectionName");
const connectionProviderSelect = document.getElementById("connectionProvider");
const connectionBaseUrlInput = document.getElementById("connectionBaseUrl");
const connectionApiKeyInput = document.getElementById("connectionApiKey");
const connectionFormStatus = document.getElementById("connectionFormStatus");
const addConnectionButton = document.getElementById("addConnection");
const cancelConnectionFormButton = document.getElementById("cancelConnectionForm");
const saveConnectionButton = document.getElementById("saveConnection");
const modelSubtabButtons = Array.from(document.querySelectorAll("[data-model-tab]"));
const connectionsSection = document.getElementById("connectionsSection");
const routingSection = document.getElementById("routingSection");
const connectionTitleEl = document.getElementById("connectionTitle");
const connectionDescriptionEl = document.getElementById("connectionDescription");
const deleteConnectionButton = document.getElementById("deleteConnection");
const toggleConnectionEnabledButton = document.getElementById("toggleConnectionEnabledButton");
const keyMaskedEl = document.getElementById("keyMasked");
const replaceKeyButton = document.getElementById("replaceKey");
const protocolNoteEl = document.getElementById("protocolNote");
const testStatusTitleEl = document.getElementById("testStatusTitle");
const testStatusDetailEl = document.getElementById("testStatusDetail");
const refreshModelsButton = document.getElementById("refreshModels");
const duplicateConnectionButton = document.getElementById("duplicateConnection");
const roleRoutingStatusEl = document.getElementById("roleRoutingStatus");
const saveRoleRoutingButton = document.getElementById("saveRoleRouting");
const setupCollapsedSummary = document.getElementById("setupCollapsedSummary");
const collapsedProjectName = document.getElementById("collapsedProjectName");
const collapsedCreateTask = document.getElementById("collapsedCreateTask");
const appShell = document.querySelector(".app-shell");
const advancedPanel = document.getElementById("advancedPanel");
const toggleAdvancedPanel = document.getElementById("toggleAdvancedPanel");
const toggleLogPanel = document.getElementById("toggleLogPanel");
const toggleQaPanel = document.getElementById("toggleQaPanel");
const toggleRevisionPanel = document.getElementById("toggleRevisionPanel");
const logPanel = document.getElementById("logPanel");
const qaPanel = document.getElementById("qaPanel");
const revisionPanel = document.getElementById("revisionPanel");
const utilityPanels = [advancedPanel, logPanel, qaPanel, revisionPanel].filter(Boolean);
const utilityToggles = [toggleAdvancedPanel, toggleLogPanel, toggleQaPanel, toggleRevisionPanel].filter(Boolean);
const toastHost = document.getElementById("toastHost");
const slideReviewPanel = null;
const slideReviewHint = document.getElementById("slideReviewHint");
const slideReviewScoreGroup = document.getElementById("slideReviewScoreGroup");
const reviewUsableYes = document.getElementById("reviewUsableYes");
const reviewUsableNo = document.getElementById("reviewUsableNo");
const reviewEditableYes = document.getElementById("reviewEditableYes");
const reviewEditableNo = document.getElementById("reviewEditableNo");
const reviewNotes = document.getElementById("reviewNotes");
const saveSlideReview = document.getElementById("saveSlideReview");
const slideReviewMeta = document.getElementById("slideReviewMeta");
const reviewTagInputs = Array.from(document.querySelectorAll(".review-tag"));

const storage = window.WorkbenchStateStorage;
const workbenchConfig = window.WorkbenchConfig;
const taskRender = window.WorkbenchTaskRender;
const previewState = window.WorkbenchPreviewState.createPreviewState();
const WORKFLOW_CONFIG = workbenchConfig.workflowConfig;
const slideStateText = workbenchConfig.slideStateText;
const pageTypeLabels = workbenchConfig.pageTypeLabels;
const projectStateText = workbenchConfig.projectStateText;

const PREVIEW_PREF_KEY = "workbench.previewPrefs.v3";
const UI_PREF_KEY = "workbench.uiPrefs.v1";
const ACTIVE_PROJECT_KEY = "workbench.activeProject.v1";
const DRAFT_PREF_KEY = "workbench.creationDraft.v1";
const AUTO_OPTIMIZE_MAX_ATTEMPTS = 2;
const BATCH_GENERATION_MAX_CONCURRENCY = 3;
const MANUAL_GENERATION_MAX_CONCURRENCY = BATCH_GENERATION_MAX_CONCURRENCY;
const BATCH_GENERATION_CONSECUTIVE_FAILURE_LIMIT = 3;
const BATCH_GENERATION_TOTAL_FAILURE_LIMIT = 5;
const BATCH_GENERATION_FAILURE_RATIO_LIMIT = 0.1;
// Frontend contract sentinels for progressive page-stream status/cache-bust.
const PAGE_STREAM_PROGRESS_SENTINEL = "Generating ${blockStatus}";
const PAGE_STREAM_CACHE_BUST_SENTINEL = "slidePreviewVersion";

let activeProject = "";
let activeTaskId = "";
let activeProjectTitle = "";
let selectedSlide = 1;
let latestStatus = null;
let humanInterventionSlides = new Set();
const localPageDrafts = new Map();
const autoGenerationSlideTasks = new Map();
const manualGenerationQueue = [];
let manualGenerationActiveCount = 0;
const manualGenerationActiveSlides = new Set();
let manualGenerationQueuedSlides = new Set();
let autoGenerationRunning = false;
let autoGenerationTargetSlide = null;
let autoGenerationGlobalBusy = false;
let batchGenerationQueuedSlides = new Set();
const batchGenerationActiveSlides = new Set();
let slideListRenderSignature = "";
let autoGenerationPollTimer = null;
let autoCheckRunning = false;
let autoCheckTimer = null;
let allTasks = [];
let selectedReviewScore = null;
let currentGenerationSettings = {};
let slideshowSlide = 1;
let previewLoadFallbackTimer = null;
let previewLoadFallbackSlide = 0;
const SLOW_GENERATION_HINT_MS = 60000;
const VERY_SLOW_GENERATION_HINT_MS = 120000;
const slowGenerationHintTimers = new Map();

function slideListText(slides) {
  if (!slides || !slides.length) return "";
  return slides.map((item) => `第 ${item} 页`).join("、");
}

function cleanSlideIds(slides) {
  const ids = [];
  (Array.isArray(slides) ? slides : []).forEach((item) => {
    const slideId = Number(item);
    if (Number.isFinite(slideId) && slideId > 0 && !ids.includes(slideId)) ids.push(slideId);
  });
  return ids;
}

function missingSlidesTitle(slides, fallbackSlide = 0) {
  const ids = cleanSlideIds(slides);
  if (ids.length > 5) return `还有 ${ids.length} 页未生成`;
  if (ids.length) return `第 ${ids.join("、")} 页未生成`;
  return fallbackSlide > 0 ? `第 ${fallbackSlide} 页未生成` : "页面未生成";
}

function missingSlidesBlockerText(slides, fallbackSlide = 0) {
  const ids = cleanSlideIds(slides);
  if (!ids.length && fallbackSlide > 0) ids.push(fallbackSlide);
  if (!ids.length) return "还有页面未生成，暂时无法生成 PPT。";
  if (ids.length === 1) return `第 ${ids[0]} 页还未生成，暂时无法生成 PPT。`;
  if (ids.length <= 5) return `第 ${ids.join("、")} 页还未生成，暂时无法生成 PPT。`;
  return `还有 ${ids.length} 页未生成，暂时无法生成 PPT。请先补齐缺失页面。`;
}

function missingSlidesBlockerDetail(slides, fallbackSlide = 0) {
  const ids = cleanSlideIds(slides);
  if (!ids.length && fallbackSlide > 0) ids.push(fallbackSlide);
  return ids.length > 5 ? "暂时无法生成 PPT。请先补齐缺失页面。" : "暂时无法生成 PPT。";
}

function userFacingTaskTitle(value, fallback = "未命名 PPT 任务") {
  return taskRender?.userFacingTaskTitle ? taskRender.userFacingTaskTitle(value, fallback) : String(value || fallback);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function hasRawTechnicalDetails(message) {
  const value = String(message || "");
  return /([A-Za-z]:\\|\/[A-Za-z0-9_.-]+\/|Traceback|Error:|Exception:|\.py\b|\.js\b|\.md\b|doctor_export|build_project|ENOENT|ECONNREFUSED)/i.test(value);
}

const WORKBENCH_PAGE_TYPES = new Set(["content", "cover", "toc", "section"]);
const CONTENT_HANDLING_OPTIONS = new Set(["preserve", "polish", "expand"]);
const PAGE_STYLE_OPTIONS = new Set(["business_simple", "software_consulting"]);

function normalizeWorkbenchPageType(value) {
  const pageType = String(value || "").trim();
  return WORKBENCH_PAGE_TYPES.has(pageType) ? pageType : "content";
}

function normalizeContentHandling(value) {
  const contentHandling = String(value || "").trim();
  return CONTENT_HANDLING_OPTIONS.has(contentHandling) ? contentHandling : "polish";
}

function normalizePageStyle(value) {
  const pageStyle = String(value || "").trim();
  return PAGE_STYLE_OPTIONS.has(pageStyle) ? pageStyle : "business_simple";
}

function setCurrentPageTypeValue(value) {
  if (!currentPageType) return;
  currentPageType.value = normalizeWorkbenchPageType(value);
}

function setCurrentContentHandlingValue(value) {
  if (!currentContentHandling) return;
  currentContentHandling.value = normalizeContentHandling(value);
}

function setCurrentPageStyleValue(value) {
  if (!currentPageStyle) return;
  currentPageStyle.value = normalizePageStyle(value);
}

function normalizePromptForSubmit(value) {
  return String(value || "").trim();
}

function compactSentenceEnd(text) {
  return String(text || "").trim().replace(/[。.!！?？]+$/, "");
}

function userFacingGenerationError(error) {
  const message = String(error || "").trim();
  if (!message) return "";
  const folded = message.toLowerCase();
  if (
    folded.includes("page_type must be one of") ||
    folded.includes("execution_policy") ||
    folded.includes("visual_contract") ||
    folded.includes("generation_strategy")
  ) {
    return "页面生成设置不一致，请重新生成本页。";
  }
  if (folded.includes("real generation unavailable")) {
    return "现在无法生成真实页面，请先在模型配置里填好 API Key 再试。";
  }
  if (folded.includes("placeholder is dry-run only")) {
    return "当前只生成了示意占位页，不能作为正式结果交付，请配置好模型后重新生成。";
  }
  if (
    message.includes("HTTP 401") ||
    folded.includes("http 401") ||
    folded.includes("api key is invalid") ||
    folded.includes("invalid api key") ||
    folded.includes("unauthorized")
  ) {
    return "模型 API Key 无效，请在服务器 .env 或 Windows 环境变量中更新后重启服务。";
  }
  if (
    message.includes("HTTP 403") ||
    folded.includes("http 403") ||
    message.includes("PERMISSION_DENIED") ||
    folded.includes("permission_denied") ||
    folded.includes("denied access") ||
    folded.includes("forbidden")
  ) {
    return "模型权限不可用，请检查模型配置或联系管理员。";
  }
  if (
    message.includes("HTTP 500") ||
    message.includes("HTTP 502") ||
    message.includes("HTTP 503") ||
    message.includes("HTTP 504") ||
    folded.includes("http 500") ||
    folded.includes("http 502") ||
    folded.includes("http 503") ||
    folded.includes("http 504") ||
    folded.includes("unavailable") ||
    folded.includes("high demand")
  ) {
    return "模型服务临时繁忙，请稍后重新生成本页。";
  }
  if (
    message.includes("HTTP 429") ||
    folded.includes("http 429") ||
    message.includes("RESOURCE_EXHAUSTED") ||
    folded.includes("quota") ||
    folded.includes("rate-limits")
  ) {
    return "模型额度或频率已达上限，请稍后重试或切换模型。";
  }
  if (folded.includes("contrast") && (folded.includes("required>=") || folded.includes("text/background") || folded.includes("design_spec.md"))) {
    return "页面颜色对比度偏低，可能影响阅读。请重新生成本页，或要求文字更深、背景更浅。";
  }
  if (folded.includes("missing svg")) return "还有页面未生成。";
  if (folded.includes("qa failed") || folded.includes("qa gate") || folded.includes("visual quality blocked")) {
    return "当前页面还需处理，请重新生成后再继续。";
  }
  if (
    folded.includes("export failed") ||
    folded.includes("finalize failed") ||
    folded.includes("deck-finalize-failed") ||
    folded.includes("doctor_export")
  ) {
    return "PPT 生成失败，请先执行导出排障任务后重试。";
  }
  if (hasRawTechnicalDetails(message)) {
    return "生成没有完成，请点“重新生成”再试一次。";
  }
  return message
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)[0] || "生成失败，请重试。";
}

function userFacingReadinessReason(reason) {
  const raw = String(reason || "").trim();
  if (!raw) return "";
  const folded = raw.toLowerCase();
  if (folded.includes("missing slides")) return "还有页面没有生成画面，请先完成这些页面。";
  if (folded.includes("qa failed") || folded.includes("qa_failed")) return "当前页面还需处理，请重新生成后再继续。";
  if (folded.includes("budget policy")) return "页面内容超出建议上限，请先精简内容再生成 PPT。";
  return userFacingGenerationError(raw);
}

function readJsonStorage(key, fallback) {
  return storage.readJson(key, fallback);
}

function writeJsonStorage(key, payload) {
  storage.writeJson(key, payload);
}

function setButtonLabel(button, text) {
  if (!button) return;
  const label = String(text || "");
  button.setAttribute("aria-label", label);
  const labelNode = button.querySelector("span");
  if (labelNode) {
    labelNode.textContent = label;
    return;
  }
  button.textContent = label;
}

function loadPreviewPrefs() {
  const saved = readJsonStorage(PREVIEW_PREF_KEY, {});
  const options = previewZoom ? Array.from(previewZoom.options).map((item) => Number(item.value)) : [];
  const prefs = previewState.loadPrefs(saved, options);
  if (previewZoom) {
    previewZoom.value = String(prefs.manualScale);
  }
}

function savePreviewPrefs() {
  writeJsonStorage(PREVIEW_PREF_KEY, previewState.savePrefs());
}

function loadUiPrefs() {
  const saved = readJsonStorage(UI_PREF_KEY, {});
  const setupCollapsed = Boolean(saved.setupCollapsed);
  setSetupCollapsed(setupCollapsed, false);
  setPanelExpanded(advancedPanel, toggleAdvancedPanel, false, false);
  setPanelExpanded(logPanel, toggleLogPanel, false, false);
  setPanelExpanded(qaPanel, toggleQaPanel, false, false);
  setPanelExpanded(revisionPanel, toggleRevisionPanel, false, false);
}

function saveUiPrefs() {
  writeJsonStorage(UI_PREF_KEY, {
    setupCollapsed: appShell.classList.contains("setup-collapsed"),
    advancedExpanded: advancedPanel?.classList.contains("expanded") || false,
    logExpanded: logPanel?.classList.contains("expanded") || false,
    qaExpanded: qaPanel?.classList.contains("expanded") || false,
    revisionExpanded: revisionPanel?.classList.contains("expanded") || false,
  });
}

function setInspectorOpen(open, persist = true) {
  const shouldOpen = Boolean(open);
  taskDetailShell?.classList.toggle("inspector-collapsed", !shouldOpen);
  detailInspector?.classList.toggle("hidden", !shouldOpen);
  expandInspector?.classList.toggle("hidden", shouldOpen);
  collapseInspector?.setAttribute("aria-expanded", String(shouldOpen));
  expandInspector?.setAttribute("aria-expanded", String(shouldOpen));
  if (persist) saveUiPrefs();
}

function setInspectorTab(tabName) {
  const showVersions = tabName === "versions";
  inspectorTabs.forEach((button) => {
    const active = button.dataset.inspectorTab === tabName;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.setAttribute("tabindex", active ? "0" : "-1");
  });
  inspectorContentPanel?.classList.toggle("hidden", showVersions);
  inspectorContentPanel?.classList.toggle("active", !showVersions);
  inspectorVersionsPanel?.classList.toggle("hidden", !showVersions);
  inspectorVersionsPanel?.classList.toggle("active", showVersions);
  if (showVersions) loadRevisions();
}

