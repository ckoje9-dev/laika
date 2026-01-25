/**
 * 스마트 셀렉트 컴포넌트
 */
import { state } from './state.js';

// Forward declaration to avoid circular dependency
let loadParsedFn = null;
export function setLoadParsedFn(fn) {
  loadParsedFn = fn;
}

export function applyTemplateSelections() {
  const layers = state.layerOptions || [];
  const blocks = state.blockOptions || [];
  const findMatches = (arr, keys) =>
    arr.filter((name) => keys.some((k) => (name || "").toUpperCase().includes(k))).map((v) => v);

  const presets = {
    "basic-border-block": { type: "block", keys: ["FORM", "TITLE", "BORD"] },
    "basic-dim-layer": { type: "layer", keys: ["DIM"] },
    "basic-symbol-layer": { type: "layer", keys: ["SYM"] },
    "basic-text-layer": { type: "layer", keys: ["TXT", "TEXT"] },
    "struct-axis-layer": { type: "layer", keys: ["AXIS", "GRID", "CEN"] },
    "struct-ccol-layer": { type: "layer", keys: ["COL"] },
    "struct-scol-layer": { type: "layer", keys: ["STL"] },
    "struct-cwall-layer": { type: "layer", keys: ["CON"] },
    "non-wall-layer": { type: "layer", keys: ["WAL"] },
    "non-door-layer": { type: "layer", keys: ["DOOR"] },
    "non-window-layer": { type: "layer", keys: ["WIN"] },
    "non-stair-layer": { type: "layer", keys: ["STR"] },
    "non-elevator-layer": { type: "layer", keys: ["ELV"] },
    "non-furniture-layer": { type: "layer", keys: ["FURN"] },
    "non-finish-layer": { type: "layer", keys: ["FIN"] },
  };

  Object.entries(presets).forEach(([id, cfg]) => {
    const pool = cfg.type === "layer" ? layers : blocks;
    state.selectedOptions[id] = findMatches(pool, cfg.keys);
  });
  initSmartSelects();
}

export function initSmartSelects() {
  const closeAll = () => document.querySelectorAll(".smart-select.open").forEach((s) => s.classList.remove("open"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".smart-select")) closeAll();
  });
  document.querySelectorAll(".smart-select").forEach((container) => {
    const type = container.dataset.selectType;
    const id = container.id;
    let options = [];
    if (type === "layer") options = state.layerOptions || [];
    else if (type === "block") options = state.blockOptions || [];
    else if (type === "template") options = (state.analyzeFiles || []).map((f) => f.name);
    const selected = new Set(state.selectedOptions[id] || []);
    const placeholder =
      type === "layer"
        ? "레이어를 선택하세요."
        : type === "block"
        ? "블록을 선택하세요."
        : "템플릿을 선택하세요.";
    container.innerHTML = `
      <div class="smart-display"><span class="muted">${placeholder}</span></div>
      <div class="smart-dropdown">
        <input class="smart-search" placeholder="검색..." />
        <div class="smart-list"></div>
      </div>
    `;
    const display = container.querySelector(".smart-display");
    const search = container.querySelector(".smart-search");
    const list = container.querySelector(".smart-list");

    const renderList = (keyword = "") => {
      list.innerHTML = "";
      options
        .filter((opt) => opt.toLowerCase().includes(keyword.toLowerCase()))
        .forEach((opt) => {
          const row = document.createElement("label");
          row.className = "smart-option";
          const input = document.createElement("input");
          input.type = type === "template" ? "radio" : "checkbox";
          input.name = type === "template" ? "template-select" : undefined;
          input.value = opt;
          input.checked = selected.has(opt);
          input.onchange = () => {
            if (type === "template") {
              selected.clear();
              if (input.checked) selected.add(opt);
              const nextTemplate = (state.analyzeFiles || []).find((f) => f.name === opt);
              if (nextTemplate) {
                state.templateFile = nextTemplate;
                state.selectedResult = nextTemplate;
                if (loadParsedFn) loadParsedFn(nextTemplate).catch(() => {});
              }
              state.selectedOptions[id] = Array.from(selected);
              applyTemplateSelections();
              closeAll();
              updateDisplay();
              return;
            }
            if (input.checked) selected.add(opt);
            else selected.delete(opt);
            state.selectedOptions[id] = Array.from(selected);
            updateDisplay();
          };
          row.appendChild(input);
          row.appendChild(document.createTextNode(opt));
          list.appendChild(row);
        });
    };

    const updateDisplay = () => {
      const arr = Array.from(selected);
      display.textContent =
        arr.length > 0
          ? arr.join(", ")
          : type === "layer"
          ? "레이어를 선택하세요."
          : type === "block"
          ? "블록을 선택하세요."
          : "템플릿을 선택하세요.";
    };

    display.onclick = (e) => {
      e.stopPropagation();
      const isOpen = container.classList.contains("open");
      closeAll();
      if (!isOpen) container.classList.add("open");
    };
    search.oninput = () => renderList(search.value);

    renderList();
    updateDisplay();
  });
}
