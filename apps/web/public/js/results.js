/**
 * 파싱/분석 결과 표시
 */
import { state, $ } from './state.js';
import { renderDxfPreview } from './viewer.js';
import { refreshParsedData, refreshEntitiesTable, refreshSemanticSummary } from './parse.js';

export function updateResultList(forceSelect = false) {
  const list = $("resultList");
  if (!list) return;
  list.innerHTML = "";
  if (forceSelect && state.analyzeFiles.length > 0 && !state.selectedResult) {
    state.selectedResult = state.analyzeFiles[0];
  }
  if (state.analyzeFiles.length === 0) {
    list.innerHTML = '<div class="muted">파싱된 파일이 없습니다.</div>';
    return;
  }
  state.analyzeFiles.forEach((f) => {
    const btn = document.createElement("button");
    btn.className = "btn ghost";
    if (state.selectedResult === f) btn.classList.add("active");
    btn.textContent = f.name;
    btn.onclick = () => {
      state.selectedResult = f;
      updateResultList();
      if (!f.parsedData && f.fileId) {
        import('./parse.js').then(mod => mod.loadParsed(f).catch(() => {}));
      }
      if (!f.entitiesTable && f.fileId) {
        refreshEntitiesTable(f)
          .catch(() => {})
          .finally(renderResultView);
      } else {
        renderResultView();
      }
      if ($("aiResultSection") && $("aiResultSection").style.display !== "none") {
        refreshSemanticSummary(f)
          .catch(() => {})
          .finally(renderAiResultView);
      }
    };
    list.appendChild(btn);
  });
}

export function renderResultView() {
  const view = $("resultView");
  if (!view) return;
  const file = state.selectedResult;
  if (!file) {
    view.innerHTML = '<div class="muted">파싱 결과를 보려면 파일을 선택하세요.</div>';
    return;
  }
  if (!file.parsedData || !file.entitiesTable) {
    if (file.fileId) {
      if (!file._loadingParsed && !file.parsedData) {
        file._loadingParsed = true;
        refreshParsedData(file)
          .catch(() => {})
          .finally(() => {
            file._loadingParsed = false;
            renderResultView();
          });
      }
      if (!file._loadingEntities && !file.entitiesTable) {
        file._loadingEntities = true;
        refreshEntitiesTable(file)
          .catch(() => {})
          .finally(() => {
            file._loadingEntities = false;
            renderResultView();
          });
      }
    }
    view.innerHTML = '<div class="muted">파싱 결과를 불러오는 중입니다...</div>';
    return;
  }
  const data = file.parsedData;
  const layers = data.layers || [];
  const blocks = data.blocks || [];
  const totalEntities =
    typeof file.entityHandleCount === "number"
      ? file.entityHandleCount
      : file.entityTableView && Array.isArray(file.entityTableView.rows)
      ? file.entityTableView.rows.length
      : typeof data.total === "number"
      ? data.total
      : Array.isArray(data.entities)
      ? data.entities.length
      : Array.isArray(data.entity_table)
      ? data.entity_table.length
      : 0;
  const totalEntitiesLabel = Number(totalEntities || 0).toLocaleString("en-US");
  const entitiesTable = Array.isArray(file.entitiesTable) ? file.entitiesTable : [];
  const entitiesColumns = Array.isArray(file.entitiesTableColumns) ? file.entitiesTableColumns : [];
  const sourceRows = entitiesTable.length ? entitiesTable.slice(0, 50) : [];

  const visibleColumns = ["handle", "type", "layer", "coord_x", "coord_y", "coord_z", "text", "name", "radius", "actualMeasurement"];
  const coordColumns = new Set(["vertices", "startpoint", "endpoint", "center", "position"].map(v => v.toLowerCase()));
  const columnMap = new Map((entitiesColumns.length ? entitiesColumns : Object.keys(sourceRows[0] || {})).map(c => [String(c).toLowerCase(), c]));

  const formatCoord = (value) => {
    const num = typeof value === "number" ? value : 0;
    return (Math.round(num * 10000) / 10000).toFixed(4);
  };

  const extractCoords = (row) => {
    for (const key of coordColumns) {
      const actualKey = columnMap.get(key) || key;
      let raw = row?.[actualKey];
      if (!raw) continue;
      if (typeof raw === "string" && (raw.startsWith("{") || raw.startsWith("["))) {
        try { raw = JSON.parse(raw); } catch { continue; }
      }
      if (Array.isArray(raw) && raw[0]) {
        return { x: raw[0].x || 0, y: raw[0].y || 0, z: raw[0].z || 0 };
      }
      if (raw && typeof raw === "object") {
        return { x: raw.x || 0, y: raw.y || 0, z: raw.z || 0 };
      }
    }
    return null;
  };

  const headerCells = visibleColumns.map(c => `<th>${c === "actualMeasurement" ? "dim" : c}</th>`).join("");
  const entityRows = sourceRows.map(row => {
    const coord = extractCoords(row);
    return `<tr>
      <td>${row.handle || "-"}</td>
      <td>${row.type || "-"}</td>
      <td>${row.layer || "-"}</td>
      <td>${coord ? formatCoord(coord.x) : "-"}</td>
      <td>${coord ? formatCoord(coord.y) : "-"}</td>
      <td>${coord ? formatCoord(coord.z) : "-"}</td>
      <td>${row.text || "-"}</td>
      <td>${row.name || "-"}</td>
      <td>${row.radius ? formatCoord(row.radius) : "-"}</td>
      <td>${row.actualMeasurement ? formatCoord(row.actualMeasurement) : "-"}</td>
    </tr>`;
  }).join("");

  view.innerHTML = `
    <div class="stats-row">
      <div class="stat"><span class="stat-label">레이어</span><span class="stat-value">${layers.length}</span></div>
      <div class="stat"><span class="stat-label">블록</span><span class="stat-value">${blocks.length}</span></div>
      <div class="stat"><span class="stat-label">엔티티</span><span class="stat-value">${totalEntitiesLabel}</span></div>
    </div>
    <div class="table-wrapper" style="margin-top:12px; max-height:300px; overflow:auto;">
      <table class="entity-table">
        <thead><tr>${headerCells}</tr></thead>
        <tbody>${entityRows || '<tr><td colspan="10" class="muted">엔티티 없음</td></tr>'}</tbody>
      </table>
    </div>
  `;
}

export function renderAiResultView() {
  const view = $("aiResultView");
  const list = $("aiBorderList");
  if (!view) return;
  const file = state.selectedResult || state.analyzeFiles[0];
  if (!file) {
    view.textContent = "분석 결과를 불러오는 중입니다...";
    return;
  }
  const entries = [];
  state.analyzeFiles.forEach((f) => {
    const sum = f.semanticSummary || {};
    const axisItems = Array.isArray(sum.axis_summaries) ? sum.axis_summaries : [];
    const borderItems = Array.isArray(sum.borders) ? sum.borders : [];
    const borderByIndex = new Map();
    borderItems.forEach((item, idx) => {
      const key = item?.border_index || idx + 1;
      borderByIndex.set(key, item);
    });
    if (axisItems.length) {
      axisItems.forEach((item, idx) => {
        const borderIdx = item.border_index || idx + 1;
        entries.push({
          file: f,
          border_index: borderIdx,
          axis_summary: item,
          bbox: item.bbox,
          bbox_world: item.bbox_world,
          border: borderByIndex.get(borderIdx) || null,
        });
      });
    } else if (borderItems.length) {
      borderItems.forEach((item, idx) => {
        entries.push({
          file: f,
          border_index: idx + 1,
          border: item,
          bbox_world: item.bbox_world,
        });
      });
    }
  });
  if (!entries.length) {
    view.textContent = "분석 결과를 불러오는 중입니다...";
    return;
  }
  const selectedIdx = Math.min(Math.max(state.aiBorderIndex || 0, 0), Math.max(entries.length - 1, 0));
  state.aiBorderIndex = selectedIdx;

  const shortenName = (name, max = 22) => {
    if (!name || name.length <= max) return name || "";
    const head = Math.max(6, Math.floor(max * 0.55));
    const tail = Math.max(4, max - head - 3);
    return `${name.slice(0, head)}...${name.slice(name.length - tail)}`;
  };

  if (list) {
    list.innerHTML = "";
    entries.forEach((item, idx) => {
      const btn = document.createElement("button");
      btn.className = "btn ghost";
      if (idx === selectedIdx) btn.classList.add("active");
      const fileLabel = shortenName(item.file?.name || "파일");
      const borderLabel = item.border_index || idx + 1;
      btn.textContent = `${fileLabel} / 도곽 ${borderLabel}`;
      btn.title = `${item.file?.name || "파일"} / 도곽 ${borderLabel}`;
      btn.onclick = () => {
        state.aiBorderIndex = idx;
        renderAiResultView();
      };
      list.appendChild(btn);
    });
  }

  const active = entries[selectedIdx] || {};
  const axisSummary = active.axis_summary || {};
  const xAxes = axisSummary.x_axes || [];
  const yAxes = axisSummary.y_axes || [];
  const xSpacing = axisSummary.x_spacing || [];
  const ySpacing = axisSummary.y_spacing || [];
  const borderBBox = active.bbox || active.bbox_world || active.border?.bbox_world || null;
  const activeFile = active.file || file;

  const formatAxisLine = (axes, spacing) => {
    if (!axes.length) return "없음";
    const parts = [];
    axes.forEach((axisItem, idx) => {
      const label = axisItem.label || `X${idx + 1}`;
      parts.push(label);
      if (idx < spacing.length) {
        let dist = spacing[idx];
        if (typeof dist === "number") {
          dist = dist.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        parts.push(`←${dist}→`);
      }
    });
    return parts.join("|");
  };

  const activeSummary = activeFile.semanticSummary || {};
  const columnTypes = Array.isArray(activeSummary.column_types) ? activeSummary.column_types : [];
  const columnCount = typeof activeSummary.column_count === "number" ? activeSummary.column_count : 0;
  const columnRows = columnTypes
    .map((col) => {
      const size = col.size || {};
      const sizeLabel =
        size.shape === "circle"
          ? `R ${Number(size.radius || 0).toFixed(2)}`
          : size.shape === "rect"
          ? `${Number(size.width || 0).toFixed(2)} × ${Number(size.height || 0).toFixed(2)}`
          : "-";
      const countLabel = typeof col.count === "number" ? col.count : 0;
      return `<tr><td>${col.type}</td><td>${sizeLabel}</td><td>${countLabel}</td></tr>`;
    })
    .join("");

  view.innerHTML = `
    <div class="card" style="margin-top:10px; background:var(--surface-2);">
      <div id="dxfPreview" class="preview-frame"></div>
    </div>
    <div class="card" style="margin-top:10px; background:var(--surface-2);">
      <div style="font-weight:700;">축선</div>
      <div class="muted" style="margin-top:4px;">X축: ${formatAxisLine(yAxes, ySpacing)}</div>
      <div class="muted">Y축: ${formatAxisLine(xAxes, xSpacing)}</div>
    </div>
    <div class="card" style="margin-top:12px; background:var(--surface-2);">
      <div style="font-weight:700; margin-bottom:6px;">기둥 일람표 (${columnCount}개)</div>
      <table style="width:100%; border-collapse: collapse;">
        <thead>
          <tr>
            <th style="text-align:left; padding:6px 4px; border-bottom:1px solid var(--border);">Type</th>
            <th style="text-align:left; padding:6px 4px; border-bottom:1px solid var(--border);">Size</th>
            <th style="text-align:left; padding:6px 4px; border-bottom:1px solid var(--border);">Count</th>
          </tr>
        </thead>
        <tbody>
          ${columnRows || "<tr><td colspan='3' class='muted' style='padding:6px 4px;'>결과 없음</td></tr>"}
        </tbody>
      </table>
    </div>
  `;
  renderDxfPreview(activeFile, borderBBox);
}
