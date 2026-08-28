// api_client.js — C13-0 拆分：网络请求封装 + 下载工具（由 app.js 原样迁移）

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return { ok: response.ok, status: response.status, message: text || response.statusText || "Request failed", data: {} };
}

async function recordTaskEvent(eventType, payload = {}) {
  if (!activeTaskId) return;
  try {
    const response = await api(`/api/workbench/tasks/${encodeURIComponent(activeTaskId)}/events`, {
      method: "POST",
      body: JSON.stringify({
        event_type: eventType,
        payload: {
          project: activeProject || "",
          slide_id: selectedSlide || 0,
          ...payload,
        },
      }),
    });
  } catch (error) {
    appendLog(`事件记录失败：${error.message || String(error)}`);
  }
}



function pptDownloadUrl() {
  return `/api/projects/${encodeURIComponent(activeProject)}/export-pptx`;
}

function pptDownloadFilename() {
  return `${activeProject || "ppt"}.pptx`;
}

async function downloadCurrentDeck() {
  if (!activeProject) return;
  const response = await fetch(pptDownloadUrl(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`下载失败：HTTP ${response.status}`);
  }
  const blob = await response.blob();
  if (!blob.size) {
    throw new Error("下载失败：服务端返回了空文件。");
  }
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = pptDownloadFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  await recordTaskEvent("download_pptx", { source: "blob_download", bytes: blob.size });
  appendLog(`PPT 下载已开始：${pptDownloadFilename()}（${blob.size} bytes）。`);
}



function singleSlideDownloadFilename(slideId = selectedSlide) {
  return `${activeProject || "ppt"}-slide-${String(slideId).padStart(2, "0")}.pptx`;
}

function triggerAttachmentDownload(url, filename = "") {
  const link = document.createElement("a");
  link.href = url;
  if (filename) link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function downloadBlob(url, filename) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`下载失败：HTTP ${response.status}`);
  }
  const blob = await response.blob();
  if (!blob.size) {
    throw new Error("下载失败：服务端返回了空文件。");
  }
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  return blob.size;
}
