/**
 * 파일 업로드 및 드롭존 관리
 */
import { state, statusCopy, formatSize, $, API_BASE } from './state.js';
import { initSmartSelects } from './smart-select.js';
import { loadParsed } from './parse.js';

export function renderFileList(kind) {
  const listEl = kind === "convert" ? $("convertList") : $("analyzeList");
  const dropEl = kind === "convert" ? $("dropConvert") : $("dropAnalyze");
  const startBtn = kind === "convert" ? $("btnConvertStart") : $("btnParse");
  const downloadBtn = kind === "convert" ? $("btnConvertDownload") : null;
  const files = kind === "convert" ? state.convertFiles : state.analyzeFiles;

  const hasFiles = files.length > 0;
  if (dropEl) dropEl.style.display = hasFiles ? "none" : "block";
  if (listEl) listEl.style.display = hasFiles ? "flex" : "none";
  if (startBtn) startBtn.disabled = !hasFiles;
  if (downloadBtn) {
    const anyDone = files.some((f) => f.status === "done" && f.pathDxf);
    downloadBtn.style.display = anyDone ? "inline-flex" : "none";
    downloadBtn.disabled = !anyDone;
  }
  if (!hasFiles || !listEl) return;
  listEl.innerHTML = "";
  files.forEach((file, idx) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const canDownload = file.status === "done" && file.pathDxf && kind === "convert";
    row.innerHTML = `
      <div class="file-name">${file.name}</div>
      <div class="muted">${formatSize(file.size)}</div>
      <div class="status-pill ${file.status}">${file.statusLabel || statusCopy[file.status] || "-"}</div>
      <div class="progress"><div class="progress-bar" style="width:${file.progress || 0}%;"></div></div>
      <div class="file-log">${file.log || ""}</div>
      ${
        canDownload
          ? `<button class="btn" data-action="download" title="다운로드">다운로드</button>`
          : `<button class="btn ghost" data-action="remove" title="삭제">✕</button>`
      }
    `;
    row.querySelectorAll("button").forEach((btn) => {
      const action = btn.dataset.action;
      btn.onclick = () => {
        if (action === "download") {
          window.open(`${API_BASE}/convert/${file.fileId}/download?kind=dxf`, "_blank");
          return;
        }
        (kind === "convert" ? state.convertFiles : state.analyzeFiles).splice(idx, 1);
        renderFileList(kind);
      };
    });
    listEl.appendChild(row);
  });
  const addCard = document.createElement("div");
  addCard.className = "add-card";
  addCard.textContent = "+ 파일 추가";
  addCard.onclick = () => (kind === "convert" ? $("inputConvert") : $("inputAnalyze")).click();
  listEl.appendChild(addCard);
}

export function addFiles(kind, fileList) {
  const allow =
    kind === "convert"
      ? state.convertMode === "dxf2dwg"
        ? [".dxf"]
        : [".dwg"]
      : [".dxf"];
  const target = kind === "convert" ? state.convertFiles : state.analyzeFiles;
  Array.from(fileList).forEach((f) => {
    const ext = `.${(f.name.split(".").pop() || "").toLowerCase()}`;
    if (!allow.includes(ext)) {
      alert(`${allow.join(", ")} 확장자만 업로드할 수 있습니다.`);
      return;
    }
    target.push({
      kind,
      convertMode: kind === "convert" ? state.convertMode : null,
      fileObj: f,
      name: f.name,
      size: f.size,
      status: "ready",
      statusLabel: statusCopy.ready,
      progress: 0,
      log: "대기 중",
      fileId: null,
      pathDxf: null,
      parsedData: null,
    });
  });
  renderFileList(kind);
  if (kind === "analyze" && !state.templateFile && target.length > 0) {
    state.templateFile = target[0];
    state.selectedResult = target[0];
    state.selectedOptions["template-file-select"] = [target[0].name];
    initSmartSelects();
  }
}

export function bindDropzone(el, kind) {
  ["dragenter", "dragover"].forEach((evt) =>
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.remove("dragover");
    })
  );
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    addFiles(kind, e.dataTransfer.files);
  });
}
