/**
 * DXF 파싱 관련 함수
 */
import { state, statusCopy, sleep, $ } from './state.js';
import { api } from './api.js';
import { setTab } from './tabs.js';
import { renderFileList } from './upload.js';
import { uploadOne, pollStatus } from './convert.js';
import { initSmartSelects, applyTemplateSelections } from './smart-select.js';
import { updateResultList, renderResultView } from './results.js';

export async function loadEntitiesTable(file) {
  if (!file?.fileId) return;
  const data = await api(`/parsing/${file.fileId}/entities-table`);
  file.entitiesTable = Array.isArray(data.rows) ? data.rows : [];
  file.entitiesTableColumns = Array.isArray(data.columns) ? data.columns : [];
  if (Array.isArray(file.entitiesTable)) {
    const columns = Array.isArray(file.entitiesTableColumns) ? file.entitiesTableColumns : [];
    const handleKey = columns.includes("handle") ? "handle" : "HANDLE";
    const set = new Set();
    file.entitiesTable.forEach((row) => {
      const val = row?.[handleKey];
      if (val) set.add(String(val));
    });
    file.entityHandleCount = set.size || file.entitiesTable.length;
  }
}

export async function loadParsed(file) {
  if (!file?.fileId) return;
  const data = await api(`/parsing/${file.fileId}/parsed1`);
  file.parsedData = data;
  const layerNames = Array.isArray(data.layers)
    ? data.layers.map((l) => l.name || l.layer || l).filter(Boolean)
    : [];
  const blockNames = Array.isArray(data.blocks)
    ? data.blocks.map((b) => b.name || b.block_name || b).filter(Boolean)
    : [];
  const isTemplate = !state.templateFile || state.templateFile === file;
  if (!state.templateFile) state.templateFile = file;
  if (isTemplate) {
    if (layerNames.length) state.layerOptions = layerNames;
    if (blockNames.length) state.blockOptions = blockNames;
    state.selectedOptions["template-file-select"] = [state.templateFile.name];
    applyTemplateSelections();
  } else if (!state.selectedOptions["template-file-select"] && state.templateFile) {
    state.selectedOptions["template-file-select"] = [state.templateFile.name];
  }
  initSmartSelects();
  updateResultList(true);
  renderResultView();
}

export async function loadSemanticSummary(file) {
  if (!file?.fileId) return;
  const data = await api(`/parsing/${file.fileId}/semantic-summary`);
  file.semanticSummary = data;
}

export async function refreshSemanticSummary(file, retries = 4) {
  if (!file?.fileId) return;
  for (let i = 0; i <= retries; i++) {
    await loadSemanticSummary(file);
    const summary = file.semanticSummary || {};
    const hasBorder = (summary.border_count || 0) > 0;
    const hasAxis = Array.isArray(summary.axis_summaries) && summary.axis_summaries.length > 0;
    const hasColumns = (summary.column_count || 0) > 0;
    const hasWalls = (summary.wall_count || 0) > 0;
    const hasRooms = (summary.room_count || 0) > 0;
    const hasDoors = (summary.door_count || 0) > 0;
    if (hasBorder || hasAxis || hasColumns || hasWalls || hasRooms || hasDoors) return;
    await sleep(800);
  }
}

export async function refreshEntitiesTable(file, retries = 4) {
  if (!file?.fileId) return;
  for (let i = 0; i <= retries; i++) {
    try {
      await loadEntitiesTable(file);
      if (Array.isArray(file.entitiesTable) && file.entitiesTable.length > 0) return;
    } catch (err) {
      // entities-table 준비 전 404는 잠시 대기 후 재시도
    }
    await sleep(800);
  }
}

export async function refreshParsedData(file, retries = 4) {
  if (!file?.fileId) return;
  for (let i = 0; i <= retries; i++) {
    try {
      await loadParsed(file);
      const hasTables = !!(file.parsedData && file.parsedData.tables);
      const hasLayers = Array.isArray(file.parsedData?.layers) && file.parsedData.layers.length > 0;
      const hasBlocks = Array.isArray(file.parsedData?.blocks) && file.parsedData.blocks.length > 0;
      if (file.parsedData && (hasTables || hasLayers || hasBlocks)) return;
    } catch (err) {
      // parsed1 준비 전 오류는 잠시 대기 후 재시도
    }
    await sleep(800);
  }
}

export async function startParse() {
  if (!state.loggedIn) {
    alert("로그인 후 이용 가능합니다.");
    return setTab("login");
  }
  if (state.analyzeFiles.length === 0) return alert("분석할 DXF 파일을 먼저 업로드하세요.");
  const btn = $("btnParse");
  if (btn) btn.disabled = true;
  if (btn) btn.classList.add("is-loading");
  for (const file of state.analyzeFiles) {
    try {
      await uploadOne(file, "/parsing/upload");
      await api(`/parsing/${file.fileId}/parse1`, { method: "POST" });
      await pollStatus(file, "analyze");
      await refreshParsedData(file).catch(() => {});
      await refreshEntitiesTable(file).catch(() => {});
    } catch (err) {
      file.status = "failed";
      file.statusLabel = statusCopy.failed;
      file.log = err.message || "파싱 실패";
      renderFileList("analyze");
    }
  }
  if (btn) btn.disabled = false;
  if (btn) btn.classList.remove("is-loading");

  // 파싱 완료 후 결과 섹션 표시
  const doneFiles = state.analyzeFiles.filter((f) => f.status === "done");
  if (doneFiles.length > 0) {
    const resultSection = $("resultSection");
    if (resultSection) resultSection.style.display = "grid";
    if (!state.selectedResult) state.selectedResult = doneFiles[0];
    updateResultList(true);
    renderResultView();
  }
}
