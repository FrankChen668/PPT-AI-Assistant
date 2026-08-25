let stagedDocumentSources = [];

function parseDocumentSourceInputs() {
  const raw = String(documentSourceInput?.value || "");
  return raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function collectDocumentSourceInputs() {
  const stagedPaths = stagedDocumentSources.map((item) => item.source_path);
  const sourceInputs = [...parseDocumentSourceInputs(), ...stagedPaths]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  return [...new Set(sourceInputs)];
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function renderDocumentSourceList() {
  if (!documentSourceList || !documentUploadHint) return;
  if (!stagedDocumentSources.length) {
    documentUploadHint.textContent = "尚未上传文件。";
    documentSourceList.innerHTML = "";
    clearDocumentUploads && (clearDocumentUploads.disabled = true);
    return;
  }
  documentUploadHint.textContent = `已上传 ${stagedDocumentSources.length} 个文件，创建任务时会自动导入。`;
  documentSourceList.innerHTML = stagedDocumentSources
    .map(
      (item) =>
        `<div class="document-source-item"><strong>${escapeHtml(item.filename)}</strong><span>${escapeHtml(
          formatBytes(item.size_bytes),
        )}</span></div>`,
    )
    .join("");
  clearDocumentUploads && (clearDocumentUploads.disabled = false);
}

function bytesToBase64(bytes) {
  const chunk = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunk) {
    const slice = bytes.subarray(index, index + chunk);
    binary += String.fromCharCode(...slice);
  }
  return btoa(binary);
}

async function stageDocumentFile(file) {
  const filename = String(file?.name || "").trim();
  if (!filename) throw new Error("文件名为空。");
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const contentBase64 = bytesToBase64(bytes);
  const response = await api("/api/workbench/uploads", {
    method: "POST",
    body: JSON.stringify({
      filename,
      content_base64: contentBase64,
    }),
  });
  if (!response.ok) {
    throw new Error(response.message || `上传失败：${filename}`);
  }
  const staged = response.data || {};
  return {
    filename: staged.filename || filename,
    size_bytes: Number(staged.size_bytes || file.size || 0),
    source_path: String(staged.source_path || ""),
    relative_path: String(staged.relative_path || ""),
  };
}

async function addDocumentFiles(files) {
  const list = Array.from(files || []);
  if (!list.length) return;
  documentUploadHint && (documentUploadHint.textContent = "正在上传文件...");
  for (const file of list) {
    const staged = await stageDocumentFile(file);
    if (!staged.source_path) continue;
    const duplicated = stagedDocumentSources.some((item) => item.source_path === staged.source_path);
    if (!duplicated) stagedDocumentSources.push(staged);
  }
  renderDocumentSourceList();
  saveCreationDraft();
}

function clearStagedDocumentSources() {
  stagedDocumentSources = [];
  if (documentFileInput) documentFileInput.value = "";
  renderDocumentSourceList();
}

window.WorkbenchAppStateOrchestration = {
  parseDocumentSourceInputs,
  collectDocumentSourceInputs,
  formatBytes,
  renderDocumentSourceList,
  bytesToBase64,
  stageDocumentFile,
  addDocumentFiles,
  clearStagedDocumentSources,
};
