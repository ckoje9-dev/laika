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
  if (!file.parsedData) {
    if (file.fileId) {
      if (!file._loadingParsed) {
        file._loadingParsed = true;
        refreshParsedData(file)
          .catch(() => {})
          .finally(() => {
            file._loadingParsed = false;
            renderResultView();
          });
      }
    }
    view.innerHTML = '<div class="muted">파싱 결과를 불러오는 중입니다...</div>';
    return;
  }
  // entitiesTable은 선택적으로 로드 (없어도 기본 결과 표시)
  if (!file.entitiesTable && !file._loadingEntities && !file._entitiesLoadFailed && file.fileId) {
    file._loadingEntities = true;
    refreshEntitiesTable(file)
      .catch(() => { file._entitiesLoadFailed = true; })
      .finally(() => {
        file._loadingEntities = false;
        renderResultView();
      });
  }
  const data = file.parsedData;
  const layers = data.layers || [];
  const blocks = data.blocks || [];
  const totalEntities =
    typeof file.entityHandleCount === "number"
      ? file.entityHandleCount
      : typeof data.total === "number"
      ? data.total
      : Array.isArray(data.entities)
      ? data.entities.length
      : 0;
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");

  // --- Sort state ---
  if (!file._sort) file._sort = {};
  const sortRows = (rows, key) => {
    const s = file._sort[key];
    if (!s || !s.col) return rows;
    const { col, dir } = s;
    return [...rows].sort((a, b) => {
      let va = a[col] ?? "", vb = b[col] ?? "";
      if (typeof va === "number" && typeof vb === "number") return dir === "asc" ? va - vb : vb - va;
      return dir === "asc"
        ? String(va).localeCompare(String(vb), undefined, { numeric: true })
        : String(vb).localeCompare(String(va), undefined, { numeric: true });
    });
  };
  const sortArrow = (key, col) => {
    const s = file._sort[key];
    if (s && s.col === col) return `<span class="sort-arrow">${s.dir === "asc" ? "\u25B2" : "\u25BC"}</span>`;
    return `<span class="sort-arrow muted">\u25B2</span>`;
  };

  // --- ACI color index → CSS color ---
  const ACI = {1:"#FF0000",2:"#FFFF00",3:"#00FF00",4:"#00FFFF",5:"#0000FF",6:"#FF00FF",7:"#FFFFFF",8:"#808080",9:"#C0C0C0",10:"#FF0000",30:"#FF7F00",40:"#FFBF00",50:"#BFFF00",70:"#00FF7F",90:"#007FFF",130:"#7F00FF",170:"#FF007F",200:"#BF7F7F",250:"#505050"};
  const aciColor = (idx) => ACI[idx] || null;
  const colorPatch = (idx) => {
    const c = aciColor(idx);
    if (c) return `<span class="color-patch" style="background:${c};"></span>`;
    if (idx === 0) return `<span class="muted" style="font-size:11px;">BYBLOCK</span>`;
    if (idx === 256) return `<span class="muted" style="font-size:11px;">BYLAYER</span>`;
    return `<span class="color-patch" style="background:hsl(${(idx * 137) % 360},60%,50%);"></span>`;
  };

  // === 레이어 TABLE ===
  const layerData = layers.map((l) => ({
    name: l.name || l.layer || String(l),
    colorIndex: typeof l.colorIndex === "number" ? l.colorIndex : 0,
    visible: l.visible !== false,
    frozen: l.frozen === true,
  }));
  const sortedLayers = sortRows(layerData, "layers");
  const layerRows = sortedLayers.map((l) => `<tr>
    <td>${l.name}</td>
    <td style="text-align:center;">${colorPatch(l.colorIndex)}</td>
    <td style="text-align:center;">${l.visible ? "\u2713" : "-"}</td>
    <td style="text-align:center;">${l.frozen ? "\u2713" : "-"}</td>
  </tr>`).join("");

  // === 블록 TABLE ===
  const blockData = blocks.map((b) => ({
    name: b.name || b.block_name || String(b),
    count: typeof b.count === "number" ? b.count : 0,
  })).filter((b) => !b.name.startsWith("*"));
  const sortedBlocks = sortRows(blockData, "blocks");
  const blockRows = sortedBlocks.map((b) => `<tr>
    <td>${b.name}</td>
    <td style="text-align:right;">${fmt(b.count)}</td>
  </tr>`).join("");

  // === 엔티티 TABLE ===
  const entitiesTable = Array.isArray(file.entitiesTable) ? file.entitiesTable : [];
  const entitiesColumns = Array.isArray(file.entitiesTableColumns) ? file.entitiesTableColumns : [];
  const sourceRows = entitiesTable.length ? entitiesTable.slice(0, 200) : [];
  const coordColumns = new Set(["vertices","startpoint","endpoint","center","position"].map(v => v.toLowerCase()));
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
      if (Array.isArray(raw) && raw[0]) return { x: raw[0].x || 0, y: raw[0].y || 0, z: raw[0].z || 0 };
      if (raw && typeof raw === "object") return { x: raw.x || 0, y: raw.y || 0, z: raw.z || 0 };
    }
    return null;
  };
  const sortedEntities = sortRows(sourceRows, "entities");
  const entityRows = sortedEntities.map((row) => {
    const coord = extractCoords(row);
    return `<tr>
      <td class="col-handle">${row.handle || "-"}</td>
      <td class="col-type">${row.type || "-"}</td>
      <td class="col-layer">${row.layer || "-"}</td>
      <td class="col-coord">${coord ? formatCoord(coord.x) : "-"}</td>
      <td class="col-coord">${coord ? formatCoord(coord.y) : "-"}</td>
      <td class="col-coord">${coord ? formatCoord(coord.z) : "-"}</td>
      <td class="col-text">${row.text || "-"}</td>
      <td class="col-name">${row.name || "-"}</td>
      <td class="col-radius">${row.radius ? formatCoord(row.radius) : "-"}</td>
      <td class="col-dim">${row.actualMeasurement ? formatCoord(row.actualMeasurement) : "-"}</td>
    </tr>`;
  }).join("");

  view.innerHTML = `
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px;">
      <div>
        <div style="font-weight:700; margin-bottom:6px;">레이어 TABLE <span class="muted" style="font-weight:400;">(총 ${fmt(layers.length)} layers)</span></div>
        <div class="table-wrap sticky-table" style="max-height:260px;">
          <table>
            <thead><tr>
              <th class="sortable" data-tbl="layers" data-col="name">layer_name ${sortArrow("layers","name")}</th>
              <th style="width:80px; text-align:center;">colorIndex</th>
              <th style="width:60px; text-align:center;">visible</th>
              <th style="width:60px; text-align:center;">frozen</th>
            </tr></thead>
            <tbody>${layerRows || '<tr><td colspan="4" class="muted">레이어 없음</td></tr>'}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div style="font-weight:700; margin-bottom:6px;">블록 TABLE <span class="muted" style="font-weight:400;">(총 ${fmt(blockData.length)} blocks)</span></div>
        <div class="table-wrap sticky-table" style="max-height:260px;">
          <table>
            <thead><tr>
              <th class="sortable" data-tbl="blocks" data-col="name">block_name ${sortArrow("blocks","name")}</th>
              <th class="sortable" data-tbl="blocks" data-col="count" style="width:100px; text-align:right;">block_cnt ${sortArrow("blocks","count")}</th>
            </tr></thead>
            <tbody>${blockRows || '<tr><td colspan="2" class="muted">블록 없음</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </div>
    <div style="margin-top:16px;">
      <div style="font-weight:700; margin-bottom:6px;">엔티티 TABLE <span class="muted" style="font-weight:400;">(총 ${fmt(totalEntities)} entities)</span></div>
      <div class="table-wrap sticky-table" style="max-height:360px;">
        <table>
          <thead><tr>
            <th class="sortable col-handle" data-tbl="entities" data-col="handle">handle ${sortArrow("entities","handle")}</th>
            <th class="sortable col-type" data-tbl="entities" data-col="type">type ${sortArrow("entities","type")}</th>
            <th class="sortable col-layer" data-tbl="entities" data-col="layer">layer_name ${sortArrow("entities","layer")}</th>
            <th class="col-coord">x</th><th class="col-coord">y</th><th class="col-coord">z</th>
            <th class="col-text">text</th><th class="col-name">name</th>
            <th class="col-radius">radius</th><th class="col-dim">dim</th>
          </tr></thead>
          <tbody>${entityRows || '<tr><td colspan="10" class="muted">엔티티 없음</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  `;
  // 정렬 클릭 핸들러
  view.querySelectorAll("th.sortable").forEach((th) => {
    th.onclick = () => {
      const tbl = th.dataset.tbl;
      const col = th.dataset.col;
      const cur = file._sort[tbl];
      file._sort[tbl] = cur && cur.col === col
        ? { col, dir: cur.dir === "asc" ? "desc" : "asc" }
        : { col, dir: "asc" };
      renderResultView();
    };
  });
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
